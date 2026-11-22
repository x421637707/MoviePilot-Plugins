import asyncio
import time
from datetime import datetime
from typing import Any, List, Optional, Union

from apscheduler.triggers.cron import CronTrigger
from fastapi import Body
from pydantic import BaseModel, Field

from app import schemas
from app.chain.mediaserver import MediaServerChain
from app.chain.subscribe.facade import SubscribeChain
from app.db.oper.subscribe import SubscribeOper
from app.db.oper.subscribehistory import SubscribeHistoryOper
from app.modules.themoviedb.tmdbapi import TmdbApi
from app.schemas.query import (
    QueryPageRequest,
    QuerySort,
    QuerySortDirection,
    QuerySortField,
    SubscriptionHistoryFilter,
    SubscriptionHistorySnapshot,
)
from app.schemas.types import EventType, MediaSource, MediaType, MessageType
from app.sdk.config import global_vars, settings
from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger
from app.sdk.media import MediaInfo, normalize_media_source, resolve_media_identity
from app.sdk.plugin.base import _PluginBase
from app.sdk.services import ServiceConfigHelper


class FollowUpConfig(BaseModel):
    """续作跟进插件配置"""

    # 插件开关
    enabled: bool = False
    # 提前提醒天数
    after_days: int = Field(default=2, ge=1, le=30)
    # 系列检查年限
    threshold_years: int = Field(default=15, ge=2, le=50)
    # cron 表达式
    cron: str = ""
    # 单次运行开关
    onlyonce: bool = False
    # 检查订阅历史
    check_sub_history: bool = True
    # 媒体库
    libraries: list[str] = []


class FollowUp(_PluginBase):
    # 插件名称
    plugin_name = "续作跟进（X魔改版）"
    # 插件描述
    plugin_desc = "根据媒体库或订阅历史检查系列续作并通知订阅"
    # 插件图标
    plugin_icon = ""
    # 插件版本
    plugin_version = "3.1.3"
    # 插件作者
    plugin_author = "Attente"
    # 作者主页
    author_url = "https://github.com/wikrin"
    # 插件配置项ID前缀
    plugin_config_prefix = "followup_"
    # 加载顺序
    plugin_order = 99
    # 可使用的用户级别
    auth_level = 2

    # 私有属性
    _last_request_time = 0
    _request_lock = asyncio.Lock()
    _min_interval = 0.025

    # 待确认条目中，真正传给 SubscribeChain.add 的字段白名单。
    # 其余字段（type/episode_number/air_date/poster/created_at）仅用于页面展示。
    _SUBSCRIBE_FIELDS = (
        "title",
        "year",
        "media_source",
        "media_id",
        "episode_group",
        "season",
        "start_episode",
    )

    # 待确认条目 key 的类型前缀白名单
    _PENDING_PREFIXES = (MediaType.MOVIE.value, MediaType.TV.value)

    # 已忽略条目的展示信息（标题/年份/海报），仅用于插件页面
    _IGNORE_META_KEY = "ignore_meta"
    # 页面单个列表区块最多渲染多少行
    _PAGE_LIST_LIMIT = 200
    # 列表缩略图使用的 TMDB 尺寸
    _THUMB_SIZE = "w154"
    # 列表缩略图尺寸（像素）
    _THUMB_WIDTH = 46
    _THUMB_HEIGHT = 69
    # 每轮补全页面展示信息时最多处理的已忽略条目数 / 合集数
    _PENDING_META_BACKFILL_LIMIT = 100
    _IGNORE_META_BACKFILL_LIMIT = 100
    _COLLECTION_META_BACKFILL_LIMIT = 100

    # 配置
    config: FollowUpConfig | None = None

    def init_plugin(self, config: dict = None):

        # 停止现有任务
        self.stop_service()
        self.load_config(config)

        self.tmdbapi = TmdbApi()

        if self.config.onlyonce:
            self.schedule_once()
            # 关闭一次性开关
            self.config.onlyonce = False
            self.__update_config()

    def load_config(self, config: dict):
        """加载配置"""
        self.config = FollowUpConfig(**config) if config else FollowUpConfig()

    def schedule_once(self):
        logger.info("续作跟进，立即运行一次")
        return asyncio.run_coroutine_threadsafe(self.follow_up(), global_vars.loop)

    def __update_config(self):
        """更新配置"""
        self.update_config(self.config.model_dump())

    def get_form(self):
        # 获取所有启用的媒体服务器及其库信息
        mediaservers = ServiceConfigHelper.get_mediaserver_configs() or []
        libraryitems = [
            {"title": library.name, "value": library.id, "subtitle": mediaserver.name}
            for mediaserver in mediaservers
            if mediaserver and mediaserver.enabled
            for library in (MediaServerChain().librarys(mediaserver.name) or [])
        ]

        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 6, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 6, "md": 4},
                                "content": [
                                    {
                                        # 'component': 'VTextField', # 组件替换为VCronField
                                        "component": "VCronField",
                                        "props": {
                                            "model": "cron",
                                            "label": "执行周期",
                                            "placeholder": "5位cron表达式，留空自动",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 6, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "onlyonce",
                                            "label": "立即运行一次",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 6, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "check_sub_history",
                                            "label": "检查订阅历史",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 6, "md": 3},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "after_days",
                                            "label": "提前提醒(天)",
                                            "type": "number",
                                            "min": 1,
                                            "max": 30,
                                            "step": 1,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 6, "md": 5},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "threshold_years",
                                            "label": "检查年限",
                                            "placeholder": "播出或上映时间超出年限则不再检查",
                                            "type": "number",
                                            "min": 2,
                                            "max": 50,
                                            "step": 1,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 12},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "libraries",
                                            "label": "选择媒体库",
                                            "chips": True,
                                            "multiple": True,
                                            "clearable": True,
                                            "items": libraryitems,
                                            "item-props": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ],
            },
        ], {
            "enabled": False,
            "after_days": 2,
            "threshold_years": 15,
            "cron": "",
            "onlyonce": False,
            "check_sub_history": True,
            "libraries": [],
        }

    def get_service(self) -> list[dict]:
        """
        注册插件公共服务
        """
        if self.config.enabled:
            trigger = (
                CronTrigger.from_crontab(self.config.cron)
                if self.config.cron
                else "interval"
            )
            kwargs = {"hours": 24} if not self.config.cron else {}
            return [
                {
                    "id": "FollowUp",
                    "name": "续作跟进",
                    "trigger": trigger,
                    "func": self.follow_up,
                    "kwargs": kwargs,
                }
            ]
        return []

    def stop_service(self):
        """退出插件"""

    def get_api(self):
        return [
            {
                "path": "/confirm",
                "endpoint": self.api_confirm,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "确认续作跟进操作（追加订阅/忽略）",
            },
            {
                "path": "/batch",
                "endpoint": self.api_batch,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "批量处理待确认续作（追加订阅/忽略）",
            },
        ]


    def get_command(self):
        return [
            {
                "cmd": "/follow_up",
                "event": EventType.PluginAction,
                "desc": "续作跟进",
                "category": "",
                "data": {"action": "follow_up"},
            }
        ]

    # ------------------------------------------------------------------ #
    # 页面
    # ------------------------------------------------------------------ #
    @staticmethod
    def _image_url(path: Optional[str]) -> str:
        """把 TMDB 相对图片路径补成完整 URL；已是完整 URL 时原样返回。"""
        if not path:
            return ""
        path = str(path)
        if path.startswith("http://") or path.startswith("https://"):
            return path
        domain = getattr(settings, "TMDB_IMAGE_DOMAIN", None) or "image.tmdb.org"
        if not str(domain).startswith("http"):
            domain = f"https://{domain}"
        return f"{str(domain).rstrip('/')}/t/p/original{path}"

    @classmethod
    def _thumb_url(cls, poster: Optional[str]) -> str:
        """列表缩略图：把 original 换成小尺寸，避免加载大图。"""
        url = cls._image_url(poster)
        if not url:
            return ""
        return url.replace("/t/p/original/", f"/t/p/{cls._THUMB_SIZE}/")

    @classmethod
    def _poster_node(cls, poster: Optional[str], icon: str) -> dict:
        """列表行左侧的海报缩略图；没有海报时退回图标。"""
        thumb = cls._thumb_url(poster)
        if thumb:
            return {
                "component": "VImg",
                "props": {
                    "src": thumb,
                    "width": cls._THUMB_WIDTH,
                    "height": cls._THUMB_HEIGHT,
                    "cover": True,
                    "rounded": "sm",
                },
            }
        return {
            "component": "VAvatar",
            "props": {
                "size": cls._THUMB_HEIGHT,
                "rounded": "sm",
                "variant": "tonal",
            },
            "content": [{"component": "VIcon", "props": {"icon": icon}}],
        }

    def _pending_items(self) -> List[tuple]:
        """收集待确认条目 [(key, data), ...]，按播出日期升序排列。"""
        items: List[tuple] = []
        for record in self.get_data() or []:
            key = getattr(record, "key", None)
            if not isinstance(key, str) or "." not in key:
                continue
            if key.split(".", 1)[0] not in self._PENDING_PREFIXES:
                continue
            value = getattr(record, "value", None)
            items.append((key, value if isinstance(value, dict) else {}))

        items.sort(key=lambda kv: (
            str(kv[1].get("air_date") or "9999-12-31"),
            str(kv[1].get("title") or kv[0]),
        ))
        return items

    @staticmethod
    def _action_button(key: str, action: str, text: str, color: str) -> dict:
        """生成一个调用 /confirm 的按钮节点（页面事件走顶层 events 字段）。"""
        return {
            "component": "VBtn",
            "props": {
                "color": color,
                "variant": "tonal",
                "size": "small",
                "class": "mr-2",
            },
            "text": text,
            "events": {
                "click": {
                    "api": "plugin/FollowUp/confirm",
                    "method": "post",
                    "params": {"key": key, "action": action},
                }
            },
        }

    @staticmethod
    def _stat_cell(label: str, value: Any, icon: str, color: str) -> dict:
        return {
            "component": "VCol",
            "props": {"cols": 6, "md": 3},
            "content": [
                {
                    "component": "div",
                    "props": {"class": "d-flex align-center"},
                    "content": [
                        {
                            "component": "VIcon",
                            "props": {"icon": icon, "color": color, "size": "26", "class": "mr-2"},
                        },
                        {
                            "component": "div",
                            "content": [
                                {
                                    "component": "div",
                                    "props": {"class": "text-caption text-medium-emphasis"},
                                    "text": label,
                                },
                                {
                                    "component": "div",
                                    "props": {"class": "text-body-1 font-weight-medium"},
                                    "text": str(value),
                                },
                            ],
                        },
                    ],
                }
            ],
        }

    def _overview_card(self, pending_count: int, ignored_count: int,
                       collection_count: int, last_run: str) -> dict:
        return {
            "component": "VCard",
            "props": {"class": "mb-3", "variant": "tonal"},
            "content": [
                {
                    "component": "VCardText",
                    "content": [
                        {
                            "component": "VRow",
                            "content": [
                                self._stat_cell("待确认", pending_count, "mdi-bell-ring-outline", "primary"),
                                self._stat_cell("已忽略", ignored_count, "mdi-bell-off-outline", "grey"),
                                self._stat_cell("追踪系列", collection_count, "mdi-movie-open-outline", "teal"),
                                self._stat_cell("上次运行", last_run or "暂无", "mdi-clock-outline", "blue-grey"),
                            ],
                        }
                    ],
                }
            ],
        }

    def _item_card(self, key: str, data: dict) -> dict:
        """单条待确认条目卡片。"""
        # 存量条目（旧版推送）可能没有 type 字段，从 key 前缀兜底
        mtype = data.get("type") or (key.split(".", 1)[0] if "." in key else "")
        is_movie = mtype == MediaType.MOVIE.value
        icon = "mdi-movie-open" if is_movie else "mdi-television-classic"

        title = data.get("title") or key
        year = data.get("year") or ""
        display_title = f"{title} ({year})" if year else title

        parts: List[str] = []
        if mtype:
            parts.append(mtype)
        if not is_movie:
            season = data.get("season") or 0
            episode = data.get("episode_number") or 0
            if season and episode:
                parts.append(f"S{int(season):02d}E{int(episode):02d}")
        air_date = str(data.get("air_date") or "")[:10]
        if air_date:
            parts.append(f"播出 {air_date}")
        subtitle = " · ".join(parts)

        info_content: List[dict] = [
            {
                "component": "div",
                "props": {"class": "text-body-1 font-weight-medium"},
                "text": display_title,
            }
        ]
        if subtitle:
            info_content.append({
                "component": "div",
                "props": {"class": "text-caption text-medium-emphasis"},
                "text": subtitle,
            })

        return {
            "component": "VCard",
            "props": {"class": "mb-2", "variant": "outlined"},
            "content": [
                {
                    "component": "VCardText",
                    "content": [
                        {
                            "component": "VRow",
                            "props": {"align": "center"},
                            "content": [
                                {
                                    "component": "VCol",
                                    "props": {"cols": "auto"},
                                    "content": [self._poster_node(data.get("poster"), icon)],
                                },
                                {
                                    "component": "VCol",
                                    "content": info_content,
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": "auto"},
                                    "content": [
                                        self._action_button(key, "add", "追加订阅", "primary"),
                                        self._action_button(key, "ignore", "忽略", "error"),
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }

    def _batch_bar(self, keys: List[str]) -> dict:
        """底部批量操作条。"""
        return {
            "component": "VCard",
            "props": {"class": "mt-2", "variant": "tonal"},
            "content": [
                {
                    "component": "VCardText",
                    "content": [
                        {
                            "component": "div",
                            "props": {"class": "d-flex justify-end align-center flex-wrap"},
                            "content": [
                                {
                                    "component": "div",
                                    "props": {"class": "text-caption text-medium-emphasis mr-3"},
                                    "text": f"共 {len(keys)} 条待确认",
                                },
                                {
                                    "component": "VBtn",
                                    "props": {
                                        "color": "primary",
                                        "variant": "flat",
                                        "size": "small",
                                        "class": "mr-2",
                                    },
                                    "text": "全部追加订阅",
                                    "events": {
                                        "click": {
                                            "api": "plugin/FollowUp/batch",
                                            "method": "post",
                                            "params": {"keys": keys, "action": "add"},
                                        }
                                    },
                                },
                                {
                                    "component": "VBtn",
                                    "props": {"color": "error", "variant": "flat", "size": "small"},
                                    "text": "全部忽略",
                                    "events": {
                                        "click": {
                                            "api": "plugin/FollowUp/batch",
                                            "method": "post",
                                            "params": {"keys": keys, "action": "ignore"},
                                        }
                                    },
                                },
                            ],
                        }
                    ],
                }
            ],
        }

    @staticmethod
    def _expansion_panel(title: str, content: List[dict], value: Optional[str] = None) -> dict:
        """可折叠区块。value 用于配合父级 modelValue 控制默认展开状态。"""
        panel = {
            "component": "VExpansionPanel",
            "content": [
                {"component": "VExpansionPanelTitle", "text": title},
                {"component": "VExpansionPanelText", "content": content},
            ],
        }
        if value:
            panel["props"] = {"value": value}
        return panel

    @classmethod
    def _plain_row(cls, icon: str, title: str, subtitle: str, chips: List[dict],
                   button: Optional[dict] = None, poster: Optional[str] = None) -> dict:
        """一行「海报/图标 + 标题/副标题 + 标签 + 可选按钮」。"""
        info: List[dict] = [
            {
                "component": "div",
                "props": {"class": "text-body-2 font-weight-medium"},
                "text": title,
            }
        ]
        if subtitle:
            info.append({
                "component": "div",
                "props": {"class": "text-caption text-medium-emphasis"},
                "text": subtitle,
            })
        if chips:
            info.append({
                "component": "div",
                "props": {"class": "d-flex align-center flex-wrap mt-1"},
                "content": chips,
            })

        row_content: List[dict] = [
            {
                "component": "VCol",
                "props": {"cols": "auto"},
                "content": [cls._poster_node(poster, icon)],
            },
            {"component": "VCol", "content": info},
        ]
        if button:
            row_content.append({
                "component": "VCol",
                "props": {"cols": "auto"},
                "content": [button],
            })

        return {
            "component": "VRow",
            "props": {"align": "center", "class": "py-1"},
            "content": row_content,
        }

    def _within_threshold(self, date_value: Optional[str]) -> bool:
        """判断某个播出/上映时间是否落在「检查年限」窗口内。

        判定依据与 `_filter_media` / `_should_track_media` 完全一致：以该条目
        自身的播出/上映时间为基准，窗口为「距今 ± threshold_years 年」。

        - 边界：恰好等于 threshold_years 年（365 * threshold_years 天）视为
          **在窗口内**（闭区间），比它更远才被排除。
        - 缺失或无法解析的日期不做判定，返回 True（保留展示），避免误伤存量数据。
        """
        raw = str(date_value or "")[:10]
        if not raw:
            return True
        try:
            datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            return True
        return self.is_date_in_range(raw, datetime.now(), 365 * self.config.threshold_years)

    def _threshold_note(self, hidden: int, subject: str) -> Optional[dict]:
        """区块顶部的年限说明；有被隐藏的条目时才提示。"""
        if not hidden:
            return None
        return {
            "component": "div",
            "props": {"class": "text-caption text-medium-emphasis mb-2"},
            "text": (
                f"仅展示播出/上映时间在 {self.config.threshold_years} 年内的{subject}；"
                f"已隐藏 {hidden} 条超出检查年限的记录。"
            ),
        }

    def _ignore_entries(self) -> tuple:
        """按检查年限过滤后的已忽略条目 [(key_tuple, info)]，以及被隐藏的数量。"""
        meta = self.get_ignore_meta()
        today = datetime.now().date()
        kept: List[tuple] = []
        hidden = 0

        for key_tuple in self.get_ignore_keys():
            info = meta.get(self.build_key(*key_tuple))
            info = info if isinstance(info, dict) else {}
            if not self._within_threshold(info.get("air_date")):
                hidden += 1
                continue
            kept.append((key_tuple, info))

        def sort_key(item: tuple) -> tuple:
            """离今天越近越靠前；没有日期的排最后。"""
            raw = str(item[1].get("air_date") or "")[:10]
            try:
                distance = abs((datetime.strptime(raw, "%Y-%m-%d").date() - today).days)
            except (TypeError, ValueError):
                distance = 10 ** 6
            return (distance, item[0][0], item[0][1])

        kept.sort(key=sort_key)
        return kept, hidden

    def _ignored_section(self, entries: List[tuple], hidden: int) -> Optional[dict]:
        """已忽略列表：仅展示检查年限内的条目，按播出/上映时间由近及远排序。"""
        if not entries and not hidden:
            return None

        rows: List[dict] = []
        note = self._threshold_note(hidden, "已忽略条目")
        if note:
            rows.append(note)

        for key_tuple, info in entries[: self._PAGE_LIST_LIMIT]:
            key = self.build_key(*key_tuple)
            title = info.get("title") or ""
            year = info.get("year") or ""
            is_movie = key_tuple[0] == MediaType.MOVIE.value
            icon = "mdi-movie-open" if is_movie else "mdi-television-classic"
            display = f"{title} ({year})" if title and year else (title or key)

            chips = [
                {
                    "component": "VChip",
                    "props": {
                        "size": "x-small",
                        "variant": "tonal",
                        "color": "deep-purple" if is_movie else "indigo",
                        "class": "mr-1",
                    },
                    "text": key_tuple[0],
                },
                {
                    "component": "VChip",
                    "props": {"size": "x-small", "variant": "text"},
                    "text": f"TMDB {key_tuple[1]}",
                },
            ]
            air_date = str(info.get("air_date") or "")[:10]
            if air_date:
                chips.append({
                    "component": "VChip",
                    "props": {"size": "x-small", "variant": "text"},
                    "text": f"上映 {air_date}",
                })
            if not title:
                chips.append({
                    "component": "VChip",
                    "props": {"size": "x-small", "variant": "text", "color": "warning"},
                    "text": "信息待补全",
                })

            rows.append(self._plain_row(
                icon=icon,
                title=display,
                subtitle="",
                chips=chips,
                poster=info.get("poster"),
                button={
                    "component": "VBtn",
                    "props": {"color": "primary", "variant": "text", "size": "small"},
                    "text": "取消忽略",
                    "events": {
                        "click": {
                            "api": "plugin/FollowUp/confirm",
                            "method": "post",
                            "params": {"key": key, "action": "unignore"},
                        }
                    },
                },
            ))

        if len(entries) > self._PAGE_LIST_LIMIT:
            rows.append({
                "component": "div",
                "props": {"class": "text-caption text-medium-emphasis mt-2"},
                "text": f"仅显示前 {self._PAGE_LIST_LIMIT} 条，共 {len(entries)} 条",
            })

        return self._expansion_panel(f"已忽略（{len(entries)}）", rows, value="ignored")

    def _collection_entries(self) -> tuple:
        """按检查年限过滤后的电影合集 [(collection_id, info)]，以及被隐藏的数量。"""
        kept: List[tuple] = []
        hidden = 0

        for collection_id, raw in self.get_collections().items():
            info = raw if isinstance(raw, dict) else {}
            if not self._within_threshold(info.get("latest_release_date")):
                hidden += 1
                continue
            kept.append((collection_id, info))

        kept.sort(key=lambda item: str(item[1].get("name") or item[0]))
        return kept, hidden

    def _collection_section(self, entries: List[tuple], hidden: int) -> Optional[dict]:
        """电影系列追踪列表（只读展示）：仅展示检查年限内的合集。"""
        if not entries and not hidden:
            return None

        rows: List[dict] = [
            {
                "component": "div",
                "props": {"class": "text-caption text-medium-emphasis mb-2"},
                "text": (
                    "追踪系列 = 你媒体库里属于同一个 TMDB 电影合集的作品。"
                    "插件会盯住该合集最新的一部，快上映/上线时提醒你。"
                ),
            }
        ]
        note = self._threshold_note(hidden, "追踪系列")
        if note:
            rows.append(note)

        for collection_id, info in entries[: self._PAGE_LIST_LIMIT]:
            name = info.get("name") or f"合集 {collection_id}"
            parts = info.get("parts") or []
            following = bool(info.get("follow_up"))
            latest = str(info.get("latest_release_date") or "")[:10]
            air_date = str(info.get("air_date") or "")[:10]

            chips = [
                {
                    "component": "VChip",
                    "props": {
                        "size": "x-small",
                        "variant": "tonal",
                        "color": "primary" if following else "grey",
                        "class": "mr-1",
                    },
                    "text": "追踪中" if following else "已停止",
                },
                {
                    "component": "VChip",
                    "props": {"size": "x-small", "variant": "text"},
                    "text": f"{len(parts)} 部",
                },
                {
                    "component": "VChip",
                    "props": {"size": "x-small", "variant": "text"},
                    "text": f"TMDB 合集 {collection_id}",
                },
            ]
            if latest:
                chips.append({
                    "component": "VChip",
                    "props": {"size": "x-small", "variant": "text"},
                    "text": f"最新 {latest}",
                })
            if air_date:
                chips.append({
                    "component": "VChip",
                    "props": {"size": "x-small", "variant": "text"},
                    "text": f"发行 {air_date}",
                })

            rows.append(self._plain_row(
                icon="mdi-movie-open-outline",
                title=name,
                subtitle="",
                chips=chips,
                poster=info.get("poster"),
            ))

        if len(entries) > self._PAGE_LIST_LIMIT:
            rows.append({
                "component": "div",
                "props": {"class": "text-caption text-medium-emphasis mt-2"},
                "text": f"仅显示前 {self._PAGE_LIST_LIMIT} 条，共 {len(entries)} 条",
            })

        return self._expansion_panel(f"追踪系列（{len(entries)}）", rows, value="collections")

    def get_page(self):
        """插件详情页：概览 + 待确认处理 + 已忽略 / 追踪系列明细（仅检查年限内）。"""
        pending = self._pending_items()
        ignore_entries, ignore_hidden = self._ignore_entries()
        collection_entries, collection_hidden = self._collection_entries()
        last_run = (self.get_data("last_run") or {}).get("at") or ""

        page: List[dict] = [
            self._overview_card(
                len(pending), len(ignore_entries), len(collection_entries), last_run
            )
        ]

        if pending:
            keys = [key for key, _ in pending]
            page.extend(self._item_card(key, data) for key, data in pending)
            page.append(self._batch_bar(keys))
        else:
            page.append({
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "tonal",
                    "text": "暂无待确认的续作跟进条目。",
                },
            })

        panels = [
            section for section in (
                self._ignored_section(ignore_entries, ignore_hidden),
                self._collection_section(collection_entries, collection_hidden),
            ) if section
        ]
        if panels:
            page.append({
                "component": "VExpansionPanels",
                "props": {
                    "multiple": True,
                    "class": "mt-3",
                    # 默认展开「已忽略」：取消单个忽略项后宿主会重新拉取整页，
                    # 不设默认展开的话选项卡会被折叠回去，无法连续取消。
                    "modelValue": ["ignored"],
                },
                "content": panels,
            })

        return page

    def api_confirm(self, payload: Optional[dict] = Body(default=None)) -> schemas.Response:
        """处理页面单条确认操作"""
        if not self.get_state():
            return schemas.Response(success=False, message="插件未启用")

        key = str((payload or {}).get("key") or "")
        action = str((payload or {}).get("action") or "")
        if not key or not action:
            return schemas.Response(success=False, message="参数不完整")

        if action == "add":
            success, msg = self._do_add(key)
        elif action == "ignore":
            success, msg = self._do_ignore(key)
        elif action == "unignore":
            success, msg = self._do_unignore(key)
        else:
            return schemas.Response(success=False, message="未知操作")

        return schemas.Response(success=success, message=msg)

    def api_batch(self, payload: Optional[dict] = Body(default=None)) -> schemas.Response:
        """处理页面批量确认操作"""
        if not self.get_state():
            return schemas.Response(success=False, message="插件未启用")

        body = payload or {}
        action = str(body.get("action") or "")
        raw_keys = body.get("keys")
        handlers = {
            "add": (self._do_add, "追加订阅"),
            "ignore": (self._do_ignore, "忽略"),
            "unignore": (self._do_unignore, "取消忽略"),
        }
        if action not in handlers:
            return schemas.Response(success=False, message="未知操作")
        if not isinstance(raw_keys, list) or not raw_keys:
            return schemas.Response(success=False, message="未选择任何条目")

        handler, word = handlers[action]

        ok, fail, errors = 0, 0, []
        for raw_key in raw_keys:
            key = str(raw_key or "")
            if not key:
                continue
            try:
                success, msg = handler(key)
            except Exception as exc:
                logger.error(f"批量{word}失败 {key}: {exc}")
                success, msg = False, str(exc)
            if success:
                ok += 1
            else:
                fail += 1
                errors.append(f"{key}: {msg}")

        if fail == 0:
            return schemas.Response(
                success=True,
                message=f"已{word} {ok} 条",
                data={"ok": ok, "fail": 0, "errors": []},
            )
        return schemas.Response(
            success=ok > 0,
            message=f"{word}完成：成功 {ok} 条，失败 {fail} 条",
            data={"ok": ok, "fail": fail, "errors": errors[:20]},
        )


    def get_state(self):
        return self.config.enabled

    @eventmanager.register(EventType.PluginAction)
    def action_event_handler(self, event: Event):
        """
        远程命令处理
        """
        event_data = event.event_data
        if not event_data or event_data.get("action") != "follow_up":
            return

        self.post_message(
            channel=event_data.get("channel"),
            title=f"【续作跟进】开始执行 ...",
            userid=event_data.get("user"),
        )
        # 执行任务
        try:
            future = self.schedule_once()
            future.result()  # 等待任务完成
            result_msg = {"title": "【续作跟进】执行完成"}
        except Exception as e:
            logger.error(f"执行续作跟进任务出错: {e!s}")
            result_msg = {"title": "【续作跟进】执行失败", "text": f"错误信息: {e!s}"}

        # 发送消息
        self.post_message(
            channel=event_data.get("channel"),
            userid=event_data.get("user"),
            **result_msg,
        )

    async def _fetch_tmdb_info(self, mtype: str, tmdbid: str) -> dict | None:
        # 频率限制
        async with self._request_lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = time.time()

        try:
            if mtype == MediaType.MOVIE.value:
                if details := await self.tmdbapi.movie.async_details(tmdbid):
                    return {
                        "title_year": f"{details.get('title')} ({details.get('release_date')[:4]})",
                        "type": MediaType.MOVIE,
                        "tmdb_id": tmdbid,
                        "release_date": details.get("release_date"),
                        "belongs_to_collection": details.get("belongs_to_collection"),
                    }
            elif mtype == MediaType.TV.value and (details := await self.tmdbapi.tv.async_details(tmdbid)):
                return {
                    "title_year": f"{details.get('name')} ({details.get('first_air_date')[:4]})",
                    "type": MediaType.TV,
                    "tmdb_id": tmdbid,
                    "last_air_date": details.get("last_air_date"),
                    "next_episode_to_air": details.get("next_episode_to_air"),
                }
            return None
        except Exception as e:
            logger.debug(f"获取TMDB信息失败 ({mtype} {tmdbid}): {e}")
            return None

    async def _fetch_display_meta(self, mtype: str, tmdbid: str | int) -> Optional[dict]:
        """取标题/年份/海报，用于补全已忽略条目的页面展示信息。"""
        async with self._request_lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = time.time()

        try:
            if mtype == MediaType.MOVIE.value:
                details = await self.tmdbapi.movie.async_details(tmdbid)
                if details:
                    return {
                        "title": details.get("title") or "",
                        "year": (details.get("release_date") or "")[:4],
                        "poster": self._image_url(details.get("poster_path")),
                        "air_date": str(details.get("release_date") or "")[:10],
                    }
            elif mtype == MediaType.TV.value:
                details = await self.tmdbapi.tv.async_details(tmdbid)
                if details:
                    next_episode = details.get("next_episode_to_air") or {}
                    air_date = next_episode.get("air_date") or details.get("last_air_date") or ""
                    return {
                        "title": details.get("name") or "",
                        "year": (details.get("first_air_date") or "")[:4],
                        "poster": self._image_url(details.get("poster_path")),
                        "air_date": str(air_date)[:10],
                    }
            return None
        except Exception as e:
            logger.debug(f"补全标题失败 ({mtype} {tmdbid}): {e}")
            return None

    async def _backfill_pending_meta(self) -> None:
        """为缺少海报或播出日期的待确认条目补全展示信息（兼容旧版本推送的条目）。"""
        pending = [
            (key, data)
            for key, data in self._pending_items()
            if not data.get("poster") or not data.get("air_date")
        ]
        if not pending:
            return

        batch = pending[: self._PENDING_META_BACKFILL_LIMIT]
        logger.info(f"补全待确认条目信息：本轮 {len(batch)}/{len(pending)} 条")

        results = await asyncio.gather(
            *[
                self._fetch_display_meta(*key.split(".", 1))
                for key, _ in batch
            ],
            return_exceptions=True,
        )

        changed = 0
        for (key, data), info in zip(batch, results):
            if isinstance(info, Exception) or not isinstance(info, dict):
                continue
            updated = dict(data)
            updated["title"] = data.get("title") or info.get("title") or ""
            updated["year"] = data.get("year") or info.get("year") or ""
            updated["poster"] = data.get("poster") or info.get("poster") or ""
            updated["air_date"] = data.get("air_date") or info.get("air_date") or ""
            updated["type"] = data.get("type") or key.split(".", 1)[0]
            if updated == data:
                continue
            self.save_data(key, updated)
            changed += 1

        if changed:
            logger.info(f"补全待确认条目信息完成，更新 {changed} 条")

    async def _backfill_ignore_meta(self) -> None:
        """为缺少标题或海报的已忽略条目补全展示信息，每轮最多处理 _IGNORE_META_BACKFILL_LIMIT 条。"""
        meta = self.get_ignore_meta()

        def incomplete(key_tuple: tuple) -> bool:
            """未补全过（或结构不完整）的条目。synced 标记避免无日期条目被反复重拉。"""
            info = meta.get(self.build_key(*key_tuple))
            if not isinstance(info, dict):
                return True
            return not info.get("synced")

        missing = [
            key_tuple
            for key_tuple in sorted(self.get_ignore_keys(), key=lambda item: (item[0], item[1]))
            if incomplete(key_tuple)
        ]
        if not missing:
            return

        batch = missing[: self._IGNORE_META_BACKFILL_LIMIT]
        logger.info(f"补全已忽略条目信息：本轮 {len(batch)}/{len(missing)} 条")

        results = await asyncio.gather(
            *[self._fetch_display_meta(mtype, tmdbid) for mtype, tmdbid in batch],
            return_exceptions=True,
        )

        changed = 0
        for key_tuple, info in zip(batch, results):
            if isinstance(info, Exception) or not isinstance(info, dict):
                continue
            key = self.build_key(*key_tuple)
            current = meta.get(key) if isinstance(meta.get(key), dict) else {}
            title = info.get("title") or current.get("title") or ""
            poster = info.get("poster") or current.get("poster") or ""
            if not title and not poster:
                continue
            meta[key] = {
                "title": title,
                "year": info.get("year") or current.get("year") or "",
                "type": key_tuple[0],
                "poster": poster,
                "air_date": info.get("air_date") or current.get("air_date") or "",
                "synced": True,
                "ignored_at": current.get("ignored_at") or "",
            }
            changed += 1

        if changed:
            self.save_ignore_meta(meta)
            logger.info(f"补全已忽略条目信息完成，更新 {changed} 条，剩余 {len(missing) - changed} 条")

    async def _fetch_collection_poster(self, collection_id: int) -> str:
        """取 TMDB 合集海报。"""
        async with self._request_lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = time.time()

        try:
            details = await self.tmdbapi.collection.async_details(collection_id=collection_id)
            if details:
                return self._image_url(details.get("poster_path"))
        except Exception as e:
            logger.debug(f"获取合集海报失败 ({collection_id}): {e}")
        return ""

    async def _backfill_collection_meta(self) -> None:
        """为缺少海报的电影合集补全海报，每轮最多处理 _COLLECTION_META_BACKFILL_LIMIT 个。"""
        collections = self.get_collections()
        missing = [
            cid
            for cid, info in collections.items()
            if isinstance(info, dict) and not info.get("poster")
        ]
        if not missing:
            return

        batch = missing[: self._COLLECTION_META_BACKFILL_LIMIT]
        logger.info(f"补全合集海报：本轮 {len(batch)}/{len(missing)} 个")

        results = await asyncio.gather(
            *[self._fetch_collection_poster(int(cid)) for cid in batch],
            return_exceptions=True,
        )

        changed = 0
        for cid, poster in zip(batch, results):
            if isinstance(poster, Exception) or not poster:
                continue
            info = collections.get(cid)
            if isinstance(info, dict):
                info["poster"] = poster
                changed += 1

        if changed:
            self.save_collections(collections)
            logger.info(f"补全合集海报完成，更新 {changed} 个，剩余 {len(missing) - changed} 个")

    async def _backfill_page_meta(self) -> None:
        """补全插件页面展示信息（待确认条目、已忽略条目、合集海报）；失败不影响跟进主流程。"""
        try:
            await self._backfill_pending_meta()
            await self._backfill_ignore_meta()
            await self._backfill_collection_meta()
        except Exception as e:
            logger.error(f"补全页面展示信息失败: {e}")

    async def follow_up(self):
        # 获取忽略列表
        _ignore = self.get_ignore_keys()
        # 获取系列合集
        collections = self.get_collections()
        # 获取需要跟进的媒体
        his = self._need_follow_up(_ignore, collections)
        if not his:
            logger.info("没有需要跟进的媒体项。")
            await self._backfill_page_meta()
            self.save_data("last_run", {"at": datetime.now().strftime("%Y-%m-%d %H:%M")})
            return

        await self._filter_media(his, _ignore, collections)

        if collections:
            self.collection_follow_up(collections, _ignore)

        self.save_collections(collections)
        # 补全已忽略条目与合集的页面展示信息
        await self._backfill_page_meta()
        # 记录最近一次运行时间，供插件页面概览展示
        self.save_data("last_run", {"at": datetime.now().strftime("%Y-%m-%d %H:%M")})
        logger.info("续作跟进执行完成。")

    async def _filter_media(
        self,
        his: set[tuple[str, str]],
        _ignore: set[tuple[str, str]],
        collections: dict[str, dict],
    ):

        logger.info(f"开始对 {len(his)} 个条目进行预检...")

        tasks = [self._fetch_tmdb_info(mtype, tmdbid) for mtype, tmdbid in his]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items_for_full_recognition = []
        _collection_ids = set()
        his_list = list(his)

        for i, min_info in enumerate(results):
            key = his_list[i]

            if isinstance(min_info, Exception):
                logger.debug(f"获取TMDB信息失败 ({key}): {min_info}")
                continue

            if not min_info:
                continue

            # 电视剧或非系列电影检查年限
            if not min_info.get("belongs_to_collection"):
                air_date = min_info.get("last_air_date") or min_info.get("release_date")
                if air_date and not self.is_date_in_range(
                    air_date, datetime.now(), 365 * self.config.threshold_years
                ):
                    logger.info(
                        f"{key} {min_info['title_year']} 已超过设定年限: {self.config.threshold_years} 年，不再跟进"
                    )
                    _ignore.add(key)
                    self.update_ignore_keys(key)
                    continue

            # 检查具体更新
            if min_info["type"] == MediaType.TV:
                next_episode = min_info.get("next_episode_to_air")
                if next_episode and self.is_date_in_range(
                    next_episode.get("air_date"), threshold_days=self.config.after_days
                ):
                    items_for_full_recognition.append(key)

            elif min_info["type"] == MediaType.MOVIE:
                collection = min_info.get("belongs_to_collection")
                if collection and collection["id"] not in _collection_ids:
                    _collection_ids.add(collection["id"])
                    items_for_full_recognition.append(key)

        logger.info(f"发现 {len(items_for_full_recognition)} 个有价值的新条目。")

        if not items_for_full_recognition:
            return

        for mtype, tmdbid in items_for_full_recognition:
            mediainfo = self.chain.recognize_media(
                mtype=MediaType(mtype),
                media_source=MediaSource.TMDB,
                media_id=str(tmdbid),
            )
            if not mediainfo:
                continue

            if mediainfo.type == MediaType.MOVIE:
                self._handle_movie(mediainfo, collections)
            else:
                self._handle_tv_show(mediainfo)

    def _handle_movie(self, mediainfo: MediaInfo, collections: dict):
        """处理电影逻辑"""
        collection_id, collection_name = self._get_collection_id(mediainfo)
        if not collection_id:
            return

        if str(collection_id) not in collections:
            collections[str(collection_id)] = {
                "follow_up": True,
                "name": collection_name,
            }
            logger.info(
                f"{mediainfo.tmdb_id} {mediainfo.title_year} 添加至系列合集 {collection_id} {collection_name}"
            )

    def _handle_tv_show(self, mediainfo: MediaInfo):
        """处理电视剧逻辑"""
        next_episode = mediainfo.next_episode_to_air

        if not (air_date := next_episode.get("air_date")):
            logger.info(
                f"{mediainfo.tmdb_id} {mediainfo.title_year} 没有新集或播出日期"
            )
            return

        # 获取季号和集号
        season_number = next_episode.get("season_number", 1)
        episode_number = next_episode.get("episode_number", 1)

        # 补零格式化
        season_number_str = f"S{season_number:02d}"
        episode_number_str = f"E{episode_number:02d}"

        msg_title = f"🆕 {mediainfo.title_year} {season_number_str}{episode_number_str} 即将播出"
        msg_text = (
            f"🎬 标题：{next_episode['name'] or '暂无标题'}\n"
            f"📅 播出日期：{air_date[:10]}\n"
            f"👉 是否订阅该系列的最新作品？\n"
        )

        self._send_menu_message(mediainfo, msg_title, msg_text, air_date=air_date)

    def collection_follow_up(self, collections: dict[str, dict], ignore: set[tuple]):
        from app.chain.tmdb import TmdbChain

        tmdbchain = TmdbChain()

        logger.info(f"开始检查 {len(collections)} 个电影合集...")
        for collection_id, followinfo in collections.items():
            if not followinfo.get("follow_up"):
                continue

            collection_info = tmdbchain.tmdb_collection(
                collection_id=int(collection_id)
            )
            if not collection_info:
                continue

            # 查找最新电影
            latest_part = max(
                collection_info, key=lambda p: p.release_date or "0000-00-00"
            )
            media_type = latest_part.type
            tmdbid = latest_part.tmdb_id

            latest_release_date = followinfo.get("latest_release_date") or "0000-00-00"
            latest_air_date = followinfo.get("air_date")

            if latest_part.release_date > latest_release_date:
                # 更新系列信息
                followinfo["parts"] = [
                    self.build_key(p.type.value, str(p.tmdb_id))
                    for p in collection_info
                ]
                followinfo["latest_release_date"] = latest_part.release_date

            # 判断是否仍需追踪该系列
            if not self._should_track_media(latest_part):
                followinfo["follow_up"] = False

            if latest_air_date and not self.is_date_in_range(
                latest_air_date, threshold_days=self.config.after_days
            ):
                logger.info(
                    f"{followinfo.get('name') or collection_id} 没有新的系列电影上映"
                )
                continue

            if (
                not followinfo["follow_up"]
                or (latest_part.type.value, str(latest_part.tmdb_id)) in ignore
            ):
                continue

            # 获取数字发行日期
            if media_type == MediaType.MOVIE:
                next_air_date, msg = self.find_earliest_date(tmdbid)
                followinfo["air_date"] = next_air_date
            else:
                next_air_date = None

            # 判断是否符合提醒时间
            if next_air_date is None or not self.is_date_in_range(
                next_air_date, threshold_days=self.config.after_days
            ):
                logger.info(
                    f"{latest_part.title} 非院线发行日期: {next_air_date if next_air_date else '暂无'}，不符合提醒条件"
                )
                continue

            msg_title = f"🆕 {followinfo.get('name')} 有新的电影即将上线！"
            msg_text = (
                f"🎬 最新电影：{latest_part.title_year}\n"
                f"{msg}\n"
                f"📅 日期：{next_air_date[:10]}\n\n"
                f"👉 是否订阅该系列的最新作品？"
            )

            self._send_menu_message(
                latest_part, msg_title, msg_text, air_date=next_air_date
            )

    def _get_collection_id(self, mediainfo: MediaInfo) -> tuple[int | None, str | None]:
        """获取媒体的合集ID"""
        tmdb_info = mediainfo.tmdb_info

        collection_id = tmdb_info["belongs_to_collection"].get("id")
        if not collection_id:
            logger.warn(
                f"{mediainfo.tmdb_id} {mediainfo.title_year} 未获取到所属合集ID, 等待下次检查"
            )

        return collection_id, tmdb_info["belongs_to_collection"].get("name")

    def _should_track_media(self, mediainfo: MediaInfo) -> bool:
        """判断是否在跟进时间范围内"""
        air_date = mediainfo.last_air_date or mediainfo.release_date
        if not air_date or not self.is_date_in_range(
            air_date, datetime.now(), 365 * self.config.threshold_years
        ):
            logger.info(
                f"{mediainfo.title_year} 已超过设定年限: {self.config.threshold_years} 年，不再跟进"
            )
            return False

        return True

    def find_earliest_date(self, tmdbid: int):
        results = TmdbApi().movie.release_dates(tmdbid) or []
        _release_date, iso_3166_1, note, _type = "9999-12-31T23:59:59.999Z", "", "", 4
        for result in results:
            for _d in result.get("release_dates", []):
                if (
                    _d.get("type", 0) > 3
                    and (_date := _d.get("release_date"))
                    and _date < _release_date
                ):
                    _release_date, iso_3166_1, note, _type = (
                        _date,
                        result.get("iso_3166_1"),
                        _d.get("note"),
                        _d.get("type"),
                    )
        return (
            _release_date if _release_date != "9999-12-31T23:59:59.999Z" else None,
            self.movie_release_info(iso_3166_1, note, _type),
        )

    def _need_follow_up(
        self, ignore: set[tuple[str, str]], collections: dict[str, dict]
    ) -> set[tuple[str, str]]:
        # 订阅
        subscriptions = {
            (sub.type, sub.media_id)
            for sub in SubscribeOper().list()
            if normalize_media_source(sub.media_source) == MediaSource.TMDB
            and sub.media_id
        }
        # 已发送跟进通知
        notified_items = {
            _key for data in self.get_data() if (_key := self.parse_key(data.key))
        }

        # 移除已订阅
        already_subscribed_items = (ignore | notified_items) & subscriptions
        if already_subscribed_items:
            logger.debug(f"清理 {len(already_subscribed_items)} 个已订阅的忽略项")
            for item in already_subscribed_items:
                ignore.discard(item)
                self.del_data(self.build_key(*item))
            self.save_ignore_keys(ignore)

        # 排除已订阅 已发送未处理的条目
        ignore |= subscriptions | notified_items

        # 检索排除包含合集中的条目
        excluded_items = {
            _key
            for collection in collections.values()
            if (parts := collection.get("parts"))
            for k in parts
            if (_key := self.parse_key(k))
        }.union(ignore)

        # 媒体服务器
        serveritems = self.get_media_server_items(exclude=excluded_items) or set()
        subscribehis = (
            {
                (sub.type, str(sub.media_id))
                for sub in self.get_subscribe_history(exclude=excluded_items)
                if normalize_media_source(sub.media_source) == MediaSource.TMDB
                and sub.media_id
            }
            if self.config.check_sub_history
            else set()
        )
        return serveritems.union(subscribehis)

    @staticmethod
    def _subscribed_keys() -> set[tuple[str, str]]:
        """当前已存在的订阅键集合，用于追加订阅前的幂等判断。"""
        keys: set[tuple[str, str]] = set()
        try:
            for sub in SubscribeOper().list():
                if (
                    normalize_media_source(sub.media_source) != MediaSource.TMDB
                    or not sub.media_id
                ):
                    continue
                keys.add((sub.type, str(sub.media_id)))
        except Exception as e:
            logger.error(f"读取订阅列表失败: {e!s}")
        return keys

    @eventmanager.register(EventType.MessageAction)
    def message_action(self, event: Event):
        """
        处理消息按钮回调
        """
        event_data = event.event_data
        if not event_data or event_data.get("plugin_id") != self.__class__.__name__:
            return

        text_parts = (event_data.get("text") or "").split("|", 1)
        if len(text_parts) < 2:
            return
        action, _key = text_parts

        handler_map = {"add": self._handle_add, "ignore": self._handle_ignore}
        if handler := handler_map.get(action):
            handler(
                event_data.get("channel"),
                event_data.get("source"),
                event_data.get("userid"),
                event_data.get("original_message_id"),
                event_data.get("original_chat_id"),
                _key,
            )

    def _send_menu_message(
        self, mediainfo: MediaInfo, title: str, text: str, air_date: str | None = None
    ):
        """
        发送主菜单
        """
        _key = self.build_key(mediainfo.type.value, mediainfo.tmdb_id)
        buttons = [
            [
                {
                    "text": "📼 追加订阅",
                    "callback_data": f"[PLUGIN]{self.__class__.__name__}|add|{_key}",
                },
                {
                    "text": "💤 不再提醒",
                    "callback_data": f"[PLUGIN]{self.__class__.__name__}|ignore|{_key}",
                },
            ]
        ]
        self.post_message(
            title=title, text=text, mtype=MessageType.Plugin, buttons=buttons
        )
        self.save_data(_key, self.clean_media_info(mediainfo, air_date=air_date))

    def _handle_add(self, channel, source, userid, original_message_id, original_chat_id, _key: str):
        success, msg = self._do_add(_key)
        if success:
            self.chain.delete_message(channel, source, original_message_id, original_chat_id)
            return
        # 失败时发送重试按钮；数据已过时则不再给重试入口（与旧版行为一致）
        buttons = (
            None
            if msg == "信息已过时"
            else [[
                {"text": "📼 重试", "callback_data": f"[PLUGIN]{self.__class__.__name__}|add|{_key}"},
                {"text": "💤 忽略", "callback_data": f"[PLUGIN]{self.__class__.__name__}|ignore|{_key}"}
            ]]
        )
        self.post_message(channel=channel, title="添加订阅失败", text=f"原因: {msg}", userid=userid, buttons=buttons,
                          original_message_id=original_message_id, original_chat_id=original_chat_id)

    def _handle_ignore(self, channel, source, userid, original_message_id, original_chat_id, _key):
        success, msg = self._do_ignore(_key)
        self.post_message(
            channel=channel,
            source=source,
            title=msg,
            userid=userid,
            original_message_id=original_message_id,
            original_chat_id=original_chat_id
        )

    @staticmethod
    def _normalize_subscription_payload(data: dict) -> dict:
        """将插件存量 TMDB 身份字段投影为 V3 媒体身份合同。"""
        payload = dict(data)
        legacy_tmdb_id = payload.pop("tmdbid", None)
        payload.pop("doubanid", None)
        payload.pop("bangumiid", None)

        media_source = normalize_media_source(payload.get("media_source"))
        media_id = str(payload.get("media_id") or "").strip()
        if not media_source and legacy_tmdb_id:
            media_source = MediaSource.TMDB
            media_id = str(legacy_tmdb_id).strip()

        if media_source and media_id and media_id != "0":
            payload["media_source"] = media_source
            payload["media_id"] = media_id
        else:
            payload.pop("media_source", None)
            payload.pop("media_id", None)
        return payload

    def _do_add(self, _key: str) -> tuple[bool, str]:
        """执行追加订阅逻辑，返回 (success, message)"""
        data = self.get_data(_key) or {}
        if not data:
            return False, "信息已过时"

        # 幂等：已存在订阅则直接视为成功，并移除待确认条目
        key_tuple = self.parse_key(_key)
        if key_tuple and key_tuple in self._subscribed_keys():
            self.del_data(_key)
            return True, "已存在订阅"

        # 先归一化媒体身份（兼容旧数据），再只把订阅需要的字段传给 SubscribeChain，
        # 展示用字段不透传
        payload = {
            k: v
            for k, v in self._normalize_subscription_payload(data).items()
            if k in self._SUBSCRIBE_FIELDS
        }
        sid, msg = SubscribeChain().add(**payload, username=self.plugin_name)
        if sid:
            self.del_data(_key)
            return True, "订阅成功"
        return False, msg

    def _do_ignore(self, _key: str) -> tuple[bool, str]:
        """执行忽略逻辑，返回 (success, message)"""
        data = self.get_data(_key) or {}
        self.del_data(_key)
        self.update_ignore_keys(_key)

        # 记录展示信息，便于在插件页面查看"已忽略了什么"
        key_tuple = self.parse_key(_key)
        if key_tuple:
            meta = self.get_ignore_meta()
            meta[_key] = {
                "title": data.get("title") or "",
                "year": data.get("year") or "",
                "type": key_tuple[0],
                "poster": data.get("poster") or "",
                "air_date": str(data.get("air_date") or "")[:10],
                "synced": True,
                "ignored_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            self.save_ignore_meta(meta)

        title = data.get('title', _key)
        year = data.get('year', '')
        return True, f"已忽略订阅 {title} ({year})" if year else f"已忽略订阅 {title}"

    def _do_unignore(self, _key: str) -> tuple[bool, str]:
        """取消忽略：把条目从忽略列表移除，返回 (success, message)"""
        key_tuple = self.parse_key(_key)
        if not key_tuple:
            return False, "无效的条目"

        ignore = self.get_ignore_keys()
        if key_tuple not in ignore:
            return False, "该条目不在忽略列表中"

        meta = self.get_ignore_meta()
        info = meta.pop(_key, None) or {}

        ignore.discard(key_tuple)
        self.save_ignore_keys(ignore)
        self.save_ignore_meta(meta)

        title = info.get("title") or _key
        year = info.get("year") or ""
        return True, f"已取消忽略 {title} ({year})" if year else f"已取消忽略 {title}"

    def get_media_server_items(
        self, exclude: set[tuple[str, str]] = set()
    ) -> set[tuple[str, str]]:
        # 获取所有媒体服务器
        mediaservers = ServiceConfigHelper.get_mediaserver_configs()
        if not mediaservers:
            # 未配置媒体服务器时返回空集合，避免调用方 union 时崩溃
            return set()
        items = set()
        serverchain = MediaServerChain()
        # 遍历媒体服务器
        for mediaserver in mediaservers:
            if not mediaserver:
                continue
            if not mediaserver.enabled:
                continue
            server_name = mediaserver.name
            libraries = serverchain.librarys(server_name)
            if not libraries:
                continue
            for library in libraries:
                if library.id not in self.config.libraries:
                    continue
                logger.info(f"正在获取 {server_name} 媒体库 {library.name} ...")

                for item in serverchain.items(
                    server=server_name, library_id=library.id
                ):
                    if not item:
                        continue
                    # 用统一身份解析，兼容不同媒体服务器返回的字段形态
                    source, media_id = resolve_media_identity(media=item)
                    if source != MediaSource.TMDB or not media_id:
                        continue
                    # 类型
                    item_type = (
                        "电视剧" if item.item_type in ["Series", "show"] else "电影"
                    )
                    # 插入数据
                    if (_key := (item_type, str(media_id))) not in exclude:
                        items.add(_key)
        return items

    def clean_media_info(self, mediainfo: MediaInfo, air_date: str | None = None) -> dict:
        """
        清洗 mediainfo 对象，仅保留关键字段用于存储或传输。

        返回的字典同时承担两个角色：
        - `_SUBSCRIBE_FIELDS` 内的字段会原样传给 SubscribeChain.add；
        - 其余字段（type / episode_number / air_date / poster / created_at）仅用于插件页面展示。
        """
        if not mediainfo:
            return {}
        next_episode = mediainfo.next_episode_to_air or {}

        # 季号优先取即将播出集所属的季，取不到再退回总季数
        season = next_episode.get("season_number") or mediainfo.number_of_seasons or 0
        episode_number = next_episode.get("episode_number") or 0

        # 开始集数优先使用 next_episode_to_air 中的 episode_number
        if episode_number:
            start_episode = episode_number
        else:
            # 查询订阅历史
            history = self.get_subscribe_history(
                tmdbid=str(mediainfo.tmdb_id), type=mediainfo.type
            )
            total_episode = next(
                (item.total_episode for item in history if item.season == season), 0
            )
            start_episode = total_episode + 1 if total_episode else 0

        display_air_date = str(air_date or next_episode.get("air_date") or "")[:10]

        return {
            "title": mediainfo.title,
            "year": mediainfo.year,
            "media_source": MediaSource.TMDB.value,
            "media_id": str(mediainfo.tmdb_id),
            "episode_group": mediainfo.episode_group,
            "season": season,
            "start_episode": start_episode,
            # 以下仅用于插件页面展示
            "type": mediainfo.type.value,
            "episode_number": episode_number,
            "air_date": display_air_date,
            "poster": mediainfo.poster_path or "",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    def get_ignore_keys(self) -> set[tuple[str, str]]:
        _keys = self.get_data("ignore_keys") or []
        return {self.parse_key(key) for key in _keys}

    def save_ignore_keys(self, keys: set[tuple[str, str]]):
        _keys = [self.build_key(*key) for key in keys]
        self.save_data("ignore_keys", _keys)

    def get_ignore_meta(self) -> dict:
        """已忽略条目的展示信息 {key: {title, year, type, ignored_at}}。"""
        meta = self.get_data(self._IGNORE_META_KEY)
        return meta if isinstance(meta, dict) else {}

    def save_ignore_meta(self, meta: dict):
        self.save_data(self._IGNORE_META_KEY, meta)

    def update_ignore_keys(self, key: tuple[str, str] | str):
        """将 key 添加到忽略列表中"""
        if isinstance(key, str):
            key = self.parse_key(key)
            if not key:
                return
        self.save_ignore_keys(self.get_ignore_keys().union({key}))

    def get_collections(self) -> dict[str, dict]:
        return self.get_data("collections") or {}

    def save_collections(self, collections: dict):
        self.save_data("collections", collections)

    def get_subscribe_history(
        self,
        tmdbid: str | None = None,
        type: MediaType | None = None,
        exclude: set[tuple[str, str]] | None = None,
    ) -> list[SubscriptionHistorySnapshot]:
        """通过订阅历史 Oper 查询并投影 TMDB 来源记录。"""
        try:
            filters = SubscriptionHistoryFilter(
                media_source=MediaSource.TMDB if tmdbid else None,
                media_id=tmdbid if tmdbid else None,
                media_types=(type,) if type else (),
            )
            page_size = 200
            page_number = 1
            histories: list[SubscriptionHistorySnapshot] = []
            while True:
                records, total = SubscribeHistoryOper().query(
                    filters=filters,
                    page=QueryPageRequest(
                        page=page_number,
                        count=page_size,
                        sort=QuerySort(
                            field=QuerySortField.ID,
                            direction=QuerySortDirection.ASC,
                        ),
                    ),
                )
                for record in records:
                    snapshot = SubscriptionHistorySnapshot.model_validate(record)
                    if (
                        snapshot.media_source != MediaSource.TMDB
                        or not snapshot.media_id
                    ):
                        continue
                    identity = (snapshot.type, snapshot.media_id)
                    if exclude and identity in exclude:
                        continue
                    histories.append(snapshot)
                if page_number * page_size >= total:
                    break
                page_number += 1
            return histories
        except Exception as e:
            logger.error(f"获取订阅历史失败: {e!s}")
            return []

    @staticmethod
    def build_key(mtype: str, tmdbid: str | int) -> str:
        return f"{mtype}.{tmdbid}"

    @staticmethod
    def parse_key(key_str: str) -> tuple[str, str] | None:
        try:
            type_str, tmdbid_str = key_str.split(".", 1)
            return type_str, tmdbid_str
        except ValueError:
            return None
        except Exception as e:
            logger.warn(f"解析key失败: {key_str}, 错误: {e!s}")
            return None

    @staticmethod
    def movie_release_info(iso_code: str, note, type_id) -> str:
        type_name = {4: "数字发行", 5: "实体发行", 6: "电视播放"}
        iso_to_country_cn = {
            "US": "美国",
            "GB": "英国",
            "FR": "法国",
            "DE": "德国",
            "JP": "日本",
            "KR": "韩国",
            "CN": "中国",
            "HK": "中国香港",
            "TW": "中国台湾",
        }
        return (
            f"🌍 地区：{iso_to_country_cn.get(iso_code.upper(), '未知地区')}\n"
            f"📼 渠道：{note or '未知'}\n"
            f"🏷️ 类型：{type_name.get(int(type_id), '未知发行渠道')}"
        )

    @staticmethod
    def is_date_in_range(
        air_date: datetime | str,
        reference_date: datetime | str | None = None,
        threshold_days: int = 2,
    ) -> bool:
        """
        两个日期接近或在未来指定天数内

        :param air_date: 目标日期
        :param reference_date: 参考日期
        :param threshold_days: 阈值天数
        :return: bool

        只传入 target_date 时，判断是否在未来 threshold_days 天内
        传入 target_date 和 reference_date 时，判断两个日期是否接近
        """
        try:
            # 解析目标日期
            if isinstance(air_date, datetime):
                date1 = air_date.date()
            elif isinstance(air_date, str):
                date1 = datetime.strptime(air_date[:10], "%Y-%m-%d").date()
            else:
                date1 = datetime.now().date()

            # 单日期模式：是否在未来threshold_days内
            if reference_date is None:
                today = datetime.now().date()
                delta = (date1 - today).days
                return 0 <= delta <= threshold_days

            # 双日期模式：两个日期是否接近
            if isinstance(reference_date, datetime):
                date2 = reference_date.date()
            elif isinstance(reference_date, str):
                date2 = datetime.strptime(reference_date[:10], "%Y-%m-%d").date()
            # 天数差
            delta = (date1 - date2).days
            return abs(delta) <= threshold_days

        except (ValueError, TypeError) as e:
            logger.error(f"日期格式错误: {e!s}")
            return False
