---
slug: MemoryHub
title: 记忆中心
description: Ultron（奥创）记忆中心：摄取、存储、聚类一体化
---

# 记忆中心

记忆中心（Memory Hub）是 Ultron 记忆侧的统一入口，整合三个子服务，并与 **轨迹层（Trajectory Hub）** 配合：`.jsonl` 会话可先落轨迹表、经**任务分割**和 trajectory 指标分析后再写入记忆（详见 [轨迹中心](TrajectoryHub.md)）。

| 子服务 | 职责 |
|--------|------|
| **Ingestion Service** | ETL：会话型 `.jsonl`（`ingest(paths)`）→ LLM 任务分割 → task_segments（指纹去重）；无文件的 **`ingest_text`** 走主 LLM 直接抽记忆 |
| **Memory Service** | 核心存储引擎：去重、层级、语义检索、脱敏 |
| **Knowledge Cluster** | 语义聚类：将相关记忆分组，为技能结晶提供原料 |

数据流（概览）：

```
原始内容（会话 `.jsonl` 路径 或 `ingest_text` 纯文本）
    │
    ▼
Ingestion Service
 ├─ 会话 .jsonl（`ingest(paths)`）→ LLM 任务分割 → task_segments（指纹去重）
 │       → 定时任务：ms-agent trajectory 指标 → 满足阈值的 segment → upload_memory
 └─ `ingest_text`（无文件路径的纯文本）→ LLM 提取结构化记忆 → 直接上传
    │
    ▼
Memory Service — 去重、embedding、存储、层级管理
    │
    ▼
Knowledge Cluster — 按语义相似度聚类，供 Skill Hub 结晶
```

---

## Ingestion Service（智能摄取）

统一知识提取有两条入口，不要混为一谈：

**`ingest(paths)`（路径列表：会话型 `.jsonl` 文件，或内含多个 `.jsonl` 的目录）**  
典型用法是 **conversation 格式的 `.jsonl`**（每行一条带 `role`/`content` 的消息）。可对多个文件、多个目录一并传入；目录会递归展开，**仅收集其中的 `.jsonl`**（其余扩展名跳过）。对每个文件：先保存 session 元数据，再用 **LLM 任务分割**将对话拆分为独立 task segment，并按 **内容指纹** 做增量去重写入 **`task_segments`**。**本次请求内**不对其调用主 LLM 抽记忆；trajectory 指标分析与 `upload_memory` 由后台定时任务按 segment 粒度完成。若要从普通文本灌记忆，请用下面的 **`ingest_text`**。

**`ingest_text(text)`（仅一段字符串）**  
**始终**走主 LLM 文本提取并直接 `upload_memory`，**不**写入 `trajectory_records`，也**不**经过轨迹质量管线；与有无 `ingest`、是否上传过 `.jsonl` 无关。

自定义组装 `IngestionService` 时须为 `.jsonl` 提供 **`trajectory_service`**，否则会摄取失败。

### 核心能力

| 能力 | 说明 |
|------|------|
| **统一摄取** | 单一 `ingest(paths)` 入口；主场景为会话 `.jsonl` → LLM 任务分割 → task_segments |
| **文本摄取** | `ingest_text` 仅字符串，主 LLM 直接抽记忆上传，不经轨迹表 |
| **任务分割** | `.jsonl` 文件自动拆分为独立 task segment，以 segment 粒度计算指标和提取 |
| **指纹去重** | 基于内容指纹（SHA-256）增量追踪，避免重复处理 |
| **会话 / 轨迹** | `.jsonl` 写入 task_segments 并走 trajectory 指标管线；须注入 `trajectory_service` |
| **目录展开** | 传目录路径递归展开，**仅** `.jsonl`（跳过隐藏路径段、符号链接） |
| **类型判定** | 自动判断记忆类型 |
| **去重处理** | 自动与已有记忆合并 |
| **原文归档** | 有数据库时固定写入：`ingest(paths)` 对每个 `.jsonl` 一条 `ingest_file`；纯 `ingest_text` 一条 `ingest_text` |

### 使用示例

```python
from ultron import Ultron

ultron = Ultron()

# 统一摄取：会话导出（可多文件、可目录，均为 conversation 型 .jsonl）
result = ultron.ingest(
    paths=["/path/to/sessions/run-20250419.jsonl", "/path/to/sessions/"],
    agent_id="my-agent",
)

print(f"处理文件数: {result['total_files']}")
print(f"总记忆数: {result['total_memories']}")
```
此处在**仅有 `.jsonl` 落轨迹**时，`total_memories` 反映的是**新写入的 segment 条数**（`new_segments`），记忆入库发生在后续定时任务。

```python
# 文本摄取（无文件路径：直接抽记忆，不经过轨迹表）
result = ultron.ingest_text(
    text="""
    排查过程：
    1. 发现 Docker 内 pip install 失败
    2. 错误信息：Could not find a version that satisfies...
    3. 原因：容器内无网络访问权限
    4. 解决：配置代理或使用 --network host
    """,
)

for mem in result.get("memories", []):
    print(f"[{mem['memory_type']}] {mem['content'][:50]}...")
```

### 分发流程

```
输入路径列表
    ↓
递归展开目录内文件
    ↓
对每个文件：归档原始字节到 raw_user_uploads
 （跳过超过 10MB 的文件；归档失败不阻塞摄取）
    ↓
每个 `.jsonl` 文件
    → LLM 任务分割 → 独立 task segments（指纹去重）
    → 同时写入 trajectory_records 作为 session 元数据
    ↓
Memory Service（去重、晋升）；由定时任务对满足指标阈值的 segment 再上传
    ↓
分配到 Knowledge Cluster（语义聚类）
    ↓
汇总结果
```

### 增量会话与任务分割

**`.jsonl`**：服务端对每个文件执行 **LLM 任务分割**，将对话拆分为独立 task segment。每个 segment 基于消息内容计算 **SHA-256 指纹**（16 字符 hex）。重新上传同一文件时：
- 指纹匹配 → 跳过（幂等）
- 指纹不匹配 → 废弃旧 segment 的 memory（通过 tag 精准 archive），重新处理

不同路径的文件视为不同 session，**不做跨文件去重**。详见 [轨迹中心](TrajectoryHub.md)。

### 定时任务与层级重分配

后台 `ultron/services/background.py` 中的 `run_decay_loop`（由 `server.py` 的 lifespan 启动）在 **tier rebalance** 之前依次执行：**任务分段** → **segment 指标标注** → **从满足阈值的 segment 提取记忆**（`TrajectoryMemoryExtractor`） → `run_tier_rebalance` → 技能进化 → 记忆整合（若启用）。因此从 `.jsonl` 进入的记忆可能比 ingest 请求晚一个 `decay_interval_hours` 周期才入库。

### LLM 提取

默认模型 `qwen3.6-flash`。提取以下类型的可复用经验：

- 错误与解决方案
- 安全相关
- 模式与规律
- 生活经验（非个人隐私）

输出格式：

```json
{
  "memories": [
    {
      "content": "错误/问题描述",
      "context": "发生场景",
      "resolution": "解决方案",
      "confidence": 0.85,
      "tags": ["python", "docker"]
    }
  ]
}
```

### Token 管理

| 配置项 | 作用 |
|--------|------|
| `llm_max_input_tokens` | 输入内容的最大 token 数 |
| `llm_prompt_reserve_tokens` | 预留给回复的 token |

超长内容会被自动截断或分段处理。

---

## Memory Service（记忆服务）

核心存储引擎，负责多智能体共享记忆的上传、去重、百分位层级重分配、语义检索。

### 记忆层级 (Tier)

| 层级 | 说明 | 行为 |
|------|------|------|
| **HOT** | 高频命中（top N%） | 对所有智能体即时可用 |
| **WARM** | 中频命中（next M%） | 上下文匹配时返回 |
| **COLD** | 低频命中（剩余） | 默认参与检索，但排名靠后（tier boost 0.8 + 时间衰减） |

层级由 **`run_tier_rebalance`** 定期批量重分配（同一后台循环中，排在 trajectory 指标分析与满足阈值的 segment 写记忆**之后**，间隔 `decay_interval_hours`）：

1. 按 `hit_count` DESC、`last_hit_at` DESC 排序所有活跃记忆
2. 前 `hot_percentile`%（默认 10%）→ HOT
3. 接下来 `warm_percentile`%（默认 40%）→ WARM
4. 其余 → COLD
5. 超过 `cold_ttl_days` 的 COLD 记忆标记为 `archived`（不删除，但不再参与检索和重分配）

`hit_count` 由三种采纳信号驱动：

| 信号 | 权重 | 说明 |
|------|------|------|
| Details（拉取全文） | +2 | agent 主动选择 |
| Search（出现在检索结果） | +1 | 被检索到 |
| Merge（去重合并） | +1 | 相似记忆上传 |

### 记忆状态 (Status)

| 状态 | 说明 |
|------|------|
| `active` | 所有活跃记忆的默认状态 |
| `archived` | 超过 COLD TTL 后归档，不参与检索和重分配 |

### 记忆类型 (MemoryType)

由服务端 LLM 自动判定，**调用方不可指定**：

| 类型 | 说明 |
|------|------|
| `error` | 错误经验（工程/工具等） |
| `security` | 安全事件 |
| `correction` | 纠正/修正 |
| `pattern` | 观察到的模式 |
| `preference` | 显式偏好 |
| `life` | 可共享的生活类客观经验（如「乘机选座窍门」） |

### 使用示例

```python
from ultron import Ultron

ultron = Ultron()

# 上传记忆（类型由服务端自动判定）
record = ultron.upload_memory(
    content="ModuleNotFoundError: No module named 'pandas'",
    context="Docker 容器内运行数据分析脚本",
    resolution="pip install pandas",
    tags=["python", "docker", "pandas"],
)

print(f"记忆ID: {record.id}")
print(f"类型: {record.memory_type}")
print(f"层级: {record.tier}")
print(f"状态: {record.status}")
```

```python
# 语义检索
results = ultron.search_memories(
    query="Python 模块导入错误",
    detail_level="l1",
    limit=10,
)

for r in results:
    print(f"[{r.record.memory_type}] {r.record.content[:50]}...")
    print(f"  相似度: {r.similarity_score:.4f}")
```

```python
# 获取记忆全文
details = ultron.get_memory_details(["id1", "id2", "id3"])
```

### 上传与去重合并

入口方法为 `MemoryService.upload_memory`；命中近重复时的收尾逻辑在 **`_complete_near_duplicate_upload`**。

**扫描范围**：在同一 **`memory_type`** 下，对 HOT、WARM 和 COLD 嵌入做近重复检索。

**判定**：余弦相似度 **大于** `dedup_similarity_threshold`（默认 0.85）则视为同一条记忆。

**命中后**：

1. 日志 + 统计：`increment_memory_hit`，原文写入 **`memory_contributions`**
2. 合并正文：通过 LLM 进行语义合并；若 LLM 不可用或调用失败，**跳过本次合并**（保留原文不变），等待下次重复上传时 LLM 恢复后重试
3. 写回主表：正文变化则重算 embedding + 再生 L0/L1；仅 tags 变化则只更新标签

**未命中**：创建新 MemoryRecord（WARM、active）。

### L0 / L1 / Full 三级上下文

| 级别 | 内容 | 用途 |
|------|------|------|
| `l0` | 一句话摘要（`summary_l0`），正文类字段清空 | 快速浏览，最省 token |
| `l1` | 核心概览（`summary_l0` + `overview_l1`） | 缩小候选后再拉详情 |
| `full` | 完整原始内容 | 通过 `get_memory_details` 按 ID 拉取 |

语义检索仅支持 `l0` 和 `l1`；完整正文通过 `get_memory_details` 二次拉取。

### 时间衰减

```
hotness = exp(-decay_alpha * days_since_last_hit)
```

衰减影响检索排序（权重由 `time_decay_weight` 控制），不直接导致层级变化。层级完全由 `run_tier_rebalance` 按 `hit_count` 百分位重配。

### 数据脱敏

记忆上传时，`content`、`context`、`resolution` 字段在写入前自动脱敏。

基于 **[Microsoft Presidio](https://github.com/microsoft/presidio)**（spaCy 后端，支持中英文双语）。额外正则覆盖：

| 类型 | 替换标签 |
|------|----------|
| 邮箱、电话、IP、人名等 | Presidio 默认标签 |
| OpenAI / LLM API Key | `<LLM_API_KEY>` |
| GitHub Token | `<GITHUB_TOKEN>` |
| AWS Access Key | `<AWS_ACCESS_KEY>` |
| Bearer / Basic 认证头 | `<REDACTED_TOKEN>` |
| 通用凭证字段 | `<REDACTED_CREDENTIAL>` |
| UUID | `<UUID>` |
| 中国手机号 | `<PHONE_NUMBER>` |
| Unix/Windows 用户路径 | `<USER>` / `<PATH>` |

---

## Knowledge Cluster（知识聚类）

将语义相关的记忆自动分组，形成知识簇。知识簇是 Skill Hub 进行技能结晶的原料——当一个簇积累足够多的记忆时，Skill Hub 的进化引擎会将其结晶为结构化技能。

### 工作原理

每条新记忆上传后，自动按 embedding 余弦相似度分配到最近的簇（阈值 ≥ `cluster_similarity_threshold`，默认 0.75），或创建新簇。簇的质心（centroid）随成员变化动态更新。

```
新记忆上传
    ↓
计算与所有簇质心的余弦相似度
    ↓
├─ 最高相似度 ≥ 0.75 → 加入该簇，更新质心
└─ 所有簇 < 0.75     → 创建新簇
```

### 与 Skill Hub 的协作

Knowledge Cluster 负责"分组"，Skill Hub 的进化引擎负责"结晶"：

| 阶段 | 负责方 | 触发条件 |
|------|--------|----------|
| 记忆聚类 | Memory Hub (Knowledge Cluster) | 每条记忆上传时 |
| 结晶就绪判定 | Memory Hub (Knowledge Cluster) | 簇内记忆数 ≥ `crystallization_threshold`（默认 5） |
| 技能结晶 | Skill Hub (Evolution Engine) | 读取就绪簇，LLM 合成技能 |
| 重新结晶判定 | Memory Hub (Knowledge Cluster) | 已结晶簇新增记忆 ≥ `recrystallization_delta`（默认 3） |
| 技能重新结晶 | Skill Hub (Evolution Engine) | 读取簇内全部记忆，重新合成 |

### API

| 方法 | 说明 |
|------|------|
| `assign_memory_to_cluster(memory)` | 分配记忆到簇 |
| `get_clusters_ready_to_crystallize()` | 获取达到临界质量但未结晶的簇 |
| `get_clusters_ready_to_recrystallize()` | 获取有足够新记忆的已结晶簇 |
| `get_cluster_memories(cluster_id)` | 获取簇内所有记忆 |
| `run_initial_clustering()` | 一次性对所有现有记忆执行聚类 |

### 数据模型

```python
KnowledgeCluster:
    cluster_id: str          # UUID
    topic: str               # LLM 生成的主题标签
    memory_ids: List[str]    # 属于该簇的记忆
    centroid: List[float]    # 聚类中心 embedding
    skill_slug: Optional[str]       # 已结晶的技能（由 Skill Hub 回写）
    superseded_slugs: List[str]     # 被合并替代的旧技能
```

### 配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `ULTRON_CLUSTER_SIMILARITY_THRESHOLD` | `0.75` | 记忆加入簇的相似度阈值 |
| `ULTRON_CRYSTALLIZATION_THRESHOLD` | `5` | 簇结晶的最小记忆数 |
| `ULTRON_RECRYSTALLIZATION_DELTA` | `3` | 触发重新结晶的新记忆增量 |

---

## HTTP API

### 摄取

```
POST /ingest
{"paths": ["/path/to/file.txt", "/path/to/sessions/"]}

POST /ingest/text
{"text": "原始文本内容..."}
```

### 记忆

```
POST /memories/upload
{"content": "...", "context": "...", "resolution": "...", "tags": [...]}

POST /memories/search
{"query": "...", "detail_level": "l1", "limit": 10}

POST /memories/details
{"ids": ["id1", "id2"]}
```

## 依赖

1. **DashScope API Key**：环境变量 `DASHSCOPE_API_KEY`
2. **LLM 可用**：默认使用 `qwen3.6-flash`（非 jsonl 摄取提取、记忆合并等）；任务分割和 trajectory 指标模型使用配置中的 LLM 服务，见 [配置](Config.md) 与 [轨迹中心](TrajectoryHub.md)
3. **Embedding 服务**：用于语义检索和聚类

如果主 LLM 不可用，非 jsonl 摄取可能失败或受限；trajectory 指标模型不可用时会**跳过**指标分析，segment 保持未标注直至恢复。
