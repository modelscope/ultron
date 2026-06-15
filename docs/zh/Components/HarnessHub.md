# HarnessHub（个人配置同步）

HarnessHub 是 Ultron 的个人工作空间同步与共享模块，支持在多个 Claw 产品（nanobot、openclaw、hermes 等）之间一键迁移和共享个人记忆、技能、人格配置。

## 核心概念

| 概念 | 说明 |
|---|---|
| **user_id** | 用户唯一标识 |
| **agent_id** | 设备/终端标识，同一用户可拥有多个设备 |
| **Claw** | 一个 `(user_id, agent_id)` 组合，代表某用户在某终端上的 agent 实例 |
| **Profile** | 存储在 Ultron 服务端的工作空间快照：`resources` 为相对路径到文本内容的映射；`product` 等为独立字段 |
| **Allowlist** | 定义每个 Claw 产品中哪些工作空间文件可被同步（排除敏感文件如 .env、auth.json） |
| **Bundle** | 将工作空间文件打包为 JSON 结构，用于传输和存储 |
| **Share Token** | 分享链接凭证，他人可通过 token 一键导入你的 agent 配置 |

## 同步模型

- 同步仅发生在**相同 `(user_id, agent_id)`** 的云端与本地之间
- 不同设备之间**不会自动同步**
- 用户可在 Dashboard 上管理自己的多个 agent_id
- 同步内容为个人工作空间文件（人格、记忆、技能等），**不包括聊天记录**

```
本地工作空间 ──sync up──▶ Ultron 服务端 ──sync down──▶ 本地工作空间
     │                        │
     │                        ▼
     │                  Share 短码 (6位)
     │                        │
     │              curl server/i/{code} | bash
     │                        │
     └────────────────────────┘
```

## 支持的 Claw 产品

| 产品 | 工作空间路径 | 同步文件 |
|---|---|---|
| nanobot | `~/.nanobot/workspace/` | AGENTS.md, SOUL.md, USER.md, TOOLS.md, HEARTBEAT.md, agents/&lt;name&gt;.md, memory/*.md, skills/*/* |
| openclaw | `~/.openclaw/workspace/`（或 `workspace-<name>`） | AGENTS.md, SOUL.md, USER.md, TOOLS.md, HEARTBEAT.md, IDENTITY.md, BOOTSTRAP.md, MEMORY.md, memory/*, skills/*/* |
| hermes | `~/.hermes/` | SOUL.md, memories/*.md, skills/*/*（含嵌套） |
| qwenpaw | `~/.qwenpaw/workspaces/<name>/` | AGENTS.md, SOUL.md, PROFILE.md, BOOTSTRAP.md, MEMORY.md, HEARTBEAT.md, memory/*.md, skills/*/* |
| openhuman | `~/.openhuman/workspace/` | SOUL.md, IDENTITY.md, USER.md, PROFILE.md, MEMORY.md, HEARTBEAT.md, wiki/*.md, skills/*/* |
| qoder | `~/.qoder/`（或项目内的 `.qoder/`） | AGENTS.md, agents/&lt;name&gt;.md, commands/*.md, rules/*.md, skills/*/* |

所有产品均**排除**：`.env`、`auth.json`、`sessions/`、`logs/`、隐藏文件。

不同产品的**子 agent 磁盘布局**不同——见下方 [`ultron upload` 命令行](#命令行ultron-upload) 一节的每框架对照表。

## 分享流程

1. 用户 A 执行 `sync up` 将工作空间上传到 Ultron
2. 用户 A 调用 `create share` 生成分享短码（6 位字母数字）
3. 用户 A 将短码发送给用户 B
4. 用户 B 在终端执行一行命令即可导入：

```bash
curl -sL https://your-server/i/Ab3xK9 | bash
```

同一 `(user_id, agent_id)` 在服务端**至多保留一条** share。创建 share 之后，若再次 `sync up`，`HarnessService` 会用当前 profile **刷新该 share 的快照**（短码通常不变），因此他人下次执行 `curl … | bash` 会得到**更新后的**工作区内容。

```
本地工作空间 ──sync up──▶ Ultron 服务端 ──create share──▶ 短码 Ab3xK9
                                                            │
                                                            ▼
                              curl -sL server/i/Ab3xK9 | bash
                                                            │
                                                            ▼
                                                     本地工作空间
```

## 命令行：`ultron upload`

`ultron` 命令行可以把单个子 agent 的文件上传到 agent 仓库，无需手写任何 HTTP
请求。只要指定 **框架**（bot 类型）和 **内部子 agent 名称**，它就会按各产品的
allowlist 自动在本地找到文件并上传；子 agent 名称同时作为仓库名（`agent_id`）。

```bash
# 1. 先登录一次（token 保存到 ~/.ultron/cli.json）
ultron login --server http://localhost:9999 --username alice

# 2. 上传一个子 agent（自动在框架默认路径下发现文件）
ultron upload --framework qoder --name reviewer

# 仅预览不上传，或指定自定义目录
ultron upload --framework qoder --name reviewer --dry-run
ultron upload --framework qwenpaw --name default --local_dir ~/.qwenpaw/workspaces/default

# 列出某框架在本地发现的所有子 agent
ultron upload --framework qoder --list
```

上传时，命令行会把该子 agent 的整个目录**打包成一个 zip**，通过
`POST /api/v1/files/upload`（`multipart/form-data`，字段 `file` + `Path`/`Name`/
`Framework`/`commit_message`）一次性提交。之所以用整目录快照而非逐文件提交，是因为
只有拿到完整文件集，服务端才能推断出**删除**（哪些文件被移除），而不仅仅是更新。

### 下载（可选格式转换）

`ultron download` 会拉取某子 agent 已存储的文件并写回本地工作空间。源框架会从仓库
中读取，因此通常只需 `--name`。下载分两步：先通过
`GET /api/v1/agents/{path}/{name}/repo/files` 取文件列表，再为每个文件获取下载链接并
逐个拉取。传入 `--target` 可在写回时把文件**转换**为另一框架的格式（例如你存的是
openclaw 的 agent，但想在 qwenpaw 下运行）：

```bash
# 还原到源框架的工作空间
ultron download --name reviewer

# 转换 openclaw -> qwenpaw 并写入 qwenpaw 工作空间
ultron download --name reviewer --target qwenpaw

# 预览，或写到其他位置
ultron download --name reviewer --target qwenpaw --dry-run
ultron download --name reviewer --local_dir /tmp/restore
```

### 本地转换（不上传/不下载）

`ultron convert` 在**纯本地文件**上执行同样的跨框架迁移——不涉及任何上传或下载。它
读取源框架的工作空间，转换为目标格式，并写出结果（默认写到目标框架的工作空间，或用
`--out` 指定）：

```bash
ultron convert --from nanobot --to hermes
ultron convert --from openclaw --to qwenpaw --local_dir ~/.openclaw/workspace --out /tmp/qwenpaw-ws
ultron convert --from nanobot --to openhuman --dry-run
```

转换由与服务端跨产品导入相同的引擎驱动（`ultron/services/harness/merge.py` 的
`merge_resources`）：语义等价的文件会被重映射到目标路径（例如 nanobot 的 `USER.md`
→ hermes 的 `memories/USER.md`），并与目标的默认模板合并。五个人格产品（nanobot、
openclaw、hermes、qwenpaw、openhuman）之间可干净互转；`qoder` 暂无语义映射，其
agent/command/rule 文件会原样保留。

`ULTRON_SERVER` / `ULTRON_TOKEN` 环境变量可覆盖已保存的凭证（便于 CI）。

一个框架可包含多个子 agent；命令行 **一次上传一个**，会收集所选子 agent 自身的
文件 **以及共享资源**（skills、rules、commands、`AGENTS.md`）。各框架布局：

| 框架 | 布局 | 子 agent `<name>` 位置 |
|------|------|------------------------|
| qwenpaw | 每个 agent 独立目录 | `~/.qwenpaw/workspaces/<name>` |
| openclaw | 每个 agent 独立目录 | `~/.openclaw/workspace`（默认）/ `workspace-<name>` |
| qoder | 单文件 + 共享 | `~/.qoder/agents/<name>.md` + 共享 `skills/`、`rules/`、`commands/`、`AGENTS.md` |
| nanobot | 单文件 + 共享 | `~/.nanobot/workspace/agents/<name>.md` + 共享 persona/memory/skills |
| hermes | 单 agent | `~/.hermes/`（name 仅作为仓库标识） |
| openhuman | 单 agent | `~/.openhuman/workspace/`（name 仅作为仓库标识） |

## 架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Nanobot   │     │  OpenClaw   │     │   Hermes    │
│  Allowlist  │     │  Allowlist  │     │  Allowlist  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────┬───────┘───────────────────┘
                   ▼
            HarnessBundle
                   │
                   ▼
          ┌────────────────┐
          │ HarnessService │
          └───────┬────────┘
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
   agents     profiles   shares
   (SQLite)   (SQLite)   (SQLite)
```

## 终端导入与恢复

导入由 **服务端** `GET /i/{short_code}` 返回的安装脚本完成，本机只需 `curl` 与 `bash`，**不依赖** 单独的 Python CLI：

```bash
curl -fsSL https://your-server/i/<short_code>?product=nanobot | bash
```

安装脚本会在覆盖前把已有工作区备份到 `~/.ultron/harness-import-backups/`，并在结束时打印用 `rm` / `mkdir` / `cp` 从备份恢复的命令。

- 在**交互式终端**（stdin 为 TTY）下，脚本会先询问是否继续导入；非交互环境（如管道）则直接继续，但仍会在非空工作区上做备份。
- 若快照中含 `skills/.ultron_modelscope_imports.json`（JSON 数组，元素可含 `full_name`），脚本会在写入文件前调用 `modelscope skills add` 安装对应技能，再复制到工作区 `skills/<name>/`。未安装 `modelscope` CLI 时脚本会失败退出。
- 查询参数 `product` 可与快照中的产品不一致；此时服务端会用 `merge_resources` 做跨产品合并（并配合各产品默认文件）。

上传、下载、创建分享等请使用 **Dashboard** 或下方 HTTP API。

## HTTP API 概要

除另有说明外，Harness 的**写操作与敏感读操作**需要 JWT（见本文末「认证」）。下列与 `ultron/api/routers/harness.py` 一致。

### 需 JWT

| 端点 | 说明 |
|------|------|
| `GET /harness/agents` | 列出当前用户的设备/agent |
| `DELETE /harness/agents` | 删除指定 `agent_id`（级联删除 profile 与 share） |
| `POST /harness/sync/up` | 上传工作区资源（body：`agent_id`、`product`、`resources`） |
| `POST /harness/sync/down` | 按 `agent_id` 拉取 profile |
| `GET /harness/profile?agent_id=…` | 获取单个 profile 详情 |
| `GET /harness/profiles` | 列出当前用户各 `agent_id` 的 profile 摘要 |
| `POST /harness/share` | 创建或刷新 share（无 profile 时 400） |
| `GET /harness/shares` | 列出当前用户的分享 |
| `DELETE /harness/share` | 按 `token` 删除分享 |
| `POST /harness/soul-presets/build` | 合并预设为 `resources`（body：`preset_ids` 数组） |

### 无需 JWT

| 端点 | 说明 |
|------|------|
| `GET /harness/defaults/{product}` | 产品默认工作区文件 |
| `GET /harness/soul-presets` | 按分类列出预设 |
| `GET /harness/soul-presets/{preset_id}` | 单个预设详情 |
| `GET /harness/showcase` | `lang` 查询参数：`zh` / `en` |
| `GET /harness/showcase/{slug}` | 单个展示案例 |
| `GET /harness/share/export/{token}` | 返回与短码相同的 shell 安装脚本（可用 `product` 覆盖目标产品） |
| `GET /i/{short_code}` | 按 6 位短码返回安装脚本（可用 `product` 查询参数） |

完整请求体与响应字段见 [HTTP API](../API/HttpAPI.md) 与 [SDK](../API/SDK.md)。

## 扩展新产品

添加新的 Claw 产品支持只需：

1. 在 `ultron/services/harness/allowlist.py` 中创建 `ClawWorkspaceAllowlist` 子类
2. 定义 `product_name`、`default_workspace_root`、`patterns`
3. （可选）重写 `list_agents()` 以支持多子 agent 发现
4. 注册到 `ALLOWLIST_REGISTRY`

基类是**子 agent 感知**的：构造函数接收 `agent_name`（所选子 agent）和可选的
`local_dir` 覆盖。`default_workspace_root` 可嵌入 `self.agent_name`（每 agent 独立
目录的产品），`patterns` 中的任意 `{name}` 占位符会用它格式化，从而只匹配所选子
agent 的文件（单文件 + 共享的产品）。单 agent 产品忽略该参数。

```python
class MyProductAllowlist(ClawWorkspaceAllowlist):
    @property
    def product_name(self) -> str:
        return "myproduct"

    @property
    def default_workspace_root(self) -> Path:
        # 每 agent 独立目录：嵌入子 agent 名；单 agent 则返回固定路径
        return Path.home() / ".myproduct" / "agents" / self.agent_name

    @property
    def patterns(self) -> List[str]:
        # 单文件 + 共享示例："{name}" 会被替换为子 agent 名
        return ["SOUL.md", "memory/*.md", "agents/{name}.md"]

ALLOWLIST_REGISTRY["myproduct"] = MyProductAllowlist
```

无论何种布局，`collect()` 都返回 `{工作空间相对路径: 文本}`，因此服务端、
`merge.py` 与控制台共用同一套键空间。控制台用 TypeScript 复刻了同样的逻辑
（`ultron/dashboard/src/components/harness/UploadWorkspace.tsx`），修改布局时请同步。

## 各产品文件模式详情

### nanobot

| 模式 | 说明 |
|---|---|
| `AGENTS.md` | Agent 指令 |
| `SOUL.md` | Agent 人格 |
| `USER.md` | 用户画像 |
| `TOOLS.md` | 工具定义 |
| `HEARTBEAT.md` | 定时任务 |
| `agents/{name}.md` | 所选子 agent（多 agent 布局） |
| `memory/MEMORY.md` | 长期记忆 |
| `memory/HISTORY.md` | 会话历史 |
| `skills/*/SKILL.md` | 技能定义 |
| `skills/*/_meta.json` | 技能元数据 |
| `skills/*/scripts/*` | 技能脚本 |
| `skills/*/setup.md` | 技能安装文档 |
| `skills/*/operations.md` | 技能操作文档 |
| `skills/*/boundaries.md` | 技能边界文档 |

### openclaw

每 agent 独立目录：默认 agent 在 `~/.openclaw/workspace`，命名 agent 在 `~/.openclaw/workspace-<name>`。

| 模式 | 说明 |
|---|---|
| `AGENTS.md` | Agent 指令 |
| `SOUL.md` | Agent 人格 |
| `USER.md` | 用户画像 |
| `TOOLS.md` | 工具定义 |
| `HEARTBEAT.md` | 定时任务 |
| `IDENTITY.md` | Agent 身份卡 |
| `BOOTSTRAP.md` | 首次引导 |
| `MEMORY.md` | 长期记忆 |
| `memory/*.md`、`memory/*.json` | 记忆文件 |
| `skills/*/SKILL.md`、`skills/*/_meta.json`、`skills/*/scripts/*` | 技能 |

### hermes

单 agent 安装；根目录 `~/.hermes`。

| 模式 | 说明 |
|---|---|
| `SOUL.md` | Agent 人格 |
| `memories/*.md` | 记忆文件 |
| `skills/*/SKILL.md`、`skills/*/DESCRIPTION.md`、`skills/*/_meta.json` | 技能定义与元数据 |
| `skills/*/scripts/*`、`skills/*/references/*` | 技能脚本与引用 |
| `skills/*/*/...` | 嵌套技能（同一组，深一层） |

### qwenpaw

每 agent 独立目录：`~/.qwenpaw/workspaces/<name>`（默认 agent 为 `workspaces/default`）。

| 模式 | 说明 |
|---|---|
| `AGENTS.md` | Agent 工作流程与规则 |
| `SOUL.md` | 核心人格 |
| `PROFILE.md` | 身份 + 用户资料 |
| `BOOTSTRAP.md` | 首次引导文件（引导完成后自动删除） |
| `MEMORY.md` | 长期记忆 |
| `HEARTBEAT.md` | 周期任务 |
| `memory/*.md` | 每日记忆文件 |
| `skills/*/SKILL.md`、`skills/*/_meta.json`、`skills/*/scripts/*` | 技能 |

### openhuman

工作空间根目录：`~/.openhuman/workspace`。

| 模式 | 说明 |
|---|---|
| `SOUL.md` | 核心人格 |
| `IDENTITY.md` | 使命与价值观 |
| `USER.md` | 用户画像 |
| `PROFILE.md` | onboarding 富化的用户资料 |
| `MEMORY.md` | 长期记忆摘要 |
| `HEARTBEAT.md` | 周期任务 |
| `wiki/*.md`、`wiki/summaries/*.md`、`wiki/notes/*.md` | Obsidian 记忆库 |
| `skills/*/SKILL.md`、`skills/*/_meta.json`、`skills/*/scripts/*` | 技能 |

### qoder

单文件 + 共享。共享根目录 `~/.qoder`（用 `--local_dir` 指向项目内的 `.qoder/` 可上传项目级配置）。一个子 agent 即一个 Markdown 文件 `agents/<name>.md`，其余文件为各子 agent 共享。

| 模式 | 说明 |
|---|---|
| `AGENTS.md` | 共享的 agent 指令 / 记忆 |
| `agents/{name}.md` | 所选子 agent 定义 |
| `commands/*.md` | 自定义斜杠命令（共享） |
| `rules/*.md` | 规则（共享） |
| `skills/*/SKILL.md`、`skills/*/scripts/*`、`skills/*/references/*` | 技能（共享） |

## 存储与 Bundle 格式

**Profile（表 `harness_profiles`）**

- `resources_json`：仅序列化**路径到文本**的 JSON 对象，例如 `{"SOUL.md": "…", "memory/MEMORY.md": "…"}`。
- `product`、`revision`、`updated_at` 等为表字段，不在 `resources_json` 内。

**Share（表 `harness_shares`）**

- `snapshot_json`：服务端写入 `{"product": "<产品名>", "resources": { ... }}`，由 `HarnessService` 在 `sync up` / `create share` 时生成或更新，**不包含** `collected_at` 字段。

**代码中的 `HarnessBundle`（`ultron/services/harness/bundle.py`）**

- 用于客户端侧从 allowlist 收集工作区时封装 `product`、`resources` 与可选的 `collected_at`；`to_snapshot_json()` 可产生含 `collected_at` 的 JSON，与上述数据库中的 `snapshot_json` 持久化格式**不必相同**。

## 已知限制

- 不支持二进制文件（仅文本同步）
- 单文件最大 1 MB（见 `allowlist.MAX_FILE_SIZE`）
- 已创建的 share 在后续 `sync up` 时可能被**覆盖更新**（见上文「分享流程」）；导入方本机已有文件不会自动同步
- 无冲突解决机制 — sync up 时以最后写入为准

API 参考见 [HTTP API](../API/HttpAPI.md) 和 [SDK](../API/SDK.md) 文档的 HarnessHub 章节。

---

## 认证（Authentication）

多数 Harness 同步与分享管理端点需要 JWT。公开端点（defaults、soul-presets 列表与详情、showcase、`GET /i/{short_code}`、`GET /harness/share/export/{token}`）无需 token。通过 `POST /auth/register` 或 `POST /auth/login` 获取 token 后，在需鉴权的请求中传递 `Authorization: Bearer <token>`；`user_id` 从 token 中提取，无需显式传递。

详见 [HTTP API — 认证](../API/HttpAPI.md#认证authentication)。

---

## Soul Presets（角色预设）

Soul Presets 提供开箱即用的 agent 人格模板。每个预设包含人格文本，按 OpenClaw 约定拆分为工作空间文件（`SOUL.md`、`AGENTS.md`、`IDENTITY.md`）。

### 结构

- 预设存储在 `data/soul_presets/` 目录，使用 YAML frontmatter（`name`、`description`、`emoji`、`color`、`vibe`）
- 按 17 个分类组织（创意、专业、技术等）
- 内置超过 200 个预设

### 构建流程

1. 用户选择一个或多个预设 ID
2. `POST /harness/soul-presets/build` 合并选定预设
3. 返回 `{resources: {"SOUL.md": "...", "AGENTS.md": "...", "IDENTITY.md": "..."}}`
4. 客户端将资源写入本地工作空间

### API

`GET` 接口无需鉴权；`POST /harness/soul-presets/build` 需 JWT（见「HTTP API 概要」）。

| 端点 | 说明 |
|------|------|
| `GET /harness/soul-presets` | 按分类列出所有预设 |
| `GET /harness/soul-presets/{preset_id}` | 获取完整预设（含 body） |
| `POST /harness/soul-presets/build` | 从选定预设构建合并资源 |

---

## Showcase（展示案例）

Showcase 是精选的 agent 示例，支持多语言。

### 结构

- 以 Markdown 文件存储在 `docs/{lang}/Showcase/` 目录（支持 `zh` 和 `en`）
- YAML frontmatter：`name`、`description`、`emoji`、`short_code`、`agent_id`、`tags`
- 每个条目有基于文件名的唯一 slug

### API

| 端点 | 说明 |
|------|------|
| `GET /harness/showcase?lang=zh` | 列出指定语言的所有案例 |
| `GET /harness/showcase/{slug}?lang=zh` | 获取完整案例内容 |

---

## Defaults（产品默认文件）

每个支持的产品附带默认工作空间文件，供新用户快速开始。

| 产品 | 默认文件 |
|------|----------|
| nanobot | SOUL.md, AGENTS.md, USER.md, TOOLS.md, HEARTBEAT.md, memory/MEMORY.md, memory/HISTORY.md |
| openclaw | SOUL.md, AGENTS.md, USER.md, TOOLS.md, HEARTBEAT.md, IDENTITY.md, BOOTSTRAP.md |
| hermes | SOUL.md, memories/USER.md |
| qwenpaw | SOUL.md, AGENTS.md, PROFILE.md, HEARTBEAT.md |
| openhuman | SOUL.md, IDENTITY.md, USER.md, HEARTBEAT.md |
| qoder | （无内置默认文件） |

### API

```
GET /harness/defaults/{product}
```

返回 `{success, product, files}`，其中 `files` 为文件名到内容的映射。
