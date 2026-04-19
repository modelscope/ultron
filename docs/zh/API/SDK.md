---
slug: SDK
title: Python SDK
description: Ultron（奥创）Python SDK 参考
---

# Python SDK

Ultron 提供 Python SDK，可直接在代码中使用，无需启动 HTTP 服务。

## 安装

```shell
pip install -e .
```

## 快速开始

```python
from ultron import Ultron

# 使用默认配置
ultron = Ultron()

# 或自定义配置
from ultron import UltronConfig

config = UltronConfig(
    data_dir="~/.my-ultron",
    llm_provider="openai",
    llm_model="gpt-5",
    llm_base_url="https://api.openai.com/v1",
    llm_api_key="your-api-key",
)
ultron = Ultron(config=config)
```

---

## 记忆管理

### upload_memory

```python
record = ultron.upload_memory(
    content: str,
    context: str,
    resolution: str,
    tags: List[str] = None,
) -> MemoryRecord
```

**示例**：

```python
record = ultron.upload_memory(
    content="ModuleNotFoundError: No module named 'pandas'",
    context="Docker 容器内运行脚本",
    resolution="pip install pandas",
    tags=["python", "docker"],
)
```

### search_memories

语义检索记忆。

```python
results = ultron.search_memories(
    query: str,
    tier: str = None,       # None=全部层级, "hot"/"warm"/"cold"/"all"
    limit: int = None,      # None 时使用 UltronConfig.memory_search_default_limit（ULTRON_MEMORY_SEARCH_LIMIT）
    detail_level: str = "l0",  # "l0" or "l1"
) -> List[MemorySearchResult]
```

### get_memory_details

根据 ID 列表获取记忆详情。

```python
records = ultron.get_memory_details(
    memory_ids: List[str],
) -> List[MemoryRecord]
```

### get_memory_stats

获取记忆统计。

```python
stats = ultron.get_memory_stats() -> dict
```

---

## 智能摄取

### ingest

统一摄取：按文件类型自动分发（`.jsonl` → 增量提取，其他 → LLM 提取）。支持文件、目录混合传入。

```python
result = ultron.ingest(
    paths: List[str],
    agent_id: str = "", 
) -> dict
```

### ingest_text

摄取原始文本。

```python
result = ultron.ingest_text(
    text: str,
) -> dict
```

---

## 层级重分配

### run_tier_rebalance

按 `hit_count` 百分位重分配 HOT/WARM/COLD 层级，归档超期 COLD 记忆。

```python
summary = ultron.run_tier_rebalance() -> dict
```

### run_memory_decay

`run_tier_rebalance` 的别名（向后兼容）。

```python
summary = ultron.run_memory_decay() -> dict
```

---

## 原文归档（raw_user_uploads）

开启 `archive_raw_uploads` 时：`ingest(paths)` 为每个摄取文件写入一行（`ingest_file`）；仅 `**ingest_text` / HTTP 纯文本摄取**（无 `source_file`）写入一行 UTF-8 原文（`ingest_text`）；**从文件读入再 LLM 提取时不重复写入正文**（已有 `ingest_file`）。`upload_skill` 为包内每个文件写入一行（`skill_upload_file`）。

### get_raw_user_upload

按 ID 获取归档记录（含 `payload_text` / `payload_base64` 等解码字段）。

```python
upload = ultron.get_raw_user_upload(
    upload_id: str,
) -> Optional[dict]
```

### list_raw_user_uploads

列出归档摘要（不含完整 payload）。

```python
uploads = ultron.list_raw_user_uploads(
    limit: int = 100,
    offset: int = 0,
    source_prefix: str = None,
) -> List[dict]
```

---

## 技能管理

### search_skills

语义检索技能（同时搜索内部技能和 ModelScope Skill Hub 目录技能，按相似度统一排序）。每条结果包含 `source`（`"internal"` 或 `"catalog"`）和 `full_name` 字段。

```python
results = ultron.search_skills(
    query: str,
    limit: int = None,  # None 时使用 UltronConfig.skill_search_default_limit（ULTRON_SKILL_SEARCH_LIMIT）
) -> List[RetrievalResult]
```

### upload_skills

批量上传技能：传入目录路径列表，自动扫描含 `SKILL.md` 的子目录并逐个上传。

```python
result = ultron.upload_skills(
    paths: List[str],
) -> dict
```

**示例**：

```python
# 上传单个技能目录
result = ultron.upload_skills(
    paths=["/path/to/my-skill"],
)

# 上传目录下所有技能
result = ultron.upload_skills(
    paths=["/path/to/skills-folder"],
)
# result: {"total": 3, "successful": 3, "results": [...]}
```

### install_skill_to

将技能安装到指定目录。优先查找 Ultron 内部技能，找不到则通过 `modelscope skill add` 从 ModelScope Skill Hub 安装。

```python
result = ultron.install_skill_to(
    full_name: str,    # 技能名称或完整路径（如 "@ns/name"）；内部技能直接用 slug
    target_dir: str,   # 安装目标目录，由调用方指定
) -> dict
```

**示例**：

```python
# 安装内部技能
result = ultron.install_skill_to(
    full_name="ultron",
    target_dir="~/.nanobot/workspace/skills",
)
# result: {"success": true, "source": "internal", "installed_path": "..."}

# 安装 ModelScope 目录技能
result = ultron.install_skill_to(
    full_name="@anthropics/minimax-pdf",
    target_dir="~/.nanobot/workspace/skills",
)
# result: {"success": true, "source": "catalog", "installed_path": "..."}
```

### upload_skill

上传单个技能目录。

```python
skill = ultron.upload_skill(
    skill_dir: str,
) -> Optional[Skill]
```

### get_skill

按 slug 获取技能，可选指定版本。

```python
skill = ultron.get_skill(
    slug: str,
    version: Optional[str] = None,
) -> Optional[Skill]
```

### get_internal_skill_md_text

获取内部技能的原始 SKILL.md 文本。

```python
text = ultron.get_internal_skill_md_text(
    slug: str,
) -> Optional[str]
```

### list_all_skills

列出所有技能。

```python
skills = ultron.list_all_skills() -> List[dict]
```

### Skill evolution and clusters

面向**服务端与运维**：结晶与重新结晶在服务端 `_decay_loop` 中执行，**不提供**对外 HTTP。在与 `Ultron` **同一进程、同一 `data_dir`/数据库**下排障或观测时，可直接使用底层 SQLite `Database`（`ultron.db`）：

```python
clusters = ultron.db.get_all_clusters()
rows = ultron.db.get_evolution_history("my-skill-slug", limit=20)
```

若需在独立脚本中手动跑一轮进化，使用与数据目录一致的 `UltronConfig` 构造 `SkillEvolutionEngine` 并调用 `run_evolution_cycle()`，见 `ultron.services.skill.skill_evolution`。

---

## HarnessHub（个人配置同步）

### list_agents

列出用户的所有 agent。

```python
agents = ultron.list_agents(user_id: str) -> List[dict]
```

### remove_agent

删除 agent（级联删除 profile 和 share）。

```python
ok = ultron.remove_agent(user_id: str, agent_id: str) -> bool
```

### harness_sync_up

上传工作空间 bundle 到服务器。

```python
profile = ultron.harness_sync_up(
    user_id: str,
    agent_id: str,
    product: str,
    resources: dict,        # {相对路径: 文件内容}
) -> dict
```

### harness_sync_down

下载工作空间 bundle。

```python
profile = ultron.harness_sync_down(
    user_id: str,
    agent_id: str,
) -> Optional[dict]
```

### get_harness_profile

获取 (user, agent) 的 profile。

```python
profile = ultron.get_harness_profile(
    user_id: str,
    agent_id: str,
) -> Optional[dict]
```

### get_profiles_by_user

列出该用户下全部工作空间 profile。

```python
profiles = ultron.get_profiles_by_user(user_id: str) -> list
```

### create_harness_share

从当前 profile 创建分享 token（无 profile 时会抛错，需先 `harness_sync_up`）。若同一 agent 已有分享，会复用 token 并刷新快照。

```python
share = ultron.create_harness_share(
    user_id: str,
    agent_id: str,
    visibility: str = "public",
) -> dict
```

### list_harness_shares

列出用户创建的所有分享。

```python
shares = ultron.list_harness_shares(user_id: str) -> List[dict]
```

### delete_harness_share

删除分享 token。

```python
ok = ultron.delete_harness_share(token: str) -> bool
```

---

## 统计

### get_stats

聚合技能存储、分类统计、嵌入模型信息与记忆统计（与 HTTP `GET /stats` 数据结构一致）。

```python
stats = ultron.get_stats() -> dict
```

---

## 管理

### reset_all

重置所有数据（清空数据库、删除技能文件）。

```python
result = ultron.reset_all() -> dict
```

---

## 数据模型

### MemoryRecord

```python
@dataclass
class MemoryRecord:
    id: str
    memory_type: str
    content: str
    context: str
    resolution: str
    summary_l0: str
    overview_l1: str
    tier: str
    status: str
    scope: str
    hit_count: int
    tags: List[str]
    created_at: datetime
    last_hit_at: datetime
```

### MemorySearchResult

```python
@dataclass
class MemorySearchResult:
    record: MemoryRecord
    similarity_score: float
    tier_boosted_score: float
```

### Skill

```python
@dataclass
class Skill:
    meta: SkillMeta
    frontmatter: SkillFrontmatter
    content: str
    scripts: Dict[str, str]
    local_path: Optional[str]
```

### RetrievalResult

```python
@dataclass
class RetrievalResult:
    skill: Skill
    similarity_score: float
    combined_score: float
```

---

## 导出

SDK 提供以下公开导出：

```python
from ultron import (
    # 主入口
    Ultron,

    # 配置
    UltronConfig,
    default_config,
    load_ultron_dotenv,

    # 模型 - 技能
    Skill,
    SkillMeta,
    SkillFrontmatter,
    SkillUsageRecord,
    SourceType,
    Complexity,

    # 模型 - 记忆
    MemoryRecord,
    MemoryTier,
    MemoryType,
    MemoryStatus,

    # 检索
    RetrievalQuery,
    RetrievalResult,
    MemorySearchResult,

    # 服务
    IntentAnalyzer,
    ConversationExtractor,
    LLMService,
    LLMOrchestrator,
    SmartIngestionService,
)
```

