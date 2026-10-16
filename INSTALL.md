# NF订阅兜底 安装指南

> 插件标识（目录名 / 类名 / package.v3.json 键）仍为 `FirstNF`，
> 仅**显示名**改为「NF订阅兜底」；升级安装不会影响既有实例绑定。

本文档说明两种安装路径：**A. 通过 MoviePilot MCP 安装**（首选，本会话已验证
`plugin.install` / `plugin.uninstall` 操作存在）；**B. 上传 GitHub 走插件市场
安装**（MCP 权限不足时的替代方案）。

---

## 0. 安装前准备（两条路径通用）

### 0.1 环境要求

| 项 | 要求 |
| --- | --- |
| MoviePilot | V3（`system_version: ">=3.0.0"`，插件已声明） |
| NextFind | 独立服务，OpenAPI 可达（默认 `http://<nf-host>:8092/api/openapi`，头 `X-API-Key`） |
| 115 网盘 | 已在 NextFind 侧完成绑定与转存授权（凭据不经过本插件） |
| 媒体库 | 若启用"转存后库扫描"，需已配置媒体服务器 |

### 0.2 版本一致性检查（必做）

官方门禁要求三处版本一致：插件类 `plugin_version`、`package.v3.json` 的
`version`、`history` 顶部记录。本仓库交付时三者均为 `1.0.0`，修改任意一处的
同时必须同步另外两处。

### 0.3 本地自检（可选但推荐）

```bash
# 语法编译
python -m compileall -q plugins.v3 tests
# 单元测试（无需宿主，纯逻辑层）
python -m pytest tests/v3/firstnf -v
```

### 0.4 权限与安全说明

- **MCP 侧**：`plugin.install` 需要在已连接的 MoviePilot MCP 服务上具备插件
  安装权限；安装动作会改动运行中的宿主，属于破坏性写操作，执行前需确认目标
  实例正确。
- **GitHub 侧**：仓库需为公开仓库（插件市场经 `raw.githubusercontent.com`
  读取），不要把任何凭据（NF API Key、115 Cookie）提交进仓库。
- **运行时**：插件只读宿主订阅（`SubscribeOper`）、写插件自有数据区；
  不修改宿主配置与数据库核心表。

---

## 方案 A：通过 MCP 安装

### A.1 前置条件

1. 本会话的 MoviePilot MCP 已连接到目标实例（当前已验证可用：
   `mcp__mp__moviepilot_api` 暴露 `plugin.install` / `plugin.uninstall`）。
2. 插件源码已托管在一个可访问的 Git 仓库（GitHub `main` 分支）：
   - `plugins.v3/firstnf/`（含 `__init__.py`、`pyproject.toml`、`README.md`、
     `nfcore/`）
   - `package.v3.json`（键名 `FirstNF`）
   - 目录名 `firstnf` = 主类名 `FirstNF` 的小写（官方强制对应关系）
3. **重要待验证点**：MCP `plugin.install` 的 `repo_url` 参数描述为
   "Approved plugin repository URL"（已批准的仓库）。是否允许任意第三方
   公开仓库尚未逐一验证——若安装被拒绝（提示仓库未批准/不受信任），
   转方案 B。

### A.2 安装步骤

1. **安装**：
   ```
   plugin.install
     path_params: { "plugin_id": "FirstNF" }
     query: { "repo_url": "https://github.com/<user>/<repo>", "force": false }
   ```
   - 若市场索引需要先刷新，可加 `force: true`。
   - `release_version` 仅在需要指定精确版本时使用。
2. **启用与配置**：MCP 当前未暴露插件启停操作，需在 MoviePilot Web UI
   「插件管理」中启用 FirstNF，并填写配置：
   - NextFind 地址与 API Key
   - 115 转存目标目录（如 `/我的接收/moviepilot/tv`）
   - 运行模式：竞速（race，推荐）/ 严格（strict）
   - 超时与轮询参数（默认值见 `get_form`）
3. **启用后**：插件注册 5 分钟周期的看门狗服务；首次新增电视剧订阅时自动
   触发 NF 流程。

### A.3 安装后验证

按可靠性从高到低：

1. **插件 API 验证**（需 bearer token，在 MP Web UI 的接口调试或外部调用）：
   ```
   GET /api/v1/plugin/FirstNF/status
   → {"enabled": true, "gate_capability": "unavailable",
      "active_tasks": 0, "terminal_tasks": 0, "total_tasks": 0}
   ```
   `gate_capability: "unavailable"` 为预期值（宿主无原生 gate，竞速模式）。
2. **任务明细**：`GET /api/v1/plugin/FirstNF/tasks` 查看任务状态机记录
   （终态应为 `native_refresh_allowed` / `no_match` / `transfer_failed` 等）。
3. **MCP 只读诊断**：`mcp__mp__query_doctor_report`（read-only）确认无插件
   加载错误；`mcp__mp__database_operation` 可查插件配置表确认配置已落库。
4. **端到端**：新增一部电视剧订阅（非洗版），观察：
   - 插件详情页出现 `gate_acquiring → nf_searching → nf_grabbing →
     library_refresh → releasing → native_refresh_allowed` 阶段推进；
   - NextFind 侧出现「已加入第一队列等待执行首次全量搜索」日志与转存记录，
     115 目标目录出现资源；
   - 任务终态后 NextFind 订阅列表不再包含该剧（插件已移除 NF 订阅，
     交还追更主权给 MP/PT）；
   - MoviePilot 对该订阅执行过一次定向补搜（PT 接管补缺）；
   - 洗版订阅新增时任务直接 `ignored`，不出现任何 NF 调用。
5. **失败演练**：把 NF 地址临时改错，新增订阅应快速进入 `no_match` 并触发
   原生补搜（订阅不停滞）。

### A.4 卸载

```
plugin.uninstall
  path_params: { "plugin_id": "FirstNF" }
```

---

## 方案 B：上传 GitHub，走插件市场安装

当 MCP 权限不足以安装（例如 `repo_url` 不被接受、MCP 未连接目标实例、
或需要让其他 MP 实例也能安装）时使用本方案。

### B.1 可行条件

1. **公开 GitHub 仓库**，`main` 分支包含：
   ```
   plugins.v3/firstnf/__init__.py
   plugins.v3/firstnf/pyproject.toml
   plugins.v3/firstnf/README.md
   plugins.v3/firstnf/nfcore/*.py
   package.v3.json
   ```
   （插件市场只读取 GitHub 仓库 `main` 分支，多地址用英文逗号分隔。）
2. **版本三处一致**（`plugin_version` / `package.v3.json` version / history）。
3. MoviePilot 容器可访问 `raw.githubusercontent.com`（国内网络需自备代理）。
4. 将仓库地址加入 MoviePilot 的 `PLUGIN_MARKET` 环境变量（多个用 `,` 分隔，
   官方仓库在前）：
   ```
   PLUGIN_MARKET=https://github.com/jxxghp/MoviePilot-Plugins,https://github.com/<user>/<repo>
   ```
   ⚠️ 修改环境变量需要**重建/重启容器**才能生效。
5. 重启后在 MoviePilot Web UI「插件市场」中即可看到 FirstNF（分类"订阅"），
   点击安装 → 启用 → 配置（配置项同 A.2 第 2 步）。

### B.2 操作流程

1. 创建公开仓库，按 B.1 结构提交全部文件并推到 `main`。
2. 修改 MoviePilot 部署配置（docker-compose `environment` 或 Portainer 等）
   加入 `PLUGIN_MARKET`。
3. 重建容器（`docker compose up -d`）。
4. Web UI → 插件市场 → 找到 FirstNF → 安装。
5. 启用并完成配置；验证步骤同 A.3。

### B.3 潜在限制

| 限制 | 说明 |
| --- | --- |
| 网络可达性 | 国内直连 GitHub raw 常失败，需容器代理或镜像加速 |
| 环境变量修改 | 必须重启容器，非 MCP 可代劳（除非 MCP 暴露宿主配置写操作） |
| 市场刷新延迟 | 索引按仓库 `main` 读取，提交后需等待市场刷新或强制刷新 |
| 版本回滚 | 市场按版本安装，回滚需在仓库恢复旧版本并重新安装 |
| 第三方仓库信任 | 自行承担第三方代码风险；建议 fork 后固定 commit 定期同步 |

### B.4 与方案 A 的区别

| 维度 | A. MCP 安装 | B. GitHub 市场安装 |
| --- | --- | --- |
| 触发方式 | MCP `plugin.install` 直接安装 | 改 `PLUGIN_MARKET` + 重启 + UI 安装 |
| 是否需要重启 | 否（热安装） | 是（环境变量变更需重建容器） |
| 前置依赖 | MCP 已连接且具备插件安装权限 | 公开仓库 + 容器网络可达 GitHub |
| 适用范围 | 单个已连接实例 | 任意配置了该市场的实例 |
| 主要风险 | `repo_url` 审批策略未逐一验证 | 网络/重启/市场刷新延迟 |
| 验证手段 | 插件 API + MCP 只读诊断 | 插件 API + UI 观察 |

> 两条路径最终都落到同一份插件代码与同一套验证步骤；若 MCP 安装被拒绝，
> 优先按 B 完成安装，再回到 A.3 的验证清单确认功能。

---

## 附：配置速查

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `enabled` | false | 启用插件 |
| `nf_base_url` | 空 | NextFind OpenAPI 地址 |
| `nf_api_key` | 空 | X-API-Key |
| `target_folder` | 空 | 115 转存目标目录 |
| `blocking_mode` | race | race=竞速（当前宿主无 gate）；strict=无 gate 能力时跳过 |
| `min_score` | 0.35 | 匹配置信度阈值（遗留直转存路径使用，主路径不参与） |
| `total_timeout` | 5400 | 任务总超时（秒） |
| `transfer_timeout` | 3600 | 转存确认超时（秒，遗留路径） |
| `nf_grab_settle` | 300 | NF 全量抓取「无资源」判定窗口（秒）：超过仍无集入库则判 no_match 释放 |
| `nf_grab_timeout` | 1800 | NF 全量抓取总等待上限（秒）：超限按 timeout 释放 |
| `poll_interval` | 60 | 抓取/转存轮询间隔（秒） |
| `library_scan_on_transfer` | false | 转存后触发媒体库扫描 |
| `cms_enabled` | false | 启用 CMS 联动（转存后通知 CMS 整理） |
| `cms_domain` | 空 | CMS 地址，如 `http://192.168.50.91:9527` |
| `cms_token` | 空 | CMS 配置页给出的 Webhook 令牌（默认 `cloud_media_sync`） |
| `cms_webhook_path` | /api/emby/webhook | CMS Webhook 路径 |
| `notify` | true | 终态发送通知 |

> **主路径说明（v1.0.8 起）**：NF 的资源管线由 NF 订阅驱动（`/resources/search`
> 只返回已完成匹配的待转存候选）。插件在首次订阅时 `POST /subscriptions/add`
> 让 NF 执行全量搜索+转存，轮询 `local_episodes` 至稳定后
> `POST /subscriptions/remove` 交还追更主权给 MP/PT，再触发原生定向补搜。
> `min_score` / `resolution_preference` / `whitelist` / `blacklist` 仅遗留
> 直转存路径使用，主路径不参与（质量由 NF 侧规则控制）。

> **CMS 联动说明（v1.0.9 起）**：NF 抓取完成（`LIBRARY_REFRESH` 阶段）时，
> 若 `cms_enabled` 为真，插件会向
> `POST {cms_domain}{cms_webhook_path}?token={cms_token}` 发送 Emby 入库事件载荷，
> 触发 CMS 的整理流程——与已安装的 CMSNotify 插件使用的是同一通道。
> 该调用失败非致命（只记录 `cms_notify_failed`，不阻塞释放与 PT 接管）。
> 获取 token：打开 CMS 配置页，复制其给出的 Emby 入库通知 Webhook 地址中的
> `token` 参数值（默认即 `cloud_media_sync`）。
