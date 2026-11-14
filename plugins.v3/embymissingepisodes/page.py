"""Vuetify JSON 页面：配置表单、缺集报告页与通知摘要。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

# 报告页每个分组最多展示的行数，完整数据可通过插件 /report 接口获取
MAX_ROWS = 400


def _col(content: List[dict], **props: Any) -> dict:
    """生成栅格列。"""
    return {"component": "VCol", "props": props or {"cols": 12}, "content": content}


def _row(*cols: dict) -> dict:
    """生成栅格行。"""
    return {"component": "VRow", "content": list(cols)}


def _switch(model: str, label: str, hint: str = "", md: int = 4) -> dict:
    """生成开关字段列。"""
    props: Dict[str, Any] = {"model": model, "label": label}
    if hint:
        props.update({"hint": hint, "persistent-hint": True})
    return _col([{"component": "VSwitch", "props": props}], cols=12, md=md)


def _text(model: str, label: str, hint: str = "", md: int = 4, **extra: Any) -> dict:
    """生成文本输入列。"""
    props: Dict[str, Any] = {"model": model, "label": label, **extra}
    if hint:
        props.update({"hint": hint, "persistent-hint": True})
    return _col([{"component": "VTextField", "props": props}], cols=12, md=md)


def _section(title: str) -> dict:
    """生成分组标题行。"""
    return _row(
        _col(
            [
                {
                    "component": "div",
                    "props": {"class": "text-subtitle-1 font-weight-bold mt-2"},
                    "text": title,
                }
            ]
        )
    )


def build_form(server_items: List[str], library_items: Optional[List[str]] = None) -> List[dict]:
    """生成插件配置页面。"""
    library_items = library_items or []
    return [
        {
            "component": "VForm",
            "content": [
                _row(
                    _switch("enabled", "启用插件"),
                    _switch("notify", "扫描完成后通知"),
                    _switch("onlyonce", "保存后立即扫描一次"),
                ),
                _row(
                    _col(
                        [
                            {
                                "component": "VCronField",
                                "props": {
                                    "model": "cron",
                                    "label": "定时扫描周期",
                                    "placeholder": "5 位 cron 表达式，留空不定时",
                                },
                            }
                        ],
                        cols=12,
                        md=4,
                    ),
                    _col(
                        [
                            {
                                "component": "VSelect",
                                "props": {
                                    "model": "servers",
                                    "label": "Emby 服务器",
                                    "items": server_items,
                                    "multiple": True,
                                    "chips": True,
                                    "clearable": True,
                                    "hint": "留空表示全部已启用的 Emby 服务器",
                                    "persistent-hint": True,
                                },
                            }
                        ],
                        cols=12,
                        md=4,
                    ),
                    _col(
                        [
                            {
                                "component": "VCombobox",
                                "props": {
                                    "model": "libraries",
                                    "label": "媒体库名称",
                                    "items": library_items,
                                    "multiple": True,
                                    "chips": True,
                                    "clearable": True,
                                    "hint": "留空表示全部电视剧库，可手动输入其他名称",
                                    "persistent-hint": True,
                                },
                            }
                        ],
                        cols=12,
                        md=4,
                    ),
                ),
                _section("缺集判定"),
                _row(
                    _text(
                        "air_buffer_days",
                        "播出缓冲天数",
                        "播出超过该天数才计入缺集",
                        type="number",
                    ),
                    _switch("include_specials", "检查第 0 季（特别篇）"),
                    _switch(
                        "only_existing_seasons",
                        "只检查库中已有的季",
                        "关闭后整季缺失也会报告",
                    ),
                ),
                _row(
                    _text(
                        "max_series",
                        "单次扫描剧集上限",
                        "0 表示不限制；达到上限时剩余剧集留到下次扫描",
                        type="number",
                    ),
                ),
                _row(
                    _col(
                        [
                            {
                                "component": "VAlert",
                                "props": {
                                    "type": "info",
                                    "variant": "tonal",
                                    "text": (
                                        "插件只读取媒体服务器的剧集季集与 TMDB 已播出集号，生成缺集报告，"
                                        "不会自动下载或订阅。报告页的「搜索」跳转 MoviePilot 搜索页，"
                                        "「订阅」按季添加订阅，实际补全仍由订阅流程完成。"
                                    ),
                                },
                            }
                        ]
                    )
                ),
            ],
        }
    ]


def _row_key(row: Dict[str, Any]) -> str:
    """生成条目唯一键，用于忽略标记。"""
    return f"{row.get('media_id')}:{int(row.get('season') or 0)}"


# 对外暴露的条目键函数，供插件主体复用
row_key = _row_key


def _row_actions(row: Dict[str, Any], plugin_id: str, ignored: bool) -> List[dict]:
    """生成缺集行的搜索、订阅与忽略按钮。"""
    keyword = quote(str(row.get("title") or ""))
    actions: List[dict] = [
        {
            "component": "VBtn",
            "props": {
                "size": "small",
                "variant": "tonal",
                "color": "primary",
                "class": "me-1",
                "href": f"#/search?keyword={keyword}",
                "target": "_blank",
                "prepend-icon": "mdi-magnify",
            },
            "text": "搜索",
        },
        {
            "component": "VBtn",
            "props": {
                "size": "small",
                "variant": "tonal",
                "color": "secondary",
                "prepend-icon": "mdi-bell-plus",
            },
            "text": "订阅本季",
            "events": {
                "click": {
                    "api": f"plugin/{plugin_id}/subscribe",
                    "method": "post",
                    "params": {
                        "title": row.get("title"),
                        "year": row.get("year"),
                        "season": row.get("season"),
                        "media_source": row.get("media_source"),
                        "media_id": row.get("media_id"),
                    },
                }
            },
        },
    ]
    if ignored:
        actions.append(
            {
                "component": "VBtn",
                "props": {
                    "size": "small",
                    "variant": "text",
                    "color": "default",
                    "prepend-icon": "mdi-undo",
                },
                "text": "取消忽略",
                "events": {
                    "click": {
                        "api": f"plugin/{plugin_id}/ignore",
                        "method": "post",
                        "params": {
                            "key": _row_key(row),
                            "title": row.get("title"),
                            "season": row.get("season"),
                            "remove": True,
                        },
                    }
                },
            }
        )
    else:
        actions.append(
            {
                "component": "VBtn",
                "props": {
                    "size": "small",
                    "variant": "text",
                    "color": "default",
                    "prepend-icon": "mdi-eye-off-outline",
                },
                "text": "忽略",
                "events": {
                    "click": {
                        "api": f"plugin/{plugin_id}/ignore",
                        "method": "post",
                        "params": {
                            "key": _row_key(row),
                            "title": row.get("title"),
                            "season": row.get("season"),
                            "remove": False,
                        },
                    }
                },
            }
        )
    return actions


def _episode_text(row: Dict[str, Any]) -> str:
    """把缺失集号列表压缩成可读文本。"""
    missing = [int(number) for number in row.get("missing") or []]
    if not missing:
        return ""
    if len(missing) <= 12:
        return "、".join(f"E{number:02d}" for number in missing)
    head = "、".join(f"E{number:02d}" for number in missing[:12])
    return f"{head} 等 {len(missing)} 集"


def _report_row(row: Dict[str, Any], plugin_id: str, status: str, ignored: bool) -> dict:
    """生成报告表格中的一行。"""
    location = row.get("server") or ""
    if row.get("library"):
        location = f"{location} / {row['library']}" if location else str(row["library"])
    title = str(row.get("title") or "")
    if row.get("year"):
        title = f"{title}（{row['year']}）"
    # 状态展示与配色
    status_map = {
        "missing": ("缺集", "error"),
        "subscribed": ("已订阅", "info"),
        "ignored": ("已忽略", "default"),
    }
    status_text, status_color = status_map.get(status, ("缺集", "error"))
    poster = str(row.get("poster") or "")
    poster_cell: List[dict] = (
        [
            {
                "component": "VImg",
                "props": {
                    "src": poster,
                    "height": 90,
                    "width": 60,
                    "aspect-ratio": "2/3",
                    "cover": True,
                    "class": "rounded",
                },
            }
        ]
        if poster
        else [
            {
                "component": "div",
                "props": {
                    "class": "d-flex align-center justify-center rounded bg-grey-lighten-3 text-grey",
                    "style": "height:90px;width:60px",
                },
                "content": [{"component": "VIcon", "props": {"icon": "mdi-television-classic-off"}}],
            }
        ]
    )
    return {
        "component": "tr",
        "props": {"class": "text-no-wrap" if ignored else ""},
        "content": [
            {"component": "td", "content": poster_cell},
            {
                "component": "td",
                "content": [
                    {"component": "div", "props": {"class": "font-weight-medium"}, "text": title},
                    {
                        "component": "div",
                        "props": {"class": "text-caption text-medium-emphasis"},
                        "text": location,
                    },
                ],
            },
            {
                "component": "td",
                "props": {"class": "text-no-wrap"},
                "content": [
                    {
                        "component": "VChip",
                        "props": {"size": "small", "color": "primary", "variant": "tonal"},
                        "text": f"S{int(row.get('season') or 0):02d}",
                    }
                ],
            },
            {
                "component": "td",
                "content": [
                    {"component": "span", "text": _episode_text(row)},
                    {
                        "component": "div",
                        "props": {"class": "text-caption text-medium-emphasis"},
                        "text": f"已播出 {row.get('aired') or 0} 集，库内 {row.get('existing') or 0} 集",
                    },
                ],
            },
            {
                "component": "td",
                "props": {"class": "text-no-wrap"},
                "content": [
                    {
                        "component": "VChip",
                        "props": {"size": "small", "color": status_color, "variant": "tonal"},
                        "text": status_text,
                    }
                ],
            },
            {
                "component": "td",
                "props": {"class": "text-no-wrap"},
                "content": _row_actions(row, plugin_id, ignored),
            },
        ],
    }


def _table(rows: List[dict]) -> dict:
    """生成缺集表格。"""
    return {
        "component": "VTable",
        "props": {"density": "compact", "hover": True},
        "content": [
            {
                "component": "thead",
                "content": [
                    {
                        "component": "tr",
                        "content": [
                            {"component": "th", "text": "海报"},
                            {"component": "th", "text": "媒体"},
                            {"component": "th", "text": "季"},
                            {"component": "th", "text": "缺失集"},
                            {"component": "th", "text": "状态"},
                            {"component": "th", "text": "操作"},
                        ],
                    }
                ],
            },
            {"component": "tbody", "content": rows},
        ],
    }


def build_page(
    plugin_id: str,
    report: Optional[Dict[str, Any]],
    progress: str = "",
    ignored_keys: Optional[List[str]] = None,
    subscribed_keys: Optional[List[str]] = None,
) -> List[dict]:
    """生成缺集报告页。

    :param ignored_keys: 已忽略条目键列表（"{media_id}:{season}"）
    :param subscribed_keys: 已订阅条目键列表（"{media_id}:{season}"）
    """
    ignored_keys = set(ignored_keys or [])
    subscribed_keys = set(subscribed_keys or [])
    content: List[dict] = []

    if progress:
        content.append(
            {
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "tonal",
                    "class": "mb-3",
                    "text": f"正在扫描：{progress}",
                },
            }
        )

    actions: List[dict] = [
        {
            "component": "VBtn",
            "props": {
                "color": "primary",
                "variant": "flat",
                "prepend-icon": "mdi-magnify-scan",
                "disabled": bool(progress),
            },
            "text": "立即扫描",
            "events": {
                "click": {
                    "api": f"plugin/{plugin_id}/scan",
                    "method": "post",
                    "params": {},
                }
            },
        }
    ]

    if not report:
        content.append(
            {
                "component": "VAlert",
                "props": {
                    "type": "warning",
                    "variant": "tonal",
                    "class": "mb-3",
                    "text": "还没有扫描结果，点击「立即扫描」开始检查已挂载媒体库的缺集。",
                },
            }
        )
        content.append({"component": "div", "props": {"class": "d-flex ga-2"}, "content": actions})
        return content

    rows = list(report.get("rows") or [])

    # 计算每行状态并分组
    def _status_of(row: Dict[str, Any]) -> str:
        if _row_key(row) in ignored_keys:
            return "ignored"
        if _row_key(row) in subscribed_keys:
            return "subscribed"
        return "missing"

    groups: Dict[str, List[Dict[str, Any]]] = {"missing": [], "subscribed": [], "ignored": []}
    for row in rows:
        groups[_status_of(row)].append(row)

    summary = (
        f"最近扫描：{report.get('scanned_at') or '-'}，"
        f"共 {report.get('series') or 0} 部剧，{len(rows)} 条缺集，"
        f"耗时 {report.get('duration') or 0} 秒"
    )
    content.append(
        {
            "component": "VAlert",
            "props": {
                "type": "success" if not rows else "warning",
                "variant": "tonal",
                "class": "mb-3",
                "text": summary,
            },
        }
    )
    if report.get("cancelled"):
        content.append(
            {
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "tonal",
                    "class": "mb-3",
                    "text": "上一次扫描被中断，结果为部分数据。",
                },
            }
        )
    for error in list(report.get("errors") or [])[:8]:
        content.append(
            {
                "component": "VAlert",
                "props": {
                    "type": "warning",
                    "variant": "tonal",
                    "density": "compact",
                    "class": "mb-2",
                    "text": str(error),
                },
            }
        )

    content.append({"component": "div", "props": {"class": "d-flex ga-2 mb-3"}, "content": actions})

    if not rows:
        content.append(
            {
                "component": "VAlert",
                "props": {
                    "type": "success",
                    "variant": "tonal",
                    "text": "没有发现缺集，媒体库已播出剧集齐全。",
                },
            }
        )
        return content

    # 状态筛选 Tab（服务端渲染各分组表格，避免依赖前端脚本）
    tab_defs = [
        ("missing", "待处理", groups["missing"], "error"),
        ("subscribed", "已订阅", groups["subscribed"], "info"),
        ("ignored", "已忽略", groups["ignored"], "default"),
        ("all", "全部", rows, "primary"),
    ]
    tabs_content: List[dict] = []
    windows_content: List[dict] = []
    for value, label, group_rows, chip_color in tab_defs:
        count = len(group_rows)
        tabs_content.append(
            {
                "component": "VTab",
                "props": {"value": value},
                "text": f"{label}（{count}）",
            }
        )
        shown = group_rows[:MAX_ROWS]
        if not shown:
            window_body: List[dict] = [
                {
                    "component": "VAlert",
                    "props": {
                        "type": "success",
                        "variant": "tonal",
                        "text": "该分组暂无条目。",
                    },
                }
            ]
        else:
            window_body = [
                _table(
                    [
                        _report_row(
                            row,
                            plugin_id,
                            value if value != "all" else _status_of(row),
                            _row_key(row) in ignored_keys,
                        )
                        for row in shown
                    ]
                )
            ]
            if count > len(shown):
                window_body.append(
                    {
                        "component": "div",
                        "props": {"class": "text-caption pa-2"},
                        "text": f"仅显示前 {len(shown)} 条，共 {count} 条；完整数据可调用插件 /report 接口获取。",
                    }
                )
        windows_content.append(
            {
                "component": "VWindowItem",
                "props": {"value": value},
                "content": window_body,
            }
        )

    content.append(
        {
            "component": "VTabs",
            "props": {"model": "_filter_tab", "density": "compact", "class": "mb-1"},
            "content": tabs_content,
        }
    )
    content.append(
        {
            "component": "VWindow",
            "props": {"model": "_filter_tab"},
            "content": windows_content,
        }
    )
    content.append(
        {
            "component": "div",
            "props": {"class": "text-caption pa-2 text-medium-emphasis"},
            "text": (
                "提示：订阅按季添加，实际补全由 MoviePilot 订阅流程完成；"
                "忽略只影响本插件报告展示，不会改动媒体库或订阅。"
            ),
        }
    )
    return content


def build_summary_text(report: Dict[str, Any], ignored_keys: Optional[List[str]] = None) -> str:
    """生成扫描完成通知的文本摘要，已忽略条目不计入提醒。"""
    ignored = set(ignored_keys or [])
    rows = [row for row in (report.get("rows") or []) if _row_key(row) not in ignored]
    ignored_count = len(report.get("rows") or []) - len(rows)
    lines = [
        f"扫描时间：{report.get('scanned_at') or '-'}",
        f"剧集数量：{report.get('series') or 0} 部",
        f"缺集条目：{len(rows)} 条",
    ]
    for row in rows[:10]:
        title = str(row.get("title") or "")
        if row.get("year"):
            title = f"{title}（{row['year']}）"
        lines.append(f"· {title} S{int(row.get('season') or 0):02d}：{_episode_text(row)}")
    if len(rows) > 10:
        lines.append(f"……另有 {len(rows) - 10} 条，详见插件报告页")
    if ignored_count:
        lines.append(f"已忽略 {ignored_count} 条（不提醒）")
    errors = list(report.get("errors") or [])
    if errors:
        lines.append(f"跳过/异常：{len(errors)} 条")
    return "\n".join(lines)
