"""学科 -> 期刊/顶会 预设库。

数据文件：backend/app/data/venues.json（31 个学科，约 200 个刊/会）。
提供：学科清单、刊会别名匹配（硬过滤用）、arXiv 分类前缀（预印本过滤用）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent.parent / "venues.json"


@lru_cache(maxsize=1)
def load_library() -> dict:
    """加载刊会库（进程内缓存）。返回 {"disciplines": [...]}。"""
    try:
        return json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"disciplines": []}


@lru_cache(maxsize=1)
def discipline_map() -> dict[str, dict]:
    """discipline_id -> 学科对象。"""
    return {d["id"]: d for d in load_library().get("disciplines", [])}


@lru_cache(maxsize=1)
def venue_alias_map() -> dict[str, list[str]]:
    """刊会小写名 -> 别名小写列表（含自身），用于硬过滤时的 venue 匹配。"""
    out: dict[str, list[str]] = {}
    for d in load_library().get("disciplines", []):
        for v in d.get("venues", []):
            key = v["name"].strip().lower()
            names = {key} | {a.strip().lower() for a in v.get("aliases", []) if a}
            out[key] = sorted(names)
    return out


def arxiv_prefixes_for(discipline_ids: list[str]) -> list[str]:
    """所选学科对应的 arXiv 分类前缀（如 cs_ai -> [cs, eess]）。"""
    prefixes: set[str] = set()
    dmap = discipline_map()
    for did in discipline_ids or []:
        d = dmap.get(did)
        if d:
            prefixes.update(p.strip().lower() for p in d.get("arxiv_categories", []))
    return sorted(prefixes)


def discipline_names(discipline_ids: list[str]) -> list[str]:
    """discipline_id 列表 -> 学科中文名列表（未知 id 原样保留）。"""
    dmap = discipline_map()
    return [dmap[d]["name"] if d in dmap else d for d in (discipline_ids or [])]


# 预印本服务器识别（按 venue 名关键字）
_PREPRINT_SERVERS = ("biorxiv", "medrxiv", "ssrn", "arxiv")


def _preprint_server(venue_name: str) -> str:
    v = (venue_name or "").lower()
    for key in _PREPRINT_SERVERS:
        if key in v:
            return key
    return "arxiv"


def venue_allowed(venue: str | None, is_preprint: bool,
                  categories: list[str] | None,
                  selected_venues: list[str],
                  arxiv_prefixes: list[str],
                  preprint_open: bool = False) -> bool:
    """硬过滤：判断单篇论文的 venue 是否在用户所选刊会范围内。

    - selected 为空 -> 不限制（兜底，避免误杀出空周报）
    - 预印本：按 bioRxiv / medRxiv / SSRN / arXiv 分别匹配用户勾选；
      arXiv 额外按分类前缀过滤（无分类信息时无法证伪则放行，靠 LLM 打分二次把关）；
      preprint_open=True 时（老画像无学科信息）放行所有预印本
    - 期刊/会议：venue 名（或别名）包含所选刊会名即命中
    """
    selected = [v.strip().lower() for v in (selected_venues or []) if v and v.strip()]
    if not selected:
        return True
    vname = (venue or "").strip().lower()
    amap = venue_alias_map()
    server = _preprint_server(vname)

    # 预印本分支：arXiv / bioRxiv / medRxiv / SSRN 各自独立匹配用户勾选
    if is_preprint or server != "arxiv" or vname == "arxiv":
        if preprint_open:
            return True
        if server not in selected:
            return False
        if server == "arxiv" and arxiv_prefixes:
            cats = [(c or "").strip().lower() for c in (categories or [])]
            if not cats:
                return True  # OpenAlex 不提供 arXiv 分类，无法证伪则放行
            return any(c.startswith(p) for c in cats for p in arxiv_prefixes)
        return True

    for sel in selected:
        if sel in _PREPRINT_SERVERS:
            continue
        candidates = amap.get(sel, [sel])
        if any(c and c in vname for c in candidates):
            return True
    return False
