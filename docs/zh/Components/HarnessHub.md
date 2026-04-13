# HarnessHub（个人配置同步）

HarnessHub 是 Ultron 的个人工作空间同步与共享模块，支持在多个 Claw 产品（nanobot、openclaw、hermes 等）之间一键迁移和共享个人记忆、技能、人格配置。

## 核心概念

| 概念 | 说明 |
|---|---|
| **user_id** | 用户唯一标识 |
| **agent_id** | 设备/终端标识，同一用户可拥有多个设备 |
| **Claw** | 一个 `(user_id, agent_id)` 组合，代表某用户在某终端上的 agent 实例 |
| **Profile** | 存储在 Ultron 服务端的工作空间快照（文件内容 + 技能引用列表） |
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
| nanobot | `~/.nanobot/workspace/` | AGENTS.md, SOUL.md, USER.md, TOOLS.md, HEARTBEAT.md, memory/*.md, skills/*/* |
| openclaw | `~/.openclaw/workspace/` | AGENTS.md, SOUL.md, USER.md, TOOLS.md, HEARTBEAT.md, memory/*.md, skills/*/* |
| hermes | `~/.hermes/` | config.yaml, SOUL.md, memories/*.md, skills/*/* |

所有产品均**排除**：`.env`、`auth.json`、`sessions/`、`logs/`、隐藏文件。

## 分享流程

1. 用户 A 执行 `sync up` 将工作空间上传到 Ultron
2. 用户 A 调用 `create share` 生成分享短码（6 位字母数字）
3. 用户 A 将短码发送给用户 B
4. 用户 B 在终端执行一行命令即可导入：

```bash
curl -sL https://your-server/i/Ab3xK9 | bash
```

分享快照是**时间点副本**，源 profile 后续修改不影响已创建的 share token。

```
本地工作空间 ──sync up──▶ Ultron 服务端 ──create share──▶ 短码 Ab3xK9
                                                            │
                                                            ▼
                              curl -sL server/i/Ab3xK9 | bash
                                                            │
                                                            ▼
                                                     本地工作空间
```

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

上传、下载、创建分享等请使用 **Dashboard** 或带鉴权的 HTTP API（如 `POST /harness/sync/up`、`POST /harness/share`）。

## 扩展新产品

添加新的 Claw 产品支持只需：

1. 在 `ultron/services/harness/allowlist.py` 中创建 `ClawWorkspaceAllowlist` 子类
2. 定义 `product_name`、`workspace_root`、`patterns`
3. 注册到 `ALLOWLIST_REGISTRY`

```python
class MyProductAllowlist(ClawWorkspaceAllowlist):
    @property
    def product_name(self) -> str:
        return "myproduct"

    @property
    def workspace_root(self) -> Path:
        return Path.home() / ".myproduct"

    @property
    def patterns(self) -> List[str]:
        return ["config.yaml", "SOUL.md", "memory/*.md"]

ALLOWLIST_REGISTRY["myproduct"] = MyProductAllowlist
```

## 各产品文件模式详情

### nanobot

| 模式 | 说明 |
|---|---|
| `AGENTS.md` | Agent 指令 |
| `SOUL.md` | Agent 人格 |
| `USER.md` | 用户画像 |
| `TOOLS.md` | 工具定义 |
| `HEARTBEAT.md` | 定时任务 |
| `memory/MEMORY.md` | 长期记忆 |
| `memory/HISTORY.md` | 会话历史 |
| `skills/*/SKILL.md` | 技能定义 |
| `skills/*/_meta.json` | 技能元数据 |
| `skills/*/scripts/*` | 技能脚本 |
| `skills/*/setup.md` | 技能安装文档 |
| `skills/*/operations.md` | 技能操作文档 |
| `skills/*/boundaries.md` | 技能边界文档 |

### openclaw

与 nanobot 相同（共享工作空间布局）。

### hermes

| 模式 | 说明 |
|---|---|
| `config.yaml` | Agent 配置 |
| `SOUL.md` | Agent 人格 |
| `memories/*.md` | 记忆文件 |
| `skills/*/SKILL.md` | 技能定义 |
| `skills/*/_meta.json` | 技能元数据 |
| `skills/*/scripts/*` | 技能脚本 |

## Bundle Schema

存储在 `harness_profiles.resources_json` 和 `harness_shares.snapshot_json` 中的 JSON 结构：

```json
{
    "product": "nanobot",
    "resources": {
        "SOUL.md": "文件内容...",
        "memory/MEMORY.md": "文件内容..."
    },
    "collected_at": "2026-04-06T12:00:00+00:00"
}
```

## 已知限制

- 不支持二进制文件（仅文本同步）
- 单文件最大 1 MB
- 分享快照为时间点副本（非实时引用）
- 无冲突解决机制 — sync up 时以最后写入为准

API 参考见 [HTTP API](../API/HttpAPI.md) 和 [SDK](../API/SDK.md) 文档的 HarnessHub 章节。
