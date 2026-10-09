"""LLM 服务：OpenAI 兼容接口（/chat/completions）的统一调用入口。

承担四个任务：
    1. gen_queries      根据用户画像生成英文检索关键词
    2. filter_papers    对候选论文打分筛选（0-10）
    3. summarize        逐篇生成中文标题 / 摘要 / 创新点 / 推荐理由
    4. digest_sections  生成周报的【本周研究动态】与【本周研究启发】

LLM 未配置时各任务均有确定性降级策略（见各函数 docstring），绝不伪造成功。
所有调用均记日志（模型名、任务、成功/失败），绝不记录 API Key。
"""
from __future__ import annotations

import json
import re

import httpx

from .. import utils

# Setting 表中的键
K_PROVIDER = "llm.provider"
K_BASE_URL = "llm.base_url"
K_API_KEY = "llm.api_key"
K_MODEL = "llm.model"
K_UPDATED_AT = "llm.updated_at"

_SYSTEM_PROMPT = (
    "你是一名严谨的学术研究助手。你只基于给定的论文信息进行分析和总结，"
    "绝不编造不存在的论文、数据或结论。所有输出必须为严格的 JSON，不要输出任何多余文字。"
)


class LlmError(Exception):
    """LLM 调用失败。"""


class LlmNotConfigured(LlmError):
    """LLM 尚未配置。"""


def get_llm_config(db) -> dict:
    """读取 LLM 配置（不含 key 明文的使用方请用 has_api_key 判断）。"""
    return {
        "provider": utils.get_setting(db, K_PROVIDER, "") or "",
        "base_url": utils.get_setting(db, K_BASE_URL, "") or "",
        "api_key": utils.get_setting(db, K_API_KEY, "") or "",
        "model": utils.get_setting(db, K_MODEL, "") or "",
        "updated_at": utils.get_setting(db, K_UPDATED_AT),
    }


def is_configured(db) -> bool:
    """LLM 是否已配置（base_url + api_key + model 均非空）。"""
    cfg = get_llm_config(db)
    return bool(cfg["base_url"] and cfg["api_key"] and cfg["model"])


def _extract_json(content: str) -> dict:
    """从模型输出中提取 JSON：先直接解析，失败则尝试 ```json fence / 首尾大括号。"""
    text = (content or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    raise LlmError("模型返回内容不是合法 JSON")


def chat(db, messages: list[dict], task: str, json_mode: bool = True, timeout: int = 120) -> str:
    """调用 OpenAI 兼容的 /chat/completions，返回 message.content 文本。

    task: 任务名，仅用于日志。失败抛 LlmError（携带真实错误信息）。
    """
    cfg = get_llm_config(db)
    if not (cfg["base_url"] and cfg["api_key"] and cfg["model"]):
        raise LlmNotConfigured("LLM 未配置（base_url / api_key / model 缺失）")
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload: dict = {"model": cfg["model"], "messages": messages, "temperature": 0.3}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except LlmNotConfigured:
        raise
    except httpx.HTTPStatusError as e:
        detail = _http_error_detail(e, url)
        utils.log_event(db, "llm", "ERROR",
                        f"LLM 调用失败 task={task} model={cfg['model']} {detail}")
        raise LlmError(detail) from e
    except Exception as e:  # 网络错误 / 解析错误：记录真实原因后上抛
        utils.log_event(db, "llm", "ERROR",
                        f"LLM 调用失败 task={task} model={cfg['model']} 错误={type(e).__name__}: {e}")
        raise LlmError(f"{type(e).__name__}: {e}") from e
    if not content:
        utils.log_event(db, "llm", "ERROR", f"LLM 返回空内容 task={task} model={cfg['model']}")
        raise LlmError("模型返回空内容")
    utils.log_event(db, "llm", "INFO", f"LLM 调用成功 task={task} model={cfg['model']}")
    return content


def mask_api_key(key: str) -> str:
    """API Key 脱敏展示（委托 utils.mask_secret，保持调用方兼容）。"""
    return utils.mask_secret(key)


def _http_error_detail(e: httpx.HTTPStatusError, url: str) -> str:
    """把服务商的错误响应体拼进错误信息，方便定位（如模型不存在、Key 无效）。"""
    try:
        body = (e.response.text or "").strip()[:300]
    except Exception:
        body = ""
    detail = f"HTTP {e.response.status_code} {url}"
    if body:
        detail += f" 返回：{body}"
    return detail


def ping(db, timeout: int = 60) -> str:
    """连通性测试：发送 'ping' 并期望简短回复。返回模型回复文本。"""
    content = chat(db, [{"role": "user", "content": "ping"}], task="ping",
                 json_mode=False, timeout=timeout)
    return (content or "").strip()


def list_models(db, base_url: str | None = None, api_key: str | None = None,
                timeout: int = 30) -> list[str]:
    """调用 OpenAI 兼容的 /models 接口，返回模型 id 列表（排序去重）。

    base_url / api_key 缺省时用已保存的配置。失败抛 LlmError（携带真实原因）。
    """
    cfg = get_llm_config(db)
    base = (base_url or cfg["base_url"] or "").rstrip("/")
    key = api_key if api_key is not None else cfg["api_key"]
    if not base:
        raise LlmError("未配置 Base URL")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        with httpx.Client(timeout=timeout, headers=headers) as client:
            resp = client.get(f"{base}/models")
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except httpx.HTTPStatusError as e:
        raise LlmError(_http_error_detail(e, f"{base}/models")) from e
    except Exception as e:
        raise LlmError(f"{type(e).__name__}: {e}") from e
    ids = [d.get("id") for d in data
              if isinstance(d, dict) and isinstance(d.get("id"), str) and d.get("id")]
    if not ids:
        raise LlmError("接口返回成功，但模型列表为空")
    utils.log_event(db, "llm", "INFO", f"获取模型列表成功：{len(ids)} 个模型")
    return sorted(set(ids))


def fallback_queries(profile: dict) -> list[str]:
    """降级检索词：用 keywords / field / methods 拼接生成查询（LLM 不可用时使用）。

    画像完全为空时返回 []，由调用方决定跳过该用户（不再用宽泛词硬搜）。
    """
    keywords = [k for k in (profile.get("keywords") or []) if k]
    fallback = keywords[:4]
    for key in ("research_direction", "field", "methods"):
        if profile.get(key):
            fallback.append(profile[key])
    fallback.extend(profile.get("discipline_names") or [])
    return [q.strip() for q in fallback if q and q.strip()][:6]


def gen_queries(db, profile: dict) -> list[str]:
    """根据用户画像生成 3-6 个英文检索词。

    LLM 未配置时自动降级为关键词拼接；LLM 调用失败时抛 LlmError（由调用方决定降级）。
    """
    if not is_configured(db):
        utils.log_event(db, "llm", "WARNING", "LLM 未配置，使用关键词拼接生成检索词")
        return fallback_queries(profile)
    keywords = [k for k in (profile.get("keywords") or []) if k]
    discipline_names = ", ".join(profile.get("discipline_names") or [])
    user_prompt = (
        "用户研究档案：\n"
        f"- 学科：{discipline_names}\n"
        f"- 研究方向：{profile.get('research_direction', '')}\n"
        f"- 研究领域：{profile.get('field', '')}\n"
        f"- 当前研究问题：{profile.get('research_problem', '')}\n"
        f"- 关注方法：{profile.get('methods', '')}\n"
        f"- 关键词：{', '.join(keywords)}\n"
        f"- 关注会议/期刊：{', '.join(profile.get('venues') or [])}\n\n"
        "请生成 3-6 个英文检索关键词/短语，用于在学术数据库中检索最近一周的相关论文。\n"
        "要求：覆盖核心概念与方法；每个查询词简洁（2-6 个英文单词）；避免过于宽泛。\n"
        '只输出 JSON：{"queries": ["...", "..."]}'
    )
    content = chat(db,
                   [{"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}],
                   task="gen_queries")
    data = _extract_json(content)
    queries = [q.strip() for q in data.get("queries", [])
               if isinstance(q, str) and q.strip()]
    if not queries:
        raise LlmError("模型未返回有效查询词")
    return queries[:6]


def _keyword_overlap_score(profile: dict, title: str, abstract: str) -> tuple[float, str]:
    """降级打分：关键词重叠度。返回 (score 0-10, reason_zh)。"""
    terms: list[str] = []
    for raw in list(profile.get("keywords") or []) + [profile.get("field", ""),
                                                       profile.get("methods", "")]:
        terms.extend(re.findall(r"[a-z0-9]+", (raw or "").lower()))
    terms = [t for t in terms if len(t) > 2]
    text = f"{title or ''} {abstract or ''}".lower()
    hits = sum(text.count(t) for t in set(terms))
    score = float(min(10, hits))
    return score, f"关键词命中 {hits} 次（未配置 LLM，仅供参考）"


def filter_papers_keyword(profile: dict, candidates: list[dict]) -> list[dict]:
    """降级打分：关键词重叠度，不依赖 LLM 与数据库。

    供 pipeline 在 LLM 调用失败时兜底，保证服务商抖动时周报仍能生成。
    返回 [{id, score, reason_zh}]。"""
    results = []
    for c in candidates:
        score, reason = _keyword_overlap_score(profile, c.get("title", ""),
                                               c.get("abstract", ""))
        results.append({"id": c["id"], "score": score, "reason_zh": reason})
    return results


def filter_papers(db, profile: dict, candidates: list[dict]) -> list[dict]:
    """对候选论文逐篇打分（0-10），返回 [{id, score, reason_zh}]。

    candidates: [{id, title, abstract, venue, date}]，每批最多 20 篇（调用方分批）。
    LLM 未配置时降级为关键词重叠度打分。
    """
    if not candidates:
        return []
    if not is_configured(db):
        utils.log_event(db, "llm", "WARNING", "LLM 未配置，使用关键词重叠度为候选论文打分")
        return filter_papers_keyword(profile, candidates)
    lines = []
    for c in candidates:
        abstract = (c.get("abstract") or "")[:800]
        lines.append(
            f"- id={c['id']} | 标题：{c.get('title', '')} | "
            f"会议/期刊：{c.get('venue', '')} | 日期：{c.get('date', '')}\n"
            f"  摘要：{abstract}"
        )
    user_prompt = (
        "用户研究档案：\n"
        f"- 学科：{', '.join(profile.get('discipline_names') or [])}\n"
        f"- 研究方向：{profile.get('research_direction', '')}\n"
        f"- 研究领域：{profile.get('field', '')}\n"
        f"- 当前研究问题：{profile.get('research_problem', '')}\n"
        f"- 关注方法：{profile.get('methods', '')}\n"
        f"- 关键词：{', '.join(profile.get('keywords') or [])}\n\n"
        f"候选论文（共 {len(candidates)} 篇）：\n" + "\n".join(lines) + "\n\n"
        "请评估每篇论文与用户研究问题的相关性：score 0-10（10=高度相关），"
        "并用中文一句话说明理由。\n"
        '只输出 JSON：{"results": [{"id": "候选id", "score": 8, "reason_zh": "..."}]}'
    )
    content = chat(db,
                   [{"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}],
                   task="filter_papers")
    data = _extract_json(content)
    results = []
    for r in data.get("results", []):
        try:
            results.append({
                "id": r["id"],
                "score": float(r.get("score", 0)),
                "reason_zh": str(r.get("reason_zh", "")),
            })
        except Exception:
            continue
    return results


def summarize(db, paper: dict, profile: dict) -> dict:
    """生成中文标题 / 中文摘要 / 核心创新点 / 推荐理由。

    仅基于给定的论文信息分析，不虚构结论。
    LLM 未配置时 zh 字段留空并标注"（未配置 LLM，摘要待补充）"。
    返回 {"zh_title", "zh_abstract", "innovations", "recommend_reason"}。
    """
    if not is_configured(db):
        utils.log_event(db, "llm", "WARNING", "LLM 未配置，论文中文摘要留空待补充")
        return {
            "zh_title": "",
            "zh_abstract": "（未配置 LLM，摘要待补充）",
            "innovations": [],
            "recommend_reason": "（未配置 LLM，推荐理由待补充）",
        }
    user_prompt = (
        "用户研究档案：\n"
        f"- 研究领域：{profile.get('field', '')}\n"
        f"- 当前研究问题：{profile.get('research_problem', '')}\n"
        f"- 关注方法：{profile.get('methods', '')}\n\n"
        "论文信息：\n"
        f"- 标题：{paper.get('title', '')}\n"
        f"- 作者：{', '.join(paper.get('authors', [])[:8])}\n"
        f"- 会议/期刊：{paper.get('venue', '')}\n"
        f"- 摘要：{(paper.get('abstract') or '')[:2000]}\n\n"
        "请输出 JSON（仅基于以上信息分析，不要编造论文中没有的结论）：\n"
        "{\n"
        '  "zh_title": "中文标题翻译",\n'
        '  "zh_abstract": "200-300 字中文摘要",\n'
        '  "innovations": ["核心创新点1", "核心创新点2", "核心创新点3"],\n'
        '  "recommend_reason": "为什么推荐给该用户（结合其研究问题），中文，100 字以内"\n'
        "}"
    )
    content = chat(db,
                   [{"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}],
                   task="summarize")
    data = _extract_json(content)
    innovations = data.get("innovations", [])
    if isinstance(innovations, str):
        innovations = [innovations]
    return {
        "zh_title": str(data.get("zh_title", "")),
        "zh_abstract": str(data.get("zh_abstract", "")),
        "innovations": [str(x) for x in innovations if x][:6],
        "recommend_reason": str(data.get("recommend_reason", "")),
    }


def digest_sections(db, profile: dict, papers: list[dict]) -> dict:
    """生成周报的【本周研究动态】与【本周研究启发】。

    LLM 未配置时使用通用模板。返回 {"overview_zh", "inspiration_zh"}。
    """
    if not is_configured(db):
        utils.log_event(db, "llm", "WARNING", "LLM 未配置，周报动态与启发使用通用模板")
        return {
            "overview_zh": (f"本周共检索到 {len(papers)} 篇相关论文"
                            "（未配置 LLM，详细研究动态总结待补充）。"),
            "inspiration_zh": ("（未配置 LLM，研究启发待补充）建议先通读本周推荐论文的摘要，"
                               "关注与您当前研究问题直接相关的方法与实验结论。"),
        }
    lines = []
    for p in papers:
        lines.append(
            f"- {p.get('title', '')}（{p.get('venue', '')}）\n"
            f"  创新点：{'；'.join(p.get('innovations', [])[:3])}\n"
            f"  推荐理由：{p.get('recommend_reason', '')}"
        )
    user_prompt = (
        "用户研究档案：\n"
        f"- 研究领域：{profile.get('field', '')}\n"
        f"- 当前研究问题：{profile.get('research_problem', '')}\n"
        f"- 关注方法：{profile.get('methods', '')}\n\n"
        "本周推荐论文：\n" + ("\n".join(lines) if lines else "（本周暂无推荐论文）") + "\n\n"
        "请输出 JSON：\n"
        "{\n"
        '  "overview_zh": "本周研究动态总结：相关领域出现了哪些值得关注的研究方向，200 字左右",\n'
        '  "inspiration_zh": "结合用户的当前研究问题，这些论文可能带来的研究启发，150 字左右"\n'
        "}"
    )
    content = chat(db,
                   [{"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}],
                   task="digest_sections")
    data = _extract_json(content)
    return {
        "overview_zh": str(data.get("overview_zh", "")),
        "inspiration_zh": str(data.get("inspiration_zh", "")),
    }
