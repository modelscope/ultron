---
slug: HttpAPI
title: HTTP API
description: Ultron（奥创）HTTP API 参考
---

# HTTP API

Ultron 提供 RESTful HTTP API，由 FastAPI 驱动，默认监听 `http://0.0.0.0:9999`。

## 启动服务

```shell
uvicorn ultron.server:app --host 0.0.0.0 --port 9999
```

## 通用说明

- **响应格式**：JSON
- **后台任务**：进程启动后会按 `decay_interval_hours` 周期执行记忆衰减；若配置 `async_embedding=true` 会启动嵌入队列（与 HTTP 行为共享同一 `Ultron` 实例）

---

## 系统

### 健康检查

```
GET /
```

重定向到 `/dashboard`（HTTP 302）。

```
GET /health
```

**响应**：

```json
{
    "status": "ok",
    "service": "ultron",
    "version": "1.0.0",
    "architecture": "collective-intelligence"
}
```

### 系统统计

```
GET /stats
```

汇总 **技能存储**、**技能分类**、**嵌入服务**、**记忆库** 四类信息。

**响应结构（示例字段）**：

```json
{
  "storage": {
    "total_skills": 56,
    "archived_skills": 2,
    "total_size_bytes": 1048576,
    "total_size_mb": 1.0,
    "skills_dir": "/path/to/skills",
    "archive_dir": "/path/to/archive"
  },
  "categories": {
    "total_skills": 56,
    "total_categories": 120,
    "categories_with_skills": 45,
    "dimension_stats": {},
    "top_categories": [{"name": "ai-llms", "count": 8}]
  },
  "embedding": {
    "backend": "dashscope",
    "model_name": "text-embedding-v4",
    "dimension": 1024,
    "is_available": true,
    "has_dashscope": true,
    "has_numpy": true,
    "request_timeout_seconds": 600
  },
  "memory": {
    "total": 1234,
    "by_tier": {"hot": 40, "warm": 500, "cold": 694},
    "by_type": {"pattern": 800, "error": 400},
    "by_status": {"active": 1200}
  }
}
```

---

## 记忆管理（Remote Memory）

### 上传记忆

```
POST /memory/upload
```

**请求体**：


| 字段           | 类型       | 必填  | 说明     |
| ------------ | -------- | --- | ------ |
| `content`    | string   | 是   | 记忆内容   |
| `context`    | string   | 否   | 上下文/场景 |
| `resolution` | string   | 否   | 解决方式   |
| `tags`       | string[] | 否   | 标签列表   |


**响应**：

```json
{
    "success": true,
    "data": {
        "id": "mem-xxx",
        "memory_type": "error",
        "tier": "warm",
        "hit_count": 1,
        "status": "active"
    }
}
```

### 检索记忆

```
POST /memory/search
```

**请求体**：


| 字段             | 类型     | 必填  | 说明                                                                                                 |
| -------------- | ------ | --- | -------------------------------------------------------------------------------------------------- |
| `query`        | string | 是   | 自然语言查询                                                                                             |
| `tier`         | string | 否   | `hot` / `warm` / `cold` 限定单层；`all` 搜全部层级；**省略或 `null` 时搜全部层级**                                     |
| `limit`        | int    | 否   | 返回条数上限；**省略**时用服务端 `ULTRON_MEMORY_SEARCH_LIMIT`（默认 **10**）                                         |
| `detail_level` | string | 否   | `**l0`** 或 `**l1`**（默认 `l0`）。仅控制检索结果中的**正文类字段**是否截断/清空：`l0` 多为摘要向（常配合 `summary_l0`）；`l1` 保留更多上下文字段 |


**响应**：

```json
{
    "success": true,
    "count": 5,
    "data": [
        {
            "id": "mem-xxx",
            "memory_type": "error",
            "content": "",
            "context": "",
            "resolution": "",
            "summary_l0": "Python 缺少 pandas 模块时的处理要点",
            "overview_l1": "",
            "tier": "warm",
            "similarity_score": 0.8765,
            "tier_boosted_score": 1.0518
        }
    ]
}
```

### 获取记忆详情

```
POST /memory/details
{
    "memory_ids": ["mem-001", "mem-002", "mem-003"]
}
```

返回与 `MemoryRecord` 对齐的**可读字段**（完整 `content` / `context` / `resolution`、标签、摘要字段、时间戳等）。

```json
{
  "success": true,
  "count": 2,
  "data": [
    {
      "id": "mem-001",
      "memory_type": "error",
      "content": "完整正文 …",
      "context": "",
      "resolution": "",
      "tier": "warm",
      "hit_count": 3,
      "summary_l0": "",
      "overview_l1": ""
    }
  ]
}
```

### 记忆统计

```
GET /memory/stats
```

```json
{
  "success": true,
  "data": {
    "total": 1234,
    "by_tier": { "hot": 40, "warm": 500, "cold": 694 },
    "by_type": { "pattern": 800 },
    "by_status": { "active": 1100 }
  }
}
```

---

## 会话与摄取

### 统一摄取

```
POST /ingest
{
    "paths": ["/path/to/file.txt", "/path/to/sessions/"]
}
```

- `**success**`：`data.successful > 0` 时为 `true。`
- `**data**`：智能摄取服务的原始结果字典（含路径处理、成功条数等，结构以运行时为准）。

### 文本摄取

```
POST /ingest/text
{
    "text": "原始文本内容..."
}
```

- `**success**`：取自结果字典的 `success` 字段。
- `**data**`：`ingest_text` 返回的详情字典。

---

## 技能管理（Skill Hub）

### 列出技能

```
GET /skills
```

```json
{
  "success": true,
  "count": 2,
  "data": [
    { "slug": "my-skill", "version": "1.0.0", "path": "/abs/path/to/my-skill-1.0.0" }
  ]
}
```

### 检索技能

```
POST /skills/search
{
    "query": "如何解决 Python 导入错误",
    "limit": 3
}
```

- `**limit**` 省略时使用 `ULTRON_SKILL_SEARCH_LIMIT`（默认 **5**）。

```json
{
  "success": true,
  "count": 2,
  "data": [
    {
      "slug": "fix-imports",
      "version": "1.0.0",
      "name": "Fix Imports",
      "description": "...",
      "categories": ["coding-agents-ides"],
      "similarity_score": 0.82,
      "combined_score": 0.91,
      "source": "internal",
      "full_name": null
    },
    {
      "slug": "catalog-skill-example",
      "version": "1.0.0",
      "name": "Catalog Skill Example",
      "description": "...",
      "categories": ["coding-agents-ides"],
      "similarity_score": 0.78,
      "combined_score": 0.85,
      "source": "catalog",
      "full_name": "@ns/catalog-skill-example"
    }
  ]
}
```

### 上传技能

```
POST /skills/upload
{
    "paths": ["/path/to/skill-dir", "/path/to/skills-folder"]
}
```

传入目录路径列表：若某路径下直接存在 `SKILL.md` 则作为单个技能目录；若为目录且无顶层 `SKILL.md`，则扫描**一层子目录**中含 `SKILL.md` 的项并分别上传。

**响应**：

```json
{
    "success": true,
    "data": {
        "total": 2,
        "successful": 2,
        "results": [
            {"path": "/path/to/skill-dir", "success": true, "slug": "my-skill", "version": "1.0.0", "name": "My Skill"},
            {"path": "/path/to/skills-folder/sub-skill", "success": true, "slug": "sub-skill", "version": "1.0.0", "name": "Sub Skill"}
        ]
    }
}
```

`**success**`：`successful > 0` 时为 `true`。

### 安装技能到指定目录

```
POST /skills/install
```

将技能安装到指定目录。优先查找 Ultron 内部技能（按 slug），找不到则通过 `modelscope skill add` 从 ModelScope Skill Hub 安装。

**请求体**：

```json
{
    "full_name": "@ns/name",
    "target_dir": "~/.nanobot/workspace/skills"
}
```


| 字段           | 类型     | 必填  | 说明                                             |
| ------------ | ------ | --- | ---------------------------------------------- |
| `full_name`  | string | 是   | 技能名称或完整路径（如 `@ns/name`）；内部技能直接用 slug           |
| `target_dir` | string | 是   | 安装目标目录，由调用方指定（如 `~/.nanobot/workspace/skills`） |


**响应**：

```json
{
    "success": true,
    "full_name": "@ns/name",
    "source": "internal",
    "installed_path": "~/.nanobot/workspace/skills/@ns/name"
}
```

- `source`：`"internal"`（来自 Ultron 内部）或 `"catalog"`（来自 ModelScope）

---

## HarnessHub（个人配置同步）

### 列出 Agent

```
GET /harness/agents
```

需要 `Authorization: Bearer <token>` 认证。

**响应**：

```json
{
    "success": true,
    "count": 2,
    "data": [...]
}
```

### 删除 Agent

```
DELETE /harness/agents
```

需要 `Authorization: Bearer <token>` 认证。

**请求体**：


| 字段         | 类型     | 必填  | 说明   |
| ---------- | ------ | --- | ---- |
| `agent_id` | string | 是   | 设备标识 |


级联删除该 agent 的 profile 和 share token。

### 上传工作空间（Sync Up）

```
POST /harness/sync/up
```

需要 `Authorization: Bearer <token>` 认证。

**请求体**：


| 字段          | 类型     | 必填  | 说明                     |
| ----------- | ------ | --- | ---------------------- |
| `agent_id`  | string | 是   | 设备标识                   |
| `product`   | string | 否   | Claw 产品名（默认 `nanobot`） |
| `resources` | object | 是   | 工作空间文件 `{相对路径: 内容}`    |


**响应**：

```json
{
    "success": true,
    "data": {
        "user_id": "u1",
        "agent_id": "d1",
        "revision": 1,
        "resources": {"SOUL.md": "..."},
        "product": "nanobot",
        "updated_at": "2026-04-06T12:00:00"
    }
}
```

### 下载工作空间（Sync Down）

```
POST /harness/sync/down
```

需要 `Authorization: Bearer <token>` 认证。

**请求体**：


| 字段         | 类型     | 必填  | 说明   |
| ---------- | ------ | --- | ---- |
| `agent_id` | string | 是   | 设备标识 |


返回该 (user, agent) 的 profile，404 表示无数据。

### 获取 Profile

```
GET /harness/profile?agent_id=d1
```

需要 `Authorization: Bearer <token>` 认证。

### 获取所有 Profile

```
GET /harness/profiles
```

需要 `Authorization: Bearer <token>` 认证。返回当前用户的所有 profile。

### 创建分享

```
POST /harness/share
```

需要 `Authorization: Bearer <token>` 认证。

**请求体**：


| 字段           | 类型     | 必填  | 说明                                   |
| ------------ | ------ | --- | ------------------------------------ |
| `agent_id`   | string | 是   | 设备标识                                 |
| `visibility` | string | 否   | `link`/`public`/`private`（默认 `link`） |


**响应**：

```json
{
    "success": true,
    "data": {
        "token": "abc123...",
        "source_user_id": "u1",
        "source_agent_id": "d1",
        "visibility": "link",
        "snapshot": {...},
        "created_at": "2026-04-06T12:00:00"
    }
}
```

### 列出分享

```
GET /harness/shares
```

需要 `Authorization: Bearer <token>` 认证。

### 删除分享

```
DELETE /harness/share
```

需要 `Authorization: Bearer <token>` 认证。

**请求体**：


| 字段      | 类型     | 必填  | 说明       |
| ------- | ------ | --- | -------- |
| `token` | string | 是   | 分享 token |


### 导出分享

```
GET /harness/share/export/{token}
```

返回 bash 安装脚本，用于导入分享的 agent 配置。


| 参数        | 位置    | 类型     | 必填  | 说明                 |
| --------- | ----- | ------ | --- | ------------------ |
| `token`   | path  | string | 是   | 分享 token           |
| `product` | query | string | 否   | 目标产品（默认 `nanobot`） |


### 短码导入

```
GET /i/{code}
```

分享导出的短码别名，返回 bash 安装脚本。


| 参数        | 位置    | 类型     | 必填  | 说明                 |
| --------- | ----- | ------ | --- | ------------------ |
| `code`    | path  | string | 是   | 6 位短码              |
| `product` | query | string | 否   | 目标产品（默认 `nanobot`） |


### 产品默认文件

```
GET /harness/defaults/{product}
```

返回指定产品（`nanobot`、`openclaw`、`hermes`）的默认工作空间文件。

**响应**：

```json
{
    "success": true,
    "product": "nanobot",
    "files": {"SOUL.md": "...", "AGENTS.md": "..."}
}
```

---

## 认证（Authentication）

### 注册

```
POST /auth/register
```

**请求体**：


| 字段         | 类型     | 必填  |
| ---------- | ------ | --- |
| `username` | string | 是   |
| `password` | string | 是   |


**响应**：

```json
{
    "success": true,
    "data": {
        "username": "alice",
        "token": "eyJ..."
    }
}
```

### 登录

```
POST /auth/login
```

**请求体**：


| 字段         | 类型     | 必填  |
| ---------- | ------ | --- |
| `username` | string | 是   |
| `password` | string | 是   |


**响应**：

```json
{
    "success": true,
    "data": {
        "username": "alice",
        "token": "eyJ..."
    }
}
```

### 当前用户

```
GET /auth/me
```

需要 `Authorization: Bearer <token>` 认证。

**响应**：

```json
{
    "success": true,
    "data": {
        "username": "alice",
        "created_at": "2026-04-06T12:00:00"
    }
}
```

---

## Soul Presets（角色预设）

### 列出预设

```
GET /harness/soul-presets
```

返回按分类分组的所有预设。

**响应**：

```json
{
    "success": true,
    "data": {
        "categories": [
            {
                "category": "creative",
                "presets": [{"id": "poet", "name": "Poet", "emoji": "✍️", "description": "..."}]
            }
        ]
    }
}
```

### 获取预设详情

```
GET /harness/soul-presets/{preset_id}
```

返回完整预设内容（含 body）。

### 构建角色资源

```
POST /harness/soul-presets/build
```

从选定预设构建合并后的工作空间资源，body 拆分为 `SOUL.md`、`AGENTS.md`、`IDENTITY.md`。

**请求体**：

```json
{
    "preset_ids": ["poet", "mentor"]
}
```

**响应**：

```json
{
    "success": true,
    "data": {
        "resources": {
            "SOUL.md": "...",
            "AGENTS.md": "...",
            "IDENTITY.md": "..."
        }
    }
}
```

---

## Showcase（展示案例）

### 列出案例

```
GET /harness/showcase?lang=zh
```


| 参数     | 位置    | 类型     | 必填  | 说明                   |
| ------ | ----- | ------ | --- | -------------------- |
| `lang` | query | string | 否   | `zh` 或 `en`（默认 `zh`） |


### 获取案例详情

```
GET /harness/showcase/{slug}?lang=zh
```

按 slug 返回完整案例内容。

---

## Dashboard（仪表盘）

### 仪表盘 UI

```
GET /dashboard
```

返回仪表盘 HTML 页面。SPA 路由（`/skills`、`/leaderboard`、`/quickstart`、`/harness`）同样返回此 HTML。

### 概览

```
GET /dashboard/overview
```

```json
{
    "memory": {...},
    "skills": {...}
}
```

### 记忆列表

```
GET /dashboard/memories?q=docker&memory_type=error&tier=hot&sort=recent&page=1&page_size=20
```

所有查询参数均可选。返回分页记忆列表。

### 技能列表

```
GET /dashboard/skills?q=python&source=internal&category=ai&page=1&page_size=20
```

所有查询参数均可选。返回分页技能列表。

### 技能 Markdown

```
GET /dashboard/skills/internal/{slug}/skill-md
```

返回内部技能的原始 SKILL.md 内容。

```json
{
    "slug": "my-skill",
    "content": "# My Skill\n..."
}
```

### 排行榜

```
GET /dashboard/leaderboard?limit=20
```

返回技能使用排行榜数据。

### Agent 技能包

```
GET /dashboard/agent-skill-package
```

返回包含所有技能的 ZIP 文件，用于 agent 部署。

---

## 错误码


| HTTP 状态码 | 说明               |
| -------- | ---------------- |
| 200      | 成功               |
| 400      | 请求参数错误           |
| 403      | 权限不足             |
| 404      | 资源不存在（如技能未找到）    |
| 422      | 请求体验证失败（FastAPI） |
| 500      | 服务器内部错误          |


---

## 请求追踪

每个请求会分配唯一 `trace_id`：

- 响应头：`X-Trace-Id: a1b2c3d4e5f6`
- 日志中可通过此 ID 追踪完整请求链路

## CORS

默认允许所有来源（`allow_origins=["*"]`），生产环境建议改为具体域名。