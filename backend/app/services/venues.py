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


def all_venue_names(discipline_ids: list[str]) -> list[str]:
    """所选学科的全部刊会名（供前端默认全选）。"""
    names: list[str] = []
    dmap = discipline_map()
    for did in discipline_ids or []:
        d = dmap.get(did)
        if d:
            names.extend(v["name"] for v in d.get("venues", []))
    # 去重保序
    seen: set[str] = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def venue_allowed(venue: str | None, is_preprint: bool,
                  categories: list[str] | None,
                  selected_venues: list[str],
                  arxiv_prefixes: list[str]) -> bool:
    """硬过滤：判断单篇论文的 venue 是否在用户所选刊会范围内。

    - selected 为空 -> 不限制（兜底，避免误杀出空周报）
    - arXiv 预印本：需选中 arXiv，且分类前缀命中所选学科的 arXiv 分类
    - 期刊/会议：venue 名（或别名）包含所选刊会名即命中
    """
    selected = [v.strip().lower() for v in (selected_venues or []) if v and v.strip()]
    if not selected:
        return True
    vname = (venue or "").strip().lower()
    amap = venue_alias_map()

    if is_preprint or vname == "arxiv":
        if "arxiv" not in selected:
            return False
        if not arxiv_prefixes:
            return True
        cats = [(c or "").strip().lower() for c in (categories or [])]
        return any(c.startswith(p) for c in cats for p in arxiv_prefixes)

    for sel in selected:
        if sel == "arxiv":
            continue
        candidates = amap.get(sel, [sel])
        if any(c and c in vname for c in candidates):
            return True
    return False
