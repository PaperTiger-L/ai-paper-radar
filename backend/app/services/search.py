"""论文检索服务：AnySearch 统一检索（学术双通道）。

数据源（需要 API Key）：
    - academic.search    跨学科论文检索（期刊 + 预印本，Semantic Scholar 类）
    - academic.preprint  预印本检索（CS/物理/数学/生物/经济）
    两条通道均用默认相关性排序（实测按时间倒序会严重损失相关性），
    时效由代码侧的 _within_window 粗过滤保证。
    POST https://api.anysearch.com/v1/search
    鉴权：Authorization: Bearer <key>

Key 来源（优先级从高到低）：
    1. 后台「检索配置」页面保存的 Key（Setting 表 search.anysearch_api_key）
    2. 环境变量 ANYSEARCH_API_KEY
    两处都未配置时检索直接报错（不降级匿名访问，避免不知不觉
    烧掉匿名每日免费额度）。

每个查询词分别走两个通道检索后合并，按 external_id + 归一化标题去重。
单通道超时/异常记日志后继续，不中断整体流程。

与旧实现（OpenAlex + arXiv）的已知差异：
    - AnySearch 的 REST 结果只有 title/url/snippet/content 四个字段，没有结构化的
      作者/发表日期。作者、年份、venue 从 snippet 解析（格式如
      "A, B, et al. (2025) — arXiv (Cornell University) — cited 3 times"），
      arXiv 链接可从编号解析出年月。
    - 因此精确到"天"的 7 天过滤做不到，采用"默认相关性排序 + 年/月粗过滤"近似：
      保留 snippet 年份 >= since 年份、且 arXiv 编号年月不早于 since 上一个月的
      结果（多留一个月是为覆盖周窗口跨月边界的情况）。是近似值，LLM 打分阶段
      会再做一轮相关性筛选。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field

import httpx

from .. import utils
from ..config import settings

ANYSEARCH_URL = "https://api.anysearch.com/v1/search"
PER_PAGE = 10  # AnySearch 上限 1-10
TIMEOUT = 30

# Setting 表中的键（后台「检索配置」页面读写）
K_API_KEY = "search.anysearch_api_key"
K_UPDATED_AT = "search.updated_at"

# 双通道：跨学科检索（替代 OpenAlex） + 预印本检索（替代 arXiv）
# 注意：不传 sort 参数（用默认相关性排序）。实测按发表时间倒序会严重
# 损失相关性（返回"最新但不相关"的结果）；时效由 _within_window 在代码侧过滤。
LEG_SEARCH = ("academic.search", {})
LEG_PREPRINT = ("academic.preprint", {"type": "preprint"})


@dataclass
class PaperCandidate:
    """检索到的单篇论文候选（尚未入库）。"""

    external_id: str  # 如 arxiv:2609.12345 / doi:10.1101/xxx / anysearch:<md5>
    title: str
    authors: list[str] = field(default_factory=list)
    venue: str | None = None
    published_date: dt.date | None = None  # 精度到月（arXiv 编号）或年（snippet）
    url: str | None = None
    abstract: str = ""
    source: str = ""  # academic.search / academic.preprint
    is_preprint: bool = False
    categories: list[str] = field(default_factory=list)


class AnySearchError(Exception):
    """AnySearch 调用失败。"""


class AnySearchNotConfigured(AnySearchError):
    """未配置 ANYSEARCH_API_KEY。"""


def mask_api_key(key: str) -> str:
    """API Key 脱敏展示（委托 utils.mask_secret）。"""
    return utils.mask_secret(key)


def get_search_config(db) -> dict:
    """读取检索配置：Key 来源、脱敏预览、更新时间。

    返回 {"api_key": 实际生效的 key（可能为空）, "source": "ui"|"env"|"",
           "updated_at": ...}。明文 key 只在服务端内部使用，绝不直接返回给前端。
    """
    ui_key = (utils.get_setting(db, K_API_KEY, "") or "").strip()
    if ui_key:
        return {"api_key": ui_key, "source": "ui",
                "updated_at": utils.get_setting(db, K_UPDATED_AT)}
    env_key = (settings.anysearch_api_key or "").strip()
    if env_key:
        return {"api_key": env_key, "source": "env", "updated_at": None}
    return {"api_key": "", "source": "", "updated_at": None}


def _get_api_key(db=None) -> str:
    if db is not None:
        key = get_search_config(db)["api_key"]
    else:
        key = (settings.anysearch_api_key or "").strip()
    if not key:
        raise AnySearchNotConfigured(
            "未配置 AnySearch Key：请在后台「检索配置」页面填写，或设置环境变量 ANYSEARCH_API_KEY"
        )
    return key


# ---------------------------------------------------------------------------
# snippet 解析：作者 / 年份 / venue
# 格式示例：
#   "Wuhao Liu, Zhaoyu Fang, Xuyan Du, et al. (2026) — Genome Research"
#   "Junpeng Tan, Zhang, Xin, Lv, Yao, et al. (2023) — arXiv (Cornell University) — cited 1 times [Open Access]"
# ---------------------------------------------------------------------------

_SNIPPET_RE = re.compile(r"^(?P<authors>.*?)\s*\((?P<year>\d{4})\)(?P<rest>.*)$", re.DOTALL)


def _parse_snippet(snippet: str) -> tuple[list[str], int | None, str | None]:
    """从 snippet 解析 (作者列表, 年份, venue)，解析失败对应项为 None/空。"""
    authors: list[str] = []
    year: int | None = None
    venue: str | None = None
    if not snippet:
        return authors, year, venue
    m = _SNIPPET_RE.match(snippet.strip())
    if not m:
        return authors, year, venue
    try:
        year = int(m.group("year"))
    except ValueError:
        year = None
    authors = [
        a.strip()
        for a in m.group("authors").split(",")
        if a.strip() and a.strip().lower() != "et al."
    ]
    rest = (m.group("rest") or "").strip()
    if rest.startswith("—"):
        rest = rest[1:].strip()
    # venue 取第一个 "—" 或 "[" 之前的片段
    venue = re.split(r"[—\[]", rest, maxsplit=1)[0].strip() or None
    return authors, year, venue


_ARXIV_ID_RE = re.compile(r"arxiv\.org/abs/(\d{2})(\d{2})\.(\d{4,5})", re.IGNORECASE)


def _parse_arxiv_ym(url: str | None) -> tuple[int, int] | None:
    """从 arXiv 链接解析 (年, 月)，如 2609.12345 -> (2026, 9)。失败返回 None。"""
    if not url:
        return None
    m = _ARXIV_ID_RE.search(url)
    if not m:
        return None
    try:
        yy, mm = int(m.group(1)), int(m.group(2))
        if not 1 <= mm <= 12:
            return None
        return 2000 + yy, mm
    except ValueError:
        return None


def _stable_id(url: str | None, title: str) -> str:
    """为 AnySearch 结果生成稳定 external_id：arXiv 编号 > DOI > 标题+URL 哈希。"""
    if url:
        m = re.search(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", url, re.IGNORECASE)
        if m:
            return f"arxiv:{m.group(1)}"
        m = re.search(r"doi\.org/(.+?)(?:[?#]|$)", url, re.IGNORECASE)
        if m:
            return f"doi:{m.group(1).rstrip('/')}"
    digest = hashlib.md5(f"{(url or '').strip()}|{title.strip().lower()}".encode()).hexdigest()[:16]
    return f"anysearch:{digest}"


def _within_window(url: str | None, year: int | None, since: dt.date) -> bool:
    """粗过滤：snippet 年份 >= since 年份；arXiv 编号年月不早于 since 上一个月。"""
    if year is None:
        return True  # 解析不出年份时放行，由下游 LLM 打分再筛
    if year < since.year:
        return False
    ym = _parse_arxiv_ym(url)
    if ym:
        ay, am = ym
        return (ay * 12 + am) >= (since.year * 12 + since.month) - 1
    return True


# ---------------------------------------------------------------------------
# AnySearch 单通道检索
# ---------------------------------------------------------------------------

def _fetch_leg(query: str, tag: str, params: dict, db=None,
               max_results: int = PER_PAGE) -> list[dict]:
    """调用 POST /v1/search 单个通道，返回原始 result 列表。失败返回空列表并记日志。"""
    api_key = _get_api_key(db)  # 未配置时直接抛错，search_all 捕获后记日志
    body: dict = {"query": query, "tag": tag, "max_results": max_results, "language": "en"}
    if params:
        body["params"] = params
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                ANYSEARCH_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
            )
        if resp.status_code == 401:
            raise AnySearchError("API Key 无效（401）：请检查 ANYSEARCH_API_KEY 是否正确")
        if resp.status_code == 402:
            raise AnySearchError("AnySearch 配额耗尽（402）：请登录控制台查看/充值")
        if resp.status_code == 429:
            raise AnySearchError("AnySearch 限流（429）：稍后再试")
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise AnySearchError(f"业务错误 code={data.get('code')}：{data.get('message')}")
        return data.get("data", {}).get("results", []) or []
    except AnySearchError:
        raise
    except Exception as e:
        if db is not None:
            utils.log_event(db, "search", "ERROR",
                            f"AnySearch 检索失败 tag={tag} query={query} 错误={type(e).__name__}: {e}")
        return []


def _to_candidate(result: dict, tag: str, since: dt.date) -> PaperCandidate | None:
    """把 AnySearch 原始 result 映射为 PaperCandidate；窗口外返回 None。"""
    title = (result.get("title") or "").strip()
    url = (result.get("url") or "").strip() or None
    snippet = result.get("snippet") or ""
    content = result.get("content") or ""
    if not title:
        return None
    authors, year, venue = _parse_snippet(snippet)
    if not _within_window(url, year, since):
        return None

    ym = _parse_arxiv_ym(url)
    published_date = dt.date(ym[0], ym[1], 1) if ym else (dt.date(year, 1, 1) if year else None)
    # 预印本判定：arXiv 链接，或 venue/URL 命中预印本服务器（与 venues._preprint_server 对齐）
    blob = f"{venue or ''} {url or ''}".lower()
    is_preprint = bool(ym) or any(h in blob for h in ("arxiv", "biorxiv", "medrxiv", "research square", "ssrn"))
    if ym:
        venue = "arXiv"

    abstract = (content.strip() or snippet.strip())
    if len(abstract) > 3000:  # 控制下游 LLM 筛选的 token 消耗
        abstract = abstract[:3000] + "…"

    return PaperCandidate(
        external_id=_stable_id(url, title),
        title=title,
        authors=authors,
        venue=venue,
        published_date=published_date,
        url=url,
        abstract=abstract,
        source=tag,
        is_preprint=is_preprint,
    )


def ping(db) -> str:
    """连通性测试：用 academic.search 真实检索 1 条，返回首条标题。失败抛异常。"""
    results = _fetch_leg("machine learning", "academic.search", {}, db, max_results=1)
    if not results:
        raise AnySearchError("连接正常，但测试检索返回 0 条结果")
    return (results[0].get("title") or "").strip() or "(无标题)"


def fetch_anysearch(query: str, since: dt.date, until: dt.date, db=None) -> list[PaperCandidate]:
    """用单个查询词走 academic.search + academic.preprint 双通道检索。

    未配置 Key 时抛 AnySearchNotConfigured（由 search_all 统一记日志）；
    单通道失败记日志后继续另一通道。
    """
    candidates: list[PaperCandidate] = []
    for tag, params in (LEG_SEARCH, LEG_PREPRINT):
        try:
            results = _fetch_leg(query, tag, params, db)
        except AnySearchNotConfigured:
            raise
        except AnySearchError as e:
            if db is not None:
                utils.log_event(db, "search", "ERROR", f"AnySearch 通道失败 tag={tag} query={query}：{e}")
            continue
        kept = 0
        for r in results:
            cand = _to_candidate(r, tag, since)
            if cand is not None:
                candidates.append(cand)
                kept += 1
        if db is not None:
            utils.log_event(db, "search", "INFO",
                            f"AnySearch 检索完成 tag={tag} query={query} 原始 {len(results)} 篇，窗口内 {kept} 篇")
    return candidates


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


def search_all(queries: list[str], db=None,
               since: dt.date | None = None,
               until: dt.date | None = None) -> list[PaperCandidate]:
    """对每个查询词分别检索 AnySearch 双通道，合并去重后返回。

    since/until 为空时默认最近 7 天（含今天）。
    未配置 ANYSEARCH_API_KEY 时记 ERROR 日志并返回空列表。
    db 可选：传入则记录每个查询词的检索日志。
    """
    until = until or utils.today()
    since = since or (until - dt.timedelta(days=6))
    try:
        _get_api_key(db)
    except AnySearchNotConfigured as e:
        if db is not None:
            utils.log_event(db, "search", "ERROR", f"检索跳过：{e}")
        return []

    all_candidates: list[PaperCandidate] = []
    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        try:
            all_candidates.extend(fetch_anysearch(q, since, until, db))
        except AnySearchNotConfigured as e:
            if db is not None:
                utils.log_event(db, "search", "ERROR", f"检索跳过：{e}")
            return []
    unique = dedupe(all_candidates)
    if db is not None:
        utils.log_event(
            db, "search", "INFO",
            f"检索完成：{len(queries)} 个查询词，原始 {len(all_candidates)} 篇，去重后 {len(unique)} 篇",
        )
    return unique
