"""论文检索服务：OpenAlex + arXiv 双数据源，合并后去重。

数据源（均为公开免费 API，无需 Key）：
    - OpenAlex  https://api.openalex.org/works
      filter=from_publication_date/to_publication_date（最近 7 天）+ search，
      per-page 25；摘要从 abstract_inverted_index 还原。
    - arXiv     http://export.arxiv.org/api/query
      search_query=all:关键词，sortBy=submittedDate，只保留 7 天内结果，
      is_preprint=true，venue="arXiv"。

每个查询词分别检索后合并，按 external_id + 归一化标题去重。
单数据源超时/异常记日志后继续，不中断整体流程。
"""
from __future__ import annotations

import datetime as dt
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx

from .. import utils

OPENALEX_URL = "https://api.openalex.org/works"
ARXIV_URL = "https://export.arxiv.org/api/query"  # 必须用 https，http 会 301 跳转
MAILTO = "paper-radar@localhost"  # OpenAlex 礼貌标识，利于进入快速通道
PER_PAGE = 25
TIMEOUT = 30


@dataclass
class PaperCandidate:
    """检索到的单篇论文候选（尚未入库）。"""

    external_id: str  # 如 openalex:W123 / arxiv:2609.12345
    title: str
    authors: list[str] = field(default_factory=list)
    venue: str | None = None
    published_date: dt.date | None = None
    url: str | None = None
    abstract: str = ""
    source: str = ""  # openalex / arxiv
    is_preprint: bool = False


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------

def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """把 OpenAlex 的 abstract_inverted_index 还原为摘要文本（最多取前 600 词）。"""
    if not inverted_index:
        return ""
    try:
        pairs: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions or []:
                pairs.append((int(pos), word))
        pairs.sort(key=lambda x: x[0])
        return " ".join(w for _, w in pairs[:600])
    except Exception:
        return ""


def _parse_openalex_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except Exception:
        return None


def fetch_openalex(query: str, since: dt.date, until: dt.date, db=None) -> list[PaperCandidate]:
    """用单个查询词检索 OpenAlex 最近 7 天的论文。失败返回空列表并记日志。"""
    params = {
        "filter": f"from_publication_date:{since.isoformat()},to_publication_date:{until.isoformat()}",
        "search": query,
        "per-page": PER_PAGE,
        "select": "id,title,authorships,primary_location,publication_date,doi,abstract_inverted_index",
        "mailto": MAILTO,
    }
    headers = {"User-Agent": f"AI-Paper-Radar/1.0 (mailto:{MAILTO})"}
    try:
        with httpx.Client(timeout=TIMEOUT, headers=headers) as client:
            resp = client.get(OPENALEX_URL, params=params)
        resp.raise_for_status()
        works = resp.json().get("results", [])
    except Exception as e:
        if db is not None:
            utils.log_event(db, "search", "ERROR", f"OpenAlex 检索失败 query={query} 错误={type(e).__name__}: {e}")
        return []

    candidates: list[PaperCandidate] = []
    for w in works:
        try:
            oid = (w.get("id") or "").rsplit("/", 1)[-1]  # https://openalex.org/W123 -> W123
            if not oid:
                continue
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in (w.get("authorships") or [])
                if a.get("author", {}).get("display_name")
            ]
            loc = w.get("primary_location") or {}
            source = loc.get("source") or {}
            venue = source.get("display_name")
            source_type = (source.get("type") or "").lower()
            is_preprint = source_type == "repository" or (venue or "").lower().startswith("arxiv")
            doi = w.get("doi")  # OpenAlex 的 doi 已是完整 URL
            url = doi or loc.get("landing_page_url") or w.get("id")
            candidates.append(
                PaperCandidate(
                    external_id=f"openalex:{oid}",
                    title=(w.get("title") or "").strip(),
                    authors=authors,
                    venue=venue,
                    published_date=_parse_openalex_date(w.get("publication_date")),
                    url=url,
                    abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
                    source="openalex",
                    is_preprint=is_preprint,
                )
            )
        except Exception:
            continue
    if db is not None:
        utils.log_event(db, "search", "INFO", f"OpenAlex 检索完成 query={query} 结果 {len(candidates)} 篇")
    return candidates


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

_ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}
_ARXIV_MIN_INTERVAL = 3.0  # arXiv 官方要求请求间隔至少 3 秒
_ARXIV_RETRIES = 3
_arxiv_lock = threading.Lock()
_last_arxiv_ts = 0.0


def _arxiv_throttle() -> None:
    """保证 arXiv 请求间隔 ≥3 秒（官方限流要求），否则会被 429。"""
    global _last_arxiv_ts
    with _arxiv_lock:
        now = time.monotonic()
        wait = _ARXIV_MIN_INTERVAL - (now - _last_arxiv_ts)
        if wait > 0:
            time.sleep(wait)
        _last_arxiv_ts = time.monotonic()


def _parse_arxiv_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except Exception:
        return None


def _fetch_arxiv_once(query: str, since: dt.date) -> list[PaperCandidate]:
    """单次 arXiv 请求 + 解析（内部用，失败抛异常由 fetch_arxiv 重试）。"""
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": PER_PAGE,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    # arXiv 推送大 XML 较慢：读超时放宽到 90 秒
    timeout = httpx.Timeout(connect=15.0, read=90.0, write=15.0, pool=15.0)
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(ARXIV_URL, params=params)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    candidates: list[PaperCandidate] = []
    for entry in root.findall("a:entry", _ARXIV_NS):
        try:
            raw_id = (entry.findtext("a:id", default="", namespaces=_ARXIV_NS) or "").strip()
            m = re.search(r"(\d{4}\.\d{4,5})", raw_id)
            if not m:
                continue
            arxiv_id = m.group(1)  # 去掉版本号
            published = _parse_arxiv_date(entry.findtext("a:published", default="", namespaces=_ARXIV_NS))
            if published is None or published < since:
                continue
            title = re.sub(r"\s+", " ", entry.findtext("a:title", default="", namespaces=_ARXIV_NS) or "").strip()
            authors = [
                (a.findtext("a:name", default="", namespaces=_ARXIV_NS) or "").strip()
                for a in entry.findall("a:author", _ARXIV_NS)
            ]
            authors = [a for a in authors if a]
            abstract = re.sub(r"\s+", " ", entry.findtext("a:summary", default="", namespaces=_ARXIV_NS) or "").strip()
            candidates.append(
                PaperCandidate(
                    external_id=f"arxiv:{arxiv_id}",
                    title=title,
                    authors=authors,
                    venue="arXiv",
                    published_date=published,
                    url=f"https://arxiv.org/abs/{arxiv_id}",
                    abstract=abstract,
                    source="arxiv",
                    is_preprint=True,
                )
            )
        except Exception:
            continue
    return candidates


def fetch_arxiv(query: str, since: dt.date, db=None) -> list[PaperCandidate]:
    """用单个查询词检索 arXiv（按提交时间倒序），只保留 since 之后的结果。

    arXiv 限流严格（常 429）且响应慢：请求间隔 ≥3 秒，
    429/5xx/超时/网络错误做退避重试（最多 3 次），仍失败返回空列表。
    """
    _arxiv_throttle()
    last_err: Exception | None = None
    for attempt in range(1, _ARXIV_RETRIES + 1):
        try:
            candidates = _fetch_arxiv_once(query, since)
            if db is not None:
                utils.log_event(db, "search", "INFO",
                                f"arXiv 检索完成 query={query} 结果 {len(candidates)} 篇（已过滤 7 天内）")
            return candidates
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            last_err = e
            if status == 429 or 500 <= status < 600:
                retry_after = e.response.headers.get("retry-after", "")
                wait = float(retry_after) if retry_after.strip().isdigit() else 5.0 * attempt
                if attempt < _ARXIV_RETRIES and db is not None:
                    utils.log_event(db, "search", "WARNING",
                                    f"arXiv 被限流/服务端错误（{status}），{wait:.0f}s 后重试 "
                                    f"query={query}（{attempt}/{_ARXIV_RETRIES}）")
                if attempt < _ARXIV_RETRIES:
                    time.sleep(wait)
                    continue
            break  # 其他 4xx 不重试
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last_err = e
            wait = 5.0 * attempt
            if attempt < _ARXIV_RETRIES:
                if db is not None:
                    utils.log_event(db, "search", "WARNING",
                                    f"arXiv 请求超时/网络错误（{type(e).__name__}），{wait:.0f}s 后重试 "
                                    f"query={query}（{attempt}/{_ARXIV_RETRIES}）")
                time.sleep(wait)
                continue
            break
        except Exception as e:  # 解析等未知错误不重试
            last_err = e
            break
    if db is not None and last_err is not None:
        utils.log_event(db, "search", "ERROR",
                        f"arXiv 检索失败（已重试 {_ARXIV_RETRIES} 次）query={query} "
                        f"错误={type(last_err).__name__}: {last_err}")
    return []


# ---------------------------------------------------------------------------
# 合并去重
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def dedupe(candidates: list[PaperCandidate]) -> list[PaperCandidate]:
    """按 external_id + 归一化标题去重，保留首次出现。"""
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[PaperCandidate] = []
    for c in candidates:
        norm = _normalize_title(c.title)
        if c.external_id in seen_ids or (norm and norm in seen_titles):
            continue
        seen_ids.add(c.external_id)
        if norm:
            seen_titles.add(norm)
        unique.append(c)
    return unique


def search_all(queries: list[str], db=None) -> list[PaperCandidate]:
    """对每个查询词分别检索 OpenAlex + arXiv，合并去重后返回。

    db 可选：传入则记录每个查询词的检索日志。
    """
    until = utils.today()
    since = until - dt.timedelta(days=6)  # 最近 7 天（含今天）
    all_candidates: list[PaperCandidate] = []
    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        all_candidates.extend(fetch_openalex(q, since, until, db))
        all_candidates.extend(fetch_arxiv(q, since, db))
    unique = dedupe(all_candidates)
    if db is not None:
        utils.log_event(
            db, "search", "INFO",
            f"检索完成：{len(queries)} 个查询词，原始 {len(all_candidates)} 篇，去重后 {len(unique)} 篇",
        )
    return unique
