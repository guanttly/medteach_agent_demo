"""教学平台工具箱桥接（Demo Shell → medteach-agent-core）。

让后端编排器复用 agent-core 里**同一套真实工具箱**（TeachingPlatformClient），
避免在后端重复实现平台对接。要点：

- 工具箱是同步 httpx 实现，这里统一用 ``asyncio.to_thread`` 包装，避免阻塞事件循环。
- 凭据通过 backend/.env 注入 os.environ（config.py 的 load_dotenv 已完成），
  工具箱按 DEMO_MODE=hybrid 真实优先、失败自动回退 Mock，返回 ``{ok,fallback,data,error}``。
- 任何导入/调用异常都向上抛，由编排器统一兜底，保证展厅永不翻车。
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Any

from .config import settings

logger = logging.getLogger("platform_bridge")

_VALID_MODES = ("mock", "real", "hybrid")

_client: Any = None
# 运行时模式覆盖（控制台 / 工具页切换）；None = 沿用 .env 的 DEMO_MODE。
_mode_override: str | None = None

# ---- 预热缓存：把慢且间歇抖动的真实调用结果缓存起来，演示时秒开且稳定 ---- #
# 真实平台单次 1.5~20s 且偶发 SSL 抖动；演示前一键预热，现场命中缓存即时返回真数据。
_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_TTL = float(os.getenv("TEACHING_PLATFORM_CACHE_TTL", "600"))


def _get_client() -> Any:
    """惰性创建工具箱单例（首次调用时把 agent-core 加入 sys.path）。"""
    global _client
    if _client is None:
        core_dir = str(settings.CLAUDE_CORE_DIR)
        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)
        from adapter.teaching_platform_client import TeachingPlatformClient  # noqa: E402

        _client = TeachingPlatformClient(mode=_mode_override)
        logger.info(
            "teaching platform toolbox ready: mode=%s base=%s",
            getattr(_client, "mode", "?"),
            getattr(_client, "base_url", "?"),
        )
    return _client


def current_mode() -> str:
    """当前工具箱真实/Mock 模式。"""
    if _client is not None:
        return _client.mode
    return _mode_override or settings.DEMO_MODE


def set_mode(mode: str) -> str:
    """切换工具箱模式：real=仅真实接口、mock=全本地、hybrid=优先真实失败回退。

    单例已创建时立即生效；未创建时记录为初始模式。返回最终生效的模式。
    """
    global _mode_override
    norm = (mode or "").strip().lower()
    if norm not in _VALID_MODES:
        return current_mode()
    _mode_override = norm
    if _client is not None:
        _client.mode = norm
    _CACHE.clear()  # 切换模式后旧缓存（real/mock 数据）失效
    logger.info("teaching platform toolbox mode -> %s", norm)
    return norm


async def _call(method: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    client = _get_client()
    fn = getattr(client, method)
    return await asyncio.to_thread(fn, *args, **kwargs)


# ---- 各业务模块只读查询封装（语音业务模块直接复用）---- #
async def get_data_board() -> dict[str, Any]:
    return await _call("get_data_board")


async def get_present_students() -> dict[str, Any]:
    return await _call("get_present_students")


async def search_students(
    keyword: str | None = None, page: int = 1, size: int = 20, scope: str = "in"
) -> dict[str, Any]:
    return await _call("search_students", keyword, page, size, scope)


async def list_exams(page: int = 1, size: int = 10) -> dict[str, Any]:
    return await _call("list_exams", page, size)


async def list_questions(page: int = 1, size: int = 10) -> dict[str, Any]:
    return await _call("list_questions", page, size)


async def list_teaching_plans(page: int = 1, size: int = 10) -> dict[str, Any]:
    return await _call("list_teaching_plans", page, size)


async def get_exam_result(exam_id: Any = None) -> dict[str, Any]:
    return await _call("get_exam_result", exam_id)


async def recommend_cases() -> dict[str, Any]:
    return await _call("recommend_cases")


async def get_exam_preview(exam_id: Any = None) -> dict[str, Any]:
    return await _call("get_exam_preview", exam_id)


async def get_exam_progress(exam_id: Any = None) -> dict[str, Any]:
    return await _call("get_exam_progress", exam_id)


async def create_exam_draft(plan: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _call("create_exam_draft", plan)


async def publish_exam(exam_id: Any = None) -> dict[str, Any]:
    return await _call("publish_exam", exam_id)


# ====================================================================== #
# 工具箱清单：把 TeachingPlatformClient 的真实能力抽成「可点击测试」的业务场景。
# 前端工具验证页据此渲染按钮，点击即直连真实教学平台调用对应 API。
# ====================================================================== #
TOOL_REGISTRY: list[dict[str, Any]] = [
    {
        "key": "get_data_board", "name": "教学数据看板", "skill": "data_board",
        "module": "data_board", "category": "read", "write": False,
        "summary": "拉取平台考试 / 试卷 / 题目总量与教学活动概览。",
        "scenario": "看一下数据看板 · 平台一共有多少考试",
        "api": "POST /riemanExam/stat/mngBoard", "params": [],
    },
    {
        "key": "get_present_students", "name": "现场学员名册", "skill": "student_management",
        "module": "list_students", "category": "read", "write": False,
        "summary": "查询当前在科的现场学员名单。",
        "scenario": "现场有哪些学员 · 在科学员名单",
        "api": "POST /riemanBase/department/in/user/search", "params": [],
    },
    {
        "key": "search_students", "name": "学员检索", "skill": "student_management",
        "module": "list_students", "category": "read", "write": False,
        "summary": "按关键字检索学员（在科 / 全部）。",
        "scenario": "查一下某位学员",
        "api": "POST /riemanBase/department/{in|out}/user/search",
        "params": [
            {"name": "keyword", "type": "string", "default": "马", "label": "关键字"},
            {"name": "scope", "type": "string", "default": "in", "label": "范围 in/out"},
            {"name": "page", "type": "number", "default": 1, "label": "页码"},
            {"name": "size", "type": "number", "default": 20, "label": "每页数"},
        ],
    },
    {
        "key": "list_exams", "name": "考试列表", "skill": "exam_monitoring",
        "module": "list_exams", "category": "read", "write": False,
        "summary": "拉取我创建的考试列表与状态。",
        "scenario": "现在有哪些考试 · 考试进度",
        "api": "POST /riemanExam/exam/my/create/list",
        "params": [
            {"name": "page", "type": "number", "default": 1, "label": "页码"},
            {"name": "size", "type": "number", "default": 10, "label": "每页数"},
        ],
    },
    {
        "key": "get_exam_preview", "name": "试卷预览", "skill": "exam_arrange",
        "module": "exam_preview", "category": "read", "write": False,
        "summary": "查看最近一场（或指定）考试的试卷详情。",
        "scenario": "看下这套试卷",
        "api": "GET /riemanExam/exam/detail",
        "params": [
            {"name": "exam_id", "type": "string", "default": "", "label": "考试ID（留空取最近）"},
        ],
    },
    {
        "key": "get_exam_progress", "name": "答题进度", "skill": "exam_monitoring",
        "module": "progress", "category": "read", "write": False,
        "summary": "查看最近一场考试的进入 / 答题 / 交卷进度。",
        "scenario": "现在多少人交卷了",
        "api": "POST /riemanExam/exam/my/create/look/student",
        "params": [
            {"name": "exam_id", "type": "string", "default": "", "label": "考试ID（留空取最近）"},
        ],
    },
    {
        "key": "get_exam_result", "name": "阅卷成绩分析", "skill": "exam_grading",
        "module": "show_grading", "category": "read", "write": False,
        "summary": "拉取最近已结束考试的平均分 / 及格率 / 薄弱点。",
        "scenario": "看一下考试成绩 · 平均分多少",
        "api": "GET /riemanExam/exam/my/create/list/result",
        "params": [
            {"name": "exam_id", "type": "string", "default": "", "label": "考试ID（留空取最近已结束）"},
        ],
    },
    {
        "key": "list_questions", "name": "题库", "skill": "question_bank",
        "module": "list_questions", "category": "read", "write": False,
        "summary": "拉取题库题目与题型分布。",
        "scenario": "题库里有哪些题",
        "api": "POST /riemanExam/question/all/list",
        "params": [
            {"name": "page", "type": "number", "default": 1, "label": "页码"},
            {"name": "size", "type": "number", "default": 10, "label": "每页数"},
        ],
    },
    {
        "key": "list_teaching_plans", "name": "教学计划", "skill": "teaching_plan",
        "module": "list_teaching", "category": "read", "write": False,
        "summary": "拉取近期教学计划 / 阅片排课。",
        "scenario": "最近有哪些教学计划",
        "api": "POST /riemanEdu/education/plan/search",
        "params": [
            {"name": "page", "type": "number", "default": 1, "label": "页码"},
            {"name": "size", "type": "number", "default": 10, "label": "每页数"},
        ],
    },
    {
        "key": "recommend_cases", "name": "复训病例推荐", "skill": "case_recommend",
        "module": "recommend_cases", "category": "read", "write": False,
        "summary": "基于专题培训病例库推荐复训病例。",
        "scenario": "推荐几个复训病例",
        "api": "POST /riemanEdu/train/case/list", "params": [],
    },
    {
        "key": "create_exam_draft", "name": "创建考试草稿", "skill": "exam_arrange",
        "module": "exam_draft", "category": "write", "write": True,
        "summary": "按方案在平台创建考试草稿（写操作，默认禁用）。",
        "scenario": "金线：确认方案后创建考试",
        "api": "POST /riemanExam/exam/add", "params": [],
    },
    {
        "key": "publish_exam", "name": "下发考试", "skill": "exam_arrange",
        "module": "publish_info", "category": "write", "write": True,
        "summary": "下发 / 发布考试，开放答题入口（写操作，默认禁用）。",
        "scenario": "金线：下发考试",
        "api": "GET /riemanExam/exam/pub",
        "params": [
            {"name": "exam_id", "type": "string", "default": "", "label": "考试ID（留空取最近）"},
        ],
    },
]

_TOOL_BY_KEY = {t["key"]: t for t in TOOL_REGISTRY}


def list_tools() -> list[dict[str, Any]]:
    return [dict(t) for t in TOOL_REGISTRY]


def _coerce_params(spec: dict[str, Any], raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    kwargs: dict[str, Any] = {}
    for p in spec["params"]:
        name = p["name"]
        provided = raw.get(name)
        if provided not in (None, ""):
            if p.get("type") == "number":
                try:
                    kwargs[name] = int(provided)
                except (TypeError, ValueError):
                    kwargs[name] = p.get("default")
            else:
                kwargs[name] = provided
        elif p.get("type") == "number":
            kwargs[name] = p.get("default")
        elif p.get("default"):
            kwargs[name] = p["default"]
    return kwargs


async def invoke_tool(
    key: str, params: dict[str, Any] | None = None, mode: str | None = None
) -> dict[str, Any]:
    """直接调用某个工具（工具验证页用）。返回 {ok,fallback,data,error,mode,elapsed_ms,tool}。"""
    spec = _TOOL_BY_KEY.get(key)
    if spec is None:
        return {
            "ok": False, "fallback": False, "data": None, "tool": key,
            "mode": current_mode(), "elapsed_ms": 0.0,
            "error": {"type": "unknown_tool", "message": f"未知工具：{key}"},
        }
    kwargs = _coerce_params(spec, params)
    client = _get_client()
    prev_mode = client.mode
    use_mode = (mode or "").strip().lower()
    if use_mode in _VALID_MODES:
        client.mode = use_mode
    started = time.time()
    effective_mode = client.mode
    try:
        fn = getattr(client, spec["key"])
        res = await asyncio.to_thread(fn, **kwargs)
    except Exception as exc:  # noqa: BLE001 - 演示需吞掉所有真实接口异常
        res = {
            "ok": False, "fallback": False, "data": None,
            "error": {"type": "invoke_failed", "message": str(exc)},
        }
    finally:
        client.mode = prev_mode
    elapsed = round((time.time() - started) * 1000.0, 1)
    out: dict[str, Any] = (
        dict(res) if isinstance(res, dict)
        else {"ok": True, "fallback": False, "data": res, "error": None}
    )
    out.setdefault("ok", False)
    out.setdefault("fallback", False)
    out.setdefault("data", None)
    out.setdefault("error", None)
    out.setdefault("dry_run", False)
    out.setdefault("empty", False)
    out["mode"] = effective_mode
    out["elapsed_ms"] = elapsed
    out["tool"] = key
    return out


def platform_status() -> dict[str, Any]:
    """平台接入状态（供工具页 / 控制台展示）。"""
    client = _get_client()
    auth = getattr(client, "_auth", None)
    return {
        "base_url": getattr(client, "base_url", ""),
        "mode": client.mode,
        "configured": bool(auth.configured()) if auth else False,
        "allow_write": bool(getattr(client, "allow_write", False)),
        "verify_ssl": bool(getattr(client, "verify_ssl", False)),
        "trust_env": bool(getattr(client, "trust_env", True)),
        "llm_configured": settings.llm_configured,
        "llm_provider": settings.llm_provider_label,
        "tool_count": len(TOOL_REGISTRY),
        "cache": warm_status(),
    }


# ====================================================================== #
# 预热缓存：演示前一键拉取所有只读模块，现场命中缓存即时返回真数据，
# 规避真实平台的高延迟与间歇抖动。缓存按「业务模块意图」键存。
# ====================================================================== #
# 业务模块意图 → 取数方法（与 interaction/business.py 的语音模块一一对应）。
READ_MODULES: dict[str, Any] = {
    "data_board": get_data_board,
    "list_students": get_present_students,
    "list_exams": list_exams,
    "show_grading": get_exam_result,
    "list_questions": list_questions,
    "recommend_cases": recommend_cases,
    "list_teaching": list_teaching_plans,
}

_MODULE_LABELS = {
    "data_board": "数据看板", "list_students": "现场学员", "list_exams": "考试列表",
    "show_grading": "成绩分析", "list_questions": "题库", "recommend_cases": "复训病例",
    "list_teaching": "教学计划",
}


def _cache_fresh(entry: dict[str, Any] | None, ttl: float) -> bool:
    return bool(entry) and (time.time() - entry["ts"]) < ttl and entry.get("mode") == current_mode()


async def cached_read(
    module: str, fn: Any | None = None, *, ttl: float | None = None, force: bool = False
) -> dict[str, Any]:
    """读类业务取数（带缓存）：命中新鲜缓存即时返回，否则实时调用并回填。

    只缓存「成功」结果（ok=True）；失败不写缓存，下次仍会重试真实接口。
    语音业务查询走这里，把现场等待从十几秒降到 0，并避开间歇抖动。
    """
    fn = fn or READ_MODULES.get(module)
    if fn is None:
        return {"ok": False, "fallback": False, "data": None, "error": {"message": f"未知模块 {module}"}}
    eff_ttl = _CACHE_TTL if ttl is None else ttl
    entry = _CACHE.get(module)
    if not force and _cache_fresh(entry, eff_ttl):
        out = dict(entry["result"])
        out["cached"] = True
        out["cache_age_ms"] = round((time.time() - entry["ts"]) * 1000.0)
        return out
    res = await fn()
    if isinstance(res, dict) and res.get("ok"):
        _CACHE[module] = {"ts": time.time(), "result": dict(res), "mode": current_mode()}
    out = dict(res) if isinstance(res, dict) else {"ok": True, "data": res}
    out["cached"] = False
    return out


async def prewarm(modules: list[str] | None = None) -> dict[str, Any]:
    """一键预热：并发拉取所有（或指定）只读模块，回填缓存。

    返回每个模块的命中情况（真实 / 回退 / 空 / 失败 + 耗时），供工具页展示「预热体检」。
    """
    keys = [m for m in (modules or list(READ_MODULES)) if m in READ_MODULES]
    started = time.time()

    async def _one(m: str) -> dict[str, Any]:
        t0 = time.time()
        try:
            res = await cached_read(m, force=True)
        except Exception as exc:  # noqa: BLE001 - 预热需吞掉所有异常
            res = {"ok": False, "fallback": False, "empty": False, "error": {"message": str(exc)}}
        return {
            "module": m,
            "label": _MODULE_LABELS.get(m, m),
            "ok": bool(res.get("ok")),
            "fallback": bool(res.get("fallback")),
            "empty": bool(res.get("empty")),
            "error": (res.get("error") or {}).get("message") if res.get("error") else None,
            "elapsed_ms": round((time.time() - t0) * 1000.0, 1),
        }

    items = await asyncio.gather(*[_one(m) for m in keys])
    real_ok = sum(1 for i in items if i["ok"] and not i["fallback"])
    fallback = sum(1 for i in items if i["fallback"])
    failed = sum(1 for i in items if not i["ok"])
    return {
        "mode": current_mode(),
        "total": len(items),
        "real_ok": real_ok,
        "fallback": fallback,
        "failed": failed,
        "elapsed_ms": round((time.time() - started) * 1000.0, 1),
        "modules": items,
    }


def warm_status() -> dict[str, Any]:
    """当前缓存命中概况（供状态面板展示）。"""
    now = time.time()
    items = []
    for m in READ_MODULES:
        e = _CACHE.get(m)
        items.append({
            "module": m,
            "label": _MODULE_LABELS.get(m, m),
            "warm": _cache_fresh(e, _CACHE_TTL),
            "age_ms": round((now - e["ts"]) * 1000.0) if e else None,
            "fallback": bool(e["result"].get("fallback")) if e else None,
        })
    warm = sum(1 for i in items if i["warm"])
    return {"ttl_seconds": _CACHE_TTL, "warm_count": warm, "total": len(items), "modules": items}


def clear_cache() -> None:
    _CACHE.clear()


# ====================================================================== #
# 组合场景：把多个工具按真实演示顺序串成一条链，一键端到端验证，
# 让演示者在上台前确认「整段流程」都可达、不报错（而非只验证单个 Skill）。
# ====================================================================== #
SCENARIOS: list[dict[str, Any]] = [
    {
        "key": "post_exam_review", "name": "考后复盘闭环",
        "desc": "数据看板 → 考试列表 → 成绩分析 → 复训病例推荐，串起一次完整的考后讲解。",
        "steps": ["get_data_board", "list_exams", "get_exam_result", "recommend_cases"],
    },
    {
        "key": "live_monitor", "name": "现场监考",
        "desc": "现场学员 → 试卷预览 → 答题进度，覆盖开考到监考的实时播报。",
        "steps": ["get_present_students", "get_exam_preview", "get_exam_progress"],
    },
    {
        "key": "data_overview", "name": "教学数据总览",
        "desc": "数据看板 → 题库 → 教学计划，统计类大屏内容的可达性体检。",
        "steps": ["get_data_board", "list_questions", "list_teaching_plans"],
    },
    {
        "key": "golden_write_dryrun", "name": "金线写操作演练",
        "desc": "创建考试草稿 → 下发考试（写操作演练预览，不污染真实平台）。",
        "steps": ["create_exam_draft", "publish_exam"],
    },
]

_SCENARIO_BY_KEY = {s["key"]: s for s in SCENARIOS}


def list_scenarios() -> list[dict[str, Any]]:
    out = []
    for s in SCENARIOS:
        steps = [
            {"key": k, "name": (_TOOL_BY_KEY.get(k) or {}).get("name", k),
             "write": bool((_TOOL_BY_KEY.get(k) or {}).get("write"))}
            for k in s["steps"]
        ]
        out.append({"key": s["key"], "name": s["name"], "desc": s["desc"], "steps": steps})
    return out


async def run_scenario(key: str, mode: str | None = None) -> dict[str, Any]:
    """按顺序执行场景里的每个工具，汇总每步真实/回退/空/失败 + 总体结论。"""
    scenario = _SCENARIO_BY_KEY.get(key)
    if scenario is None:
        return {"ok": False, "key": key, "error": f"未知场景：{key}", "steps": []}
    started = time.time()
    steps_out: list[dict[str, Any]] = []
    for tool_key in scenario["steps"]:
        res = await invoke_tool(tool_key, None, mode)
        spec = _TOOL_BY_KEY.get(tool_key) or {}
        steps_out.append({
            "key": tool_key,
            "name": spec.get("name", tool_key),
            "skill": spec.get("skill"),
            "ok": bool(res.get("ok")),
            "fallback": bool(res.get("fallback")),
            "empty": bool(res.get("empty")),
            "dry_run": bool(res.get("dry_run")),
            "elapsed_ms": res.get("elapsed_ms"),
            "error": (res.get("error") or {}).get("message") if res.get("error") else None,
        })
    real_ok = sum(1 for s in steps_out if s["ok"] and not s["fallback"] and not s["dry_run"])
    reachable = all(s["ok"] for s in steps_out)  # 含回退/演练也算「链路通」
    return {
        "ok": reachable,
        "key": key,
        "name": scenario["name"],
        "mode": (mode or current_mode()),
        "real_ok": real_ok,
        "total": len(steps_out),
        "elapsed_ms": round((time.time() - started) * 1000.0, 1),
        "steps": steps_out,
    }
