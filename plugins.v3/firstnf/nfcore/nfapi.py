"""NextFind OpenAPI HTTP 适配器。

合同来源（2026-10-16 核对）：
1. **NextFind 官方智能体开发文档**（用户提供）：端点前缀 /api/openapi、
   鉴权头 X-API-Key、/resources/search（tmdb_id/media_type/season/episode）、
   /transfer（slug + target_folder）、/history（page/page_size）、
   /subscriptions/info（items[]，tmdb_id 为字符串）、/subscriptions/add、
   /media/fill_missing、/quota、/logs、/directories、/local_library/filter 等。
2. unisub 实测参考（nextfind-api-v3，2026-07-22）：响应字段级细节
   （parsed_episodes、video_resolution、is_slug_transferred、local_episodes 等）。
3. 目标实例已安装的 NextFindController 源码：调用方式交叉验证通过。

官方文档确认存在但本插件有意不使用的端点及理由见 ports.NextfindPort 文档字符串：
- GET /local_library/filter：仅返回 missing/error/duplicate 问题项，响应结构
  未明确，无法安全用作完成确认信号；
- POST /media/fill_missing：NF 侧补缺——按设计由 PT 承担后续追更；
- POST /subscriptions/add：NF 订阅由 MP 订阅主控，避免双轨追更。

网络层优先使用宿主 app.sdk.network.AsyncRequestUtils（HTTPX2），
导入失败时回退 requests，保证核心逻辑可在宿主外运行。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from .ports import NextfindPort


class NextfindError(Exception):
    """NF 调用失败，kind 用于编排层区分处理策略。"""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind  # network / http / api / timeout / config


def normalize_nf_base_url(base_url: str) -> str:
    """补全 NextFind OpenAPI 前缀。

    官方智能体开发文档约定接口前缀为 /api/openapi；用户常只填主机根地址，
    这里自动补全，避免配置遗漏导致 404。
    已含 /api/openapi（允许结尾斜杠）时原样返回（去尾斜杠）。
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return ""
    if not base.endswith("/api/openapi"):
        base = f"{base}/api/openapi"
    return base


class NextfindHttpAdapter(NextfindPort):
    """基于 OpenAPI 的 NF 适配器。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
    ) -> None:
        if not base_url or not api_key:
            raise NextfindError("config", "NF base_url/api_key 未配置")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    # ------------------------------------------------------------------ HTTP

    async def _request(
        self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """发起一次 API 请求并归一化响应。"""
        url = f"{self.base_url}{path}"
        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        try:
            payload = await self._do_request(method, url, params=params, body=body, headers=headers)
        except NextfindError:
            raise
        except Exception as error:  # 网络层异常归一
            raise NextfindError("network", f"NF 请求失败：{error}") from error

        status = payload.get("status")
        if status == "error":
            raise NextfindError("api", f"NF 返回错误：{payload.get('message')}")
        return payload

    async def _do_request(
        self, method: str, url: str, *, params, body, headers
    ) -> Dict[str, Any]:
        """优先宿主 AsyncRequestUtils，失败回退 requests。

        timeout 走 AsyncRequestUtils 构造器（文档化参数，默认 20s），
        避免依赖 kwargs 透传；headers 按 get_res/post_res 合同走 kwargs。
        """
        try:
            from app.sdk.network import AsyncRequestUtils

            utils = AsyncRequestUtils(timeout=self.timeout)
            if method == "GET":
                response = await utils.get_res(url, params=params, headers=headers)
            else:
                response = await utils.post_res(url, json=body, headers=headers)
            return self._unwrap(response)
        except ImportError:
            pass

        import requests  # 宿主共享环境必有；回退路径

        def _call() -> Dict[str, Any]:
            response = requests.request(
                method, url, params=params, json=body, headers=headers,
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                raise NextfindError("http", f"NF HTTP {response.status_code}")
            return response.json()

        return await asyncio.get_running_loop().run_in_executor(None, _call)

    @staticmethod
    def _unwrap(response: Any) -> Dict[str, Any]:
        """把响应对象转为 dict。

        兼容三种形态：
        1. 直接是 dict（测试替身）；
        2. httpx2.Response / requests.Response —— .json() 返回**已解析对象**；
        3. 退化按 .text 文本解析。
        HTTP >= 400 状态在此拦截并给出明确错误（宿主不会自动抛出）。
        """
        if isinstance(response, dict):
            return response
        if response is None:
            raise NextfindError("network", "NF 请求无响应（网络错误被宿主拦截）")
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int) and status_code >= 400:
            raise NextfindError("http", f"NF HTTP {status_code}")
        json_method = getattr(response, "json", None)
        if callable(json_method):
            try:
                parsed = json_method()
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            try:
                return json.loads(text)
            except Exception:
                pass
        raise NextfindError(
            "network",
            f"无法解析 NF 响应（类型 {type(response).__name__}，"
            f"状态 {status_code if status_code is not None else '未知'}）",
        )

    # ------------------------------------------------------------------ 端口

    async def search_resources(
        self, tmdb_id: str, media_type: str, season: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """GET /resources/search。"""
        params: Dict[str, Any] = {"tmdb_id": str(tmdb_id), "media_type": media_type}
        if season is not None:
            params["season"] = season
        payload = await self._request("GET", "/resources/search", params=params)
        data = payload.get("data")
        return list(data) if isinstance(data, list) else []

    async def library_progress(self, tmdb_id: str, media_type: str) -> Optional[int]:
        """POST /subscriptions/info 返回 local_episodes。"""
        payload = await self._request(
            "POST",
            "/subscriptions/info",
            body={"items": [{"tmdb_id": str(tmdb_id), "media_type": media_type}]},
        )
        data = payload.get("data") or []
        if not data:
            return None
        return data[0].get("local_episodes")

    async def add_subscription(
        self, tmdb_id: str, media_type: str, title: str = ""
    ) -> bool:
        """POST /subscriptions/add：添加 NF 订阅，触发 NF 全量搜索+转存。

        实测（2026-10-16）返回 "订阅成功，已加入第一队列排队进行全量搜索..."。
        tmdb_id 必须为字符串（官方文档明确约定）。
        """
        body: Dict[str, Any] = {"tmdb_id": str(tmdb_id), "media_type": media_type}
        if title:
            body["title"] = title
        payload = await self._request("POST", "/subscriptions/add", body=body)
        return payload.get("status") == "success"

    async def remove_subscription(self, tmdb_id: str, media_type: str) -> bool:
        """POST /subscriptions/remove：移除 NF 订阅（幂等）。

        实测（2026-10-16）返回 "已取消订阅"；重复移除同样返回 success。
        """
        payload = await self._request(
            "POST",
            "/subscriptions/remove",
            body={"tmdb_id": str(tmdb_id), "media_type": media_type},
        )
        return payload.get("status") == "success"

    async def submit_transfer(self, slug: str, target_folder: str) -> bool:
        """POST /transfer（异步任务，返回仅代表受理）。"""
        payload = await self._request(
            "POST", "/transfer", body={"slug": slug, "target_folder": target_folder}
        )
        return payload.get("status") == "success"

    async def transfer_history(self, slug: str) -> List[Dict[str, Any]]:
        """GET /history（分页拉取前 5 页用于兜底确认）。"""
        entries: List[Dict[str, Any]] = []
        for page in range(1, 6):
            payload = await self._request(
                "GET", "/history", params={"page": page, "page_size": 100}
            )
            data = payload.get("data")
            if not isinstance(data, list) or not data:
                break
            entries.extend(data)
            if any(str(entry.get("slug") or "").find(slug) >= 0 for entry in data):
                break
        return entries

    async def quota(self) -> Optional[Dict[str, Any]]:
        """GET /quota 健康预检：验证 NF 可达且密钥有效。

        成功返回额度数据字典；失败抛出 NextfindError（由编排层决定重试或跳过）。
        """
        payload = await self._request("GET", "/quota")
        return payload.get("data") if isinstance(payload.get("data"), dict) else {}

    async def recent_logs(self, lines: int = 20) -> Optional[List[str]]:
        """GET /logs 最近日志行（用于失败诊断富化）。"""
        payload = await self._request("GET", "/logs", params={"lines": lines})
        data = payload.get("data")
        return [str(line) for line in data] if isinstance(data, list) else None
