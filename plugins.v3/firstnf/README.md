# FirstNF —— 首次订阅 NF 优先（MoviePilot V3 插件）

仅**首次新增电视剧订阅**时：优先经 NextFind（NF）搜索网盘资源并转存到 115，
转存确认后刷新媒体库状态，再触发 MoviePilot 原生定向补搜，由 PT 补全缺集并
承担后续追更。**洗版订阅**（`best_version=1`）与已有订阅的后续刷新/追更
不触发 NF 搜索、不拦截原生刷新。

## 重要边界（当前宿主能力）

- **MoviePilot V3 不存在原生订阅刷新拦截/gate 接口**（2026-10-16 源码核验）：
  插件默认以"竞速"模式运行——NF 流程与宿主自身的新订阅搜索并行，
  NF 转存完成后再触发定向补搜；不承诺严格顺序。
- NextFind OpenAPI 合同参考第三方实测文档（unisub，2026-07-22），
  接入前需以目标实例校准；NF 未配置时任务会快速失败并释放。
- 本插件不写宿主数据库、不修改宿主配置，运行数据仅存于插件数据区
  （`save_data` / 数据目录）。

## 目录结构

```text
plugins.v3/firstnf/
├── __init__.py      # 插件主类 FirstNF（宿主装配：事件、页面、服务、命令）
├── pyproject.toml   # 无额外第三方依赖（全部使用宿主提供能力）
├── README.md
└── nfcore/          # 可在宿主外独立测试的核心逻辑
    ├── state.py         # 状态机与任务记录
    ├── decision.py      # 首次订阅/洗版/类型准入判定
    ├── selection.py     # NF 候选择优
    ├── ports.py         # 端口抽象（gate / NF / 释放 / 媒体库 / 通知）
    ├── gate.py          # NullGate（当前）+ HostGateAdapter（未来接缝）
    ├── nfapi.py         # NextFind OpenAPI HTTP 适配器
    ├── store.py         # 任务持久化（宿主 / 文件 / 内存）
    └── orchestrator.py  # 状态机编排与看门狗
```

## 本地运行测试（无需宿主）

```bash
python -m pytest tests/v3/firstnf -v
```

宿主内测试请按官方规范以 `app.plugins.firstnf` 路径导入（见官方
《MoviePilot 插件开发指南（V3）》第 11 章）。
