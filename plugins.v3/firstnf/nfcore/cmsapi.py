"""CMS（云盘媒体整理工具）联动 HTTP 适配器。

实测契约来源（2026-10-16，目标实例 http://192.168.50.91:9527）：
1. CMS 前端 bundle 反查：整理任务由 ``GET /api/sync/auto_organize`` 触发，
   但该接口要求网页登录会话令牌（插件侧不可得）。
2. CMS 配置页明确给出对外令牌端点：
   ``POST {domain}/api/emby/webhook?token={token}``（Emby 入库通知 Webhook），
   token 为 CMS 侧配置的 webhook 令牌；实测 ``{"status":"success"}``，
   token 错误时返回 ``{"code":"400","message":"token错误"}``。
3. 该端点与已安装的 CMSNotify 插件（配置项 cms_domain / cms_api_token /
   cms_notify_type=auto_organize）使用的是同一通道。

网络层与 nfapi 一致：优先宿主 app.sdk.network.AsyncRequestUtils，
导入失败时回退 requests，保证核心逻辑可在宿主外运行。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional
from urllib.parse import quote

from .ports import CmsNotifyPort

#: 默认 webhook 路径（CMS 配置页给出的 Emby 入库通知地址）
DEFAULT_WEBHOOK_PATH = "/api/emby/webhook"


class CmsNotifyError(Exception):
    """CMS 调用失败。"""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind  # network / http / api / config


class CmsWebhookAdapter(CmsNotifyPort):
    """基于 CMS webhook 的联动适配器。"""

    def __init__(
        self,
        domain: str,
        token: str,
        path: str = DEFAULT_WEBHOOK_PATH,
        timeout: float = 15.0,
    ) -> None:
        if not domain or not token:
            raise CmsNotifyError("config", "CMS domain/token 未配置")
        self.domain = domain.rstrip("/")
        self.token = token
        self.path = path if path.startswith("/") else f"/{path}"
        self.timeout = timeout

    # ------------------------------------------------------------------ HTTP

    async def _do_request(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """优先宿主 AsyncRequestUtils，失败回退 requests。"""
        headers = {"Content-Type": "application/json"}
        try:
            from app.sdk.network import AsyncRequestUtils

            utils = AsyncRequestUtils(timeout=self.timeout)
            response = await utils.post_res(url, json=body, headers=headers)
            return self._unwrap(response)
        except ImportError:
            pass

        import requests  # 宿主共享环境必有；回退路径

        def _call() -> Dict[str, Any]:
            response = requests.post(
                url, json=body, headers=headers, timeout=self.timeout
            )
            if response.status_code >= 400:
                raise CmsNotifyError("http", f"CMS HTTP {response.status_code}")
            return self._unwrap(response)

        return await asyncio.get_running_loop().run_in_executor(None, _call)

    @staticmethod
    def _unwrap(response: Any) -> Dict[str, Any]:
        """把响应对象转为 dict（与 nfapi._unwrap 同构）。"""
        if isinstance(response, dict):
            return response
        if response is None:
            raise CmsNotifyError("network", "CMS 请求无响应")
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int) and status_code >= 400:
            raise CmsNotifyError("http", f"CMS HTTP {status_code}")
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
        raise CmsNotifyError(
            "network",
            f"无法解析 CMS 响应（类型 {type(response).__name__}）",
        )

    # ------------------------------------------------------------------ 端口

    async def trigger_organize(self, title: str, path: str = "") -> bool:
        """POST {domain}{path}?token={token} 通知 CMS 整理。

        载荷采用 Emby 入库事件形状（CMS 该端点的原生输入格式）。
        """
        url = f"{self.domain}{self.path}?token={quote(str(self.token))}"
        body: Dict[str, Any] = {
            "Event": "library.new",
            "Item": {
                "Name": title or "",
                "Type": "Series",
                "Path": path or "",
            },
        }
        payload = await self._do_request(url, body)
        if payload.get("status") == "success":
            return True
        # token 错误等：抛出以便编排层记录诊断信息
        message = payload.get("message") or payload.get("msg") or str(payload)
        raise CmsNotifyError("api", f"CMS 返回异常：{message}")


def normalize_cms_domain(domain: str) -> str:
    """归一化 CMS 地址：去尾斜杠；缺协议时补 http://。"""
    base = (domain or "").strip().rstrip("/")
    if not base:
        return ""
    if not base.startswith(("http://", "https://")):
        base = f"http://{base}"
    return base


__all__ = ["CmsNotifyError", "CmsWebhookAdapter", "DEFAULT_WEBHOOK_PATH", "normalize_cms_domain"]
