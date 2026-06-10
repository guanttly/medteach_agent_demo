"""教学平台适配器（工具箱网关）：决定走真实接口还是 Mock，并做形状转换。

DEMO_MODE:
- mock   : 全部使用本地演示数据
- real   : 仅调用真实教学平台接口（失败直接报错）
- hybrid : 优先真实接口，失败自动回退 Mock（推荐展厅使用）

真实接口统一经 `_api(service, method, path, ...)` 调用，自动：
- 附带鉴权头（Authorization + platId，见 AuthClient）
- 解析 ResultBean（{state,errorCode,message,data}），失败抛异常
- 遇 401/无效登录刷新 token 重试一次

写操作（创建/下发考试）默认禁用（TEACHING_PLATFORM_ALLOW_WRITE=false），
避免演示在真实平台产生脏数据；hybrid 下会回退 Mock。
"""
from __future__ import annotations

import os
from typing import Any, Callable

from . import mock_client, transformers
from .auth_client import AuthClient

SERVICE_EXAM = "riemanExam"
SERVICE_BASE = "riemanBase"
SERVICE_EDU = "riemanEdu"


def _wrap(data: Any) -> dict[str, Any]:
    return {"ok": True, "fallback": False, "data": data, "error": None}


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


class EmptyData(Exception):
    """真实接口**可达但无可用数据**（平台暂无内容 / 统计为空）。

    与「真实接口不可用（网络/鉴权/平台报错）」区分开：这不是故障，
    不应展示成「真实接口不可用」，而是诚实提示「平台暂无数据，展示示例」。
    """


class TeachingPlatformClient:
    def __init__(self, mode: str | None = None) -> None:
        self.mode = (mode or os.getenv("DEMO_MODE", "hybrid")).lower()
        self._auth = AuthClient()
        self.base_url = self._auth.base_url
        self.verify_ssl = self._auth.verify_ssl
        self.timeout = self._auth.timeout
        self.trust_env = self._auth.trust_env
        self.max_retries = self._auth.max_retries
        self.allow_write = _truthy(os.getenv("TEACHING_PLATFORM_ALLOW_WRITE", "false"))
        # 可选：把「最近考试」类查询（试卷预览/答题进度/成绩分析）钉到一场已知有数据的考试，
        # 避免默认取到「尚未结束 / 无成绩」的考试。留空走自动定位。
        self.demo_exam_id = os.getenv("TEACHING_PLATFORM_DEMO_EXAM_ID", "").strip() or None

    @staticmethod
    def _dry_run(endpoint: str, payload: Any, note: str) -> dict[str, Any]:
        """写操作未启用时的「演练预览」：只回显**将要发送**的请求，不真正写平台。

        让演示者能安全验证写操作的请求构造（端点 + 报文），而不在真实平台产生脏数据。
        """
        return {
            "ok": True, "fallback": False, "dry_run": True, "data": {
                "dry_run": True,
                "endpoint": endpoint,
                "payload": payload,
                "note": note,
            },
            "error": None,
        }

    # ------------------------------------------------------------------ #
    # 底层真实调用：URL = {base}/{service}{path}
    # ------------------------------------------------------------------ #
    def _api(
        self,
        service: str,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        if not self._auth.configured():
            raise RuntimeError("教学平台未配置凭据，回退 Mock。")
        import httpx  # 延迟导入：缺少 httpx 时真实调用抛错→hybrid 回退 Mock

        url = f"{self.base_url}/{service.strip('/')}{path}"
        # trust_env=False 默认绕过系统代理直连，去掉一层间歇握手失败。
        with httpx.Client(
            timeout=self.timeout, verify=self.verify_ssl, trust_env=self.trust_env
        ) as client:
            last_body: Any = None
            last_exc: Exception | None = None
            # 鉴权重试（2 次）× 瞬时网络重试（max_retries+1 次）。
            for attempt in range(2):
                headers = self._auth.auth_headers(force_refresh=(attempt == 1))
                for net_try in range(self.max_retries + 1):
                    try:
                        resp = client.request(
                            method.upper(), url, json=json_body, params=params, headers=headers
                        )
                        break
                    except (httpx.TransportError, OSError) as exc:
                        # SSL UNEXPECTED_EOF / ConnectTimeout / ReadTimeout 等瞬时抖动→重试
                        last_exc = exc
                        if net_try >= self.max_retries:
                            raise RuntimeError(
                                f"{path} 网络异常（已重试 {net_try} 次）：{exc}"
                            ) from exc
                resp.raise_for_status()
                body = resp.json()
                last_body = body
                if isinstance(body, dict) and body.get("errorCode") == 401:
                    self._auth.invalidate()
                    continue  # token 失效，刷新后重试一次
                if isinstance(body, dict) and body.get("state") is False:
                    raise RuntimeError(
                        f"{path} 调用失败：{body.get('message') or body.get('errorCode')}"
                    )
                return body.get("data") if isinstance(body, dict) else body
        raise RuntimeError(
            f"{path} 鉴权失败：{(last_body or {}).get('message') if isinstance(last_body, dict) else last_body}"
        )

    # ------------------------------------------------------------------ #
    # 统一分发：mock / real / hybrid（real_fn 返回已转换的 demo 形状 data）
    # ------------------------------------------------------------------ #
    def _dispatch(
        self,
        name: str,
        real_fn: Callable[[], Any],
        mock_fn: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        if self.mode == "mock":
            return mock_fn()
        try:
            return _wrap(real_fn())
        except EmptyData as empty:  # 接口可达但平台无内容：诚实提示，非「不可用」
            note = str(empty) or "平台暂无数据"
            if self.mode == "real":
                # real 模式不掺 Mock：返回「真实但为空」，由上层友好展示。
                return {
                    "ok": True, "fallback": False, "data": None,
                    "empty": True, "error": {"type": "empty", "message": note},
                }
            result = dict(mock_fn())
            result["fallback"] = True
            result["empty"] = True
            result["error"] = {"type": "empty", "message": f"{note}，已展示示例数据。"}
            return result
        except Exception as exc:  # noqa: BLE001 - 演示需吞掉所有真实接口异常
            if self.mode == "real":
                return {
                    "ok": False,
                    "fallback": False,
                    "data": None,
                    "error": {"type": "real_api_failed", "message": str(exc)},
                }
            result = dict(mock_fn())
            result["fallback"] = True
            result["error"] = {
                "type": "real_api_failed",
                "message": f"{name} 真实接口暂不可用，已切换演示数据：{exc}",
            }
            return result

    # ------------------------------------------------------------------ #
    # 内部：取最近一场考试（供「最近考试」类查询自动定位 examId）
    # ------------------------------------------------------------------ #
    def _latest_exam(self, prefer_finished: bool = False) -> dict[str, Any]:
        page = self._api(
            SERVICE_EXAM, "POST", "/exam/my/create/list",
            json_body={"pageNum": 1, "pageSize": 20},
        )
        exams = transformers.exams_from_pageinfo(page).get("exams", [])
        if not exams:
            raise EmptyData("平台暂无考试记录")
        if prefer_finished:
            finished = [e for e in exams if e.get("status") in ("已结束", "已公布")]
            if finished:
                return finished[0]
        return exams[0]

    # ================================================================== #
    # 既有 7 大能力（保持签名；黄金路径相关写操作受 ALLOW_WRITE 保护）
    # ================================================================== #
    def get_present_students(self) -> dict[str, Any]:
        def real() -> Any:
            page = self._api(
                SERVICE_BASE, "POST", "/department/in/user/search",
                json_body={"pageNum": 1, "pageSize": 50},
            )
            result = transformers.students_from_pageinfo(page, group_name="现场在科学员")
            if not result["students"]:
                raise EmptyData("当前在科暂无学员")
            return result

        return self._dispatch("get_present_students", real, mock_client.get_present_students)

    def create_exam_draft(self, plan: dict[str, Any] | None = None) -> dict[str, Any]:
        dto = mock_client.build_exam_save_dto(plan)
        if self.mode != "mock" and not self.allow_write:
            return self._dry_run(
                "POST /riemanExam/exam/add", dto,
                "写操作未启用（TEACHING_PLATFORM_ALLOW_WRITE=false）。以上为将要提交的考试草稿报文，"
                "可据此校验请求构造；启用写操作后即真实创建。",
            )

        def real() -> Any:
            exam_id = self._api(SERVICE_EXAM, "POST", "/exam/add", json_body=dto)
            return {"exam_id": exam_id, "status": "draft_created"}

        return self._dispatch("create_exam_draft", real, mock_client.create_exam_draft)

    def get_exam_preview(self, exam_id: Any = None) -> dict[str, Any]:
        def real() -> Any:
            eid = exam_id or self.demo_exam_id or self._latest_exam().get("exam_id")
            detail = self._api(SERVICE_EXAM, "GET", "/exam/detail", params={"examId": eid})
            if not detail:
                raise EmptyData("未取到考试详情")
            return detail

        return self._dispatch("get_exam_preview", real, mock_client.get_exam_preview)

    def publish_exam(self, exam_id: Any = None) -> dict[str, Any]:
        if self.mode != "mock" and not self.allow_write:
            return self._dry_run(
                "GET /riemanExam/exam/pub?examId=<考试ID>",
                {"examId": exam_id or self.demo_exam_id or "<最近一场考试>"},
                "写操作未启用（TEACHING_PLATFORM_ALLOW_WRITE=false）。以上为将要调用的下发端点，"
                "可据此校验；启用写操作后即真实下发。",
            )

        def real() -> Any:
            eid = exam_id or self.demo_exam_id or self._latest_exam().get("exam_id")
            self._api(SERVICE_EXAM, "GET", "/exam/pub", params={"examId": eid})
            return {"exam_id": eid, "status": "published"}

        return self._dispatch("publish_exam", real, mock_client.publish_exam)

    def get_exam_progress(self, exam_id: Any = None) -> dict[str, Any]:
        def real() -> Any:
            eid = exam_id or self.demo_exam_id or self._latest_exam().get("exam_id")
            raw = self._api(
                SERVICE_EXAM, "POST", "/exam/my/create/look/student",
                json_body={"examId": eid, "finishTag": -1, "pageNum": 1, "pageSize": 1},
            )
            return transformers.progress_from_look(raw)

        return self._dispatch("get_exam_progress", real, mock_client.get_exam_progress)

    def get_exam_result(self, exam_id: Any = None) -> dict[str, Any]:
        def real() -> Any:
            if exam_id is not None:
                exam = {"exam_id": exam_id, "name": ""}
            elif self.demo_exam_id:
                exam = {"exam_id": self.demo_exam_id, "name": ""}
            else:
                exam = self._latest_exam(prefer_finished=True)
            eid = exam.get("exam_id")
            overview = self._api(
                SERVICE_EXAM, "GET", "/exam/my/create/list/result", params={"examId": eid}
            )
            try:
                scores = self._api(
                    SERVICE_EXAM, "POST", "/exam/my/create/list/scores",
                    json_body={"examId": eid, "pageNum": 1, "pageSize": 100},
                )
            except Exception:  # noqa: BLE001 - 成绩明细可选
                scores = None
            try:
                analysis = self._api(
                    SERVICE_EXAM, "GET", "/exam/my/create/list/scores/analy",
                    params={"examId": eid},
                )
            except Exception:  # noqa: BLE001 - 分析可选
                analysis = None
            result = transformers.exam_result_from_real(
                overview, scores, analysis,
                exam_id=eid, exam_name=str(exam.get("name") or ""),
            )
            # 真实成绩不可用于演示（无人交卷 / 平均分为 0 / 无成绩明细）→ 当作空数据，
            # 回退到统计完整的示例成绩，避免大屏出现「平均 0 分」这类失真画面。
            summary = result.get("summary") or {}
            if (
                int(summary.get("submitted") or 0) == 0
                or float(summary.get("average") or 0) <= 0
            ):
                raise EmptyData("该考试暂无可展示的成绩统计")
            return result

        return self._dispatch("get_exam_result", real, mock_client.get_exam_result)

    def recommend_cases(self) -> dict[str, Any]:
        def real() -> Any:
            page = self._api(
                SERVICE_EDU, "POST", "/train/case/list",
                json_body={"pageNum": 1, "pageSize": 8},
            )
            result = transformers.cases_from_pageinfo(page)
            if not result["cases"]:
                raise EmptyData("平台专题培训病例库暂为空")
            return result

        return self._dispatch("recommend_cases", real, mock_client.recommend_cases)

    # ================================================================== #
    # 新增业务线能力（只读，已对真实平台验证）
    # ================================================================== #
    def get_data_board(self) -> dict[str, Any]:
        def real() -> Any:
            exam_board = self._api(SERVICE_EXAM, "POST", "/stat/mngBoard", json_body={})
            try:
                edu_board = self._api(SERVICE_EDU, "POST", "/stat/mngBoard", json_body={})
            except Exception:  # noqa: BLE001 - 教学看板可选
                edu_board = None
            return transformers.data_board_from_real(exam_board, edu_board)

        return self._dispatch("get_data_board", real, mock_client.get_data_board)

    def search_students(
        self, keyword: str | None = None, page: int = 1, size: int = 20, scope: str = "in"
    ) -> dict[str, Any]:
        def real() -> Any:
            path = "/department/in/user/search" if scope == "in" else "/department/out/user/search"
            body: dict[str, Any] = {"pageNum": page, "pageSize": size}
            if keyword:
                body["keyword"] = keyword
            result = transformers.students_from_pageinfo(
                self._api(SERVICE_BASE, "POST", path, json_body=body),
                group_name="在科学员" if scope == "in" else "学员名册",
            )
            if not result["students"]:
                raise EmptyData("未检索到匹配的学员")
            return result

        return self._dispatch("search_students", real, mock_client.get_student_roster)

    def list_exams(self, page: int = 1, size: int = 10) -> dict[str, Any]:
        def real() -> Any:
            result = transformers.exams_from_pageinfo(
                self._api(
                    SERVICE_EXAM, "POST", "/exam/my/create/list",
                    json_body={"pageNum": page, "pageSize": size},
                )
            )
            if not result["exams"]:
                raise EmptyData("平台暂无考试")
            return result

        return self._dispatch("list_exams", real, mock_client.list_exams)

    def list_questions(self, page: int = 1, size: int = 10) -> dict[str, Any]:
        def real() -> Any:
            result = transformers.questions_from_pageinfo(
                self._api(
                    SERVICE_EXAM, "POST", "/question/all/list",
                    json_body={"pageNum": page, "pageSize": size},
                )
            )
            if not result["questions"]:
                raise EmptyData("题库暂无题目")
            return result

        return self._dispatch("list_questions", real, mock_client.list_questions)

    def list_teaching_plans(self, page: int = 1, size: int = 10) -> dict[str, Any]:
        def real() -> Any:
            result = transformers.teaching_plans_from_pageinfo(
                self._api(
                    SERVICE_EDU, "POST", "/education/plan/search",
                    json_body={"pageNum": page, "pageSize": size},
                )
            )
            if not result["plans"]:
                raise EmptyData("近期暂无教学计划")
            return result

        return self._dispatch("list_teaching_plans", real, mock_client.list_teaching_plans)
