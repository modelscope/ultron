# Ultron Skill 自进化系统

## 概述

Ultron 作为 Skill Hub，通过 **Knowledge Cluster → Crystallization → Re-crystallization** 机制实现 skill 的自动进化。核心思路：将同领域的 N 条 memory 聚合结晶为完整的工作流 skill，并随着新知识流入持续重新结晶。

### 解决的问题

当前 1:1 的 Memory → Skill 策略产生了大量窄小、重叠的 skill（云端 194 个）。例如 agent 初始化领域有 4 个重叠 skill，安全领域有 5+ 个，各自只覆盖一个侧面。进化系统将这些碎片合并为完整的多步骤工作流。

### 设计约束

Ultron 是 Skill Hub（技能仓库服务），不是 Agent。它不执行 skill，无法观察运行时表现。所有进化信号基于 Ultron 自身可观察的数据：Memory 积累、embedding 相似度、LLM 结构评估。

---

## 调研基础

| 项目 | 核心机制 | 对 Ultron 的启发 |
|------|---------|-----------------|
| **darwin-skill**（https://github.com/alchaincyf, 991 stars） | 8 维评估、棘轮机制（分数只升不降）、单变量控制、探索性重写 | 棘轮门控、结构评估维度 |
| **Hermes Agent**（https://github.com/NousResearch/hermes-agent, 92K stars） | 运行时 skill patch、复杂任务后自动创建 skill | skill 应来自复杂工作流的聚合，不是单条 tip |
| **Hermes Self-Evolution**（https://github.com/NousResearch/hermes-self-evolution, 1805 stars） | DSPy + GEPA 反思性变异、LLM-as-Judge、约束门控 | 约束门控体系、独立评分 |
| **SkillClaw**（https://github.com/AMAP-ML/skillclaw, 670 stars） | session 聚合进化、保守编辑、失败归因、4 维验证 | 保守编辑原则、知识溯源验证、Evolve Server 也不执行 skill |

---

## 架构

```
Memory 持续流入
    │
    ▼
Phase 1: Knowledge Clustering（知识聚类）
    按 embedding 相似度将 memory 聚类
    │
    ▼ (cluster 达到临界质量，默认 ≥3 条)
Phase 2: Crystallization（结晶）
    从整个 cluster 的 N 条 memory 合成多步骤工作流 skill
    │
    ▼ (新 memory 流入 cluster，增量 ≥2 条)
Phase 3: Re-crystallization（重新结晶 = 进化）
    用更丰富的 memory 集合重新合成，棘轮门控保证只升不降
```

---

## 模块说明

### 1. KnowledgeClusterService (`services/skill/skill_cluster.py`)

将 memory 按语义相似度聚类。每条新 memory 上传时自动分配到最近的 cluster（cosine similarity > 0.6），或创建新 cluster。

- `assign_memory_to_cluster(memory)` — 分配 memory 到 cluster
- `get_clusters_ready_to_crystallize()` — 找到达到临界质量但未结晶的 cluster
- `get_clusters_ready_to_recrystallize()` — 找到有足够新 memory 的已结晶 cluster
- `run_initial_clustering()` — 一次性对所有现有 memory 执行聚类

### 2. SkillEvolutionEngine (`services/skill/skill_evolution.py`)

进化引擎，执行结晶和重新结晶。

- `crystallize_cluster(cluster)` — 从 cluster 结晶出新 skill
- `recrystallize_skill(cluster)` — 用新知识重新结晶已有 skill
- `run_evolution_cycle()` — 一个完整的进化周期（结晶 + 重新结晶）

### 3. LLM Prompts (`utils/llm_orchestrator.py` 新增方法)

| 方法 | 用途 |
|------|------|
| `crystallize_skill_from_cluster()` | 从 N 条 memory 合成多步骤工作流 skill |
| `recrystallize_skill()` | 用新知识增强已有 skill（保守编辑） |
| `verify_skill()` | 独立验证：知识溯源 + 结构评分 |
| `generate_cluster_topic()` | 为 cluster 生成主题标签 |

---

## 进化流程详解

### 结晶（Crystallization）

```
Cluster 达到临界质量 (≥3 memories)
    │
    ▼
LLM 合成：N 条 memory → 多步骤工作流 skill
    │
    ▼
质量门槛检查：
    - ≥3 个步骤
    - 有触发条件
    - 有边界处理
    - 内容 ≥500 字符
    (至少满足 3 项)
    │
    ▼
独立 LLM 验证：
    - 知识溯源：grounded_in_evidence ≥ 0.8
    - 无矛盾：has_contradiction = false
    - 结构评分：workflow_clarity + specificity_and_reusability
    │
    ▼
保存 Skill v1.0，旧 1:1 skill → ARCHIVED
```

### 重新结晶（Re-crystallization = 进化）

```
Cluster 新增 ≥2 条 memory
    │
    ▼
LLM 重新合成：当前 skill 作为骨架 + 所有 memory（含新增）
    │
    ▼
质量门槛 + 独立验证（同上）
    │
    ▼
棘轮门控：new_structure_score > old_structure_score？
    ├─ 是 → Skill v1.1 (ACTIVE), parent_version = "1.0.0"
    └─ 否 → 保持 v1.0，记录 revert
```

### 验证维度

| 维度 | 权重 | 说明 |
|------|------|------|
| `grounded_in_evidence` | 门槛 ≥0.8 | skill 中的步骤能否在源 memory 中找到依据 |
| `has_contradiction` | 门槛 = false | 是否与源 memory 矛盾 |
| `workflow_clarity` | 0.35 | 步骤是否明确、有序、可执行 |
| `specificity_and_reusability` | 0.35 | 具体且可复用，非通用建议 |
| `preserves_existing_value` | 0.30 | 重新结晶时：是否保留了旧版本的有效内容 |

---

## 数据模型

### KnowledgeCluster

```python
cluster_id: str          # UUID
topic: str               # LLM 生成的主题标签
memory_ids: List[str]    # 属于该 cluster 的 memory
centroid: List[float]    # 聚类中心 embedding
skill_slug: Optional[str]       # 已结晶的 skill
superseded_slugs: List[str]     # 被合并替代的旧 skill
```

### EvolutionRecord

```python
skill_slug: str
cluster_id: str
old_version / new_version: str
old_score / new_score: float
status: str    # "crystallized" | "recrystallized" | "revert" | "constraint_failed"
trigger: str   # "initial_clustering" | "new_memory" | "manual" | "background"
memory_count: int
mutation_summary: str
```

### SkillMeta 新增字段

```python
cluster_id: Optional[str]       # 所属 cluster
evolution_count: int             # 进化次数
structure_score: Optional[float] # 结构评分
```

---

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/skills/evolve` | POST | 手动触发进化（指定 cluster 或全自动） |
| `/skills/clusters` | GET | 查看所有 cluster 及其状态 |
| `/skills/evolution-history` | GET | 查看进化历史 |
| `/skills/feedback` | POST | agent 上报 skill 使用结果（转化为 memory） |

### POST /skills/evolve

```json
// 请求
{"cluster_id": "可选，指定 cluster", "limit": 3}

// 响应（指定 cluster）
{"success": true, "data": {"skill_slug": "agent-init-auth", "version": "1.1.0"}}

// 响应（全自动）
{"success": true, "data": {"crystallized": 2, "recrystallized": 1}}
```

### GET /skills/clusters

```json
{
  "success": true,
  "count": 35,
  "data": [
    {
      "cluster_id": "abc123",
      "topic": "Agent 初始化与认证",
      "size": 5,
      "skill_slug": "agent-init-auth",
      "ready_to_crystallize": false,
      "ready_to_recrystallize": true
    }
  ]
}
```

---

## 配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `ULTRON_EVOLUTION_ENABLED` | `true` | 是否启用进化 |
| `ULTRON_CLUSTER_SIMILARITY_THRESHOLD` | `0.6` | memory 加入 cluster 的相似度阈值 |
| `ULTRON_CRYSTALLIZATION_THRESHOLD` | `3` | cluster 结晶的最小 memory 数 |
| `ULTRON_RECRYSTALLIZATION_DELTA` | `2` | 触发重新结晶的新 memory 增量 |
| `ULTRON_EVOLUTION_BATCH_LIMIT` | `3` | 每个进化周期最多处理的 skill 数 |

---

## 集成点

### Memory 上传时

每条新 memory 上传后自动调用 `cluster_service.assign_memory_to_cluster()`，分配到最近的 cluster 或创建新 cluster。

### 背景任务（每 6 小时）

在现有的 `_decay_loop` 中，tier rebalance 和 consolidation 之后执行 `evolution_engine.run_evolution_cycle()`。

### Agent 反馈（可选）

agent 通过 `POST /skills/feedback` 上报使用结果，转化为 correction 类型的 memory，通过正常的 knowledge_gap 信号触发进化。保持架构一致性——所有进化信号最终都通过 Memory 系统传导。

---

## 文件清单

| 文件 | 状态 | 说明 |
|------|------|------|
| `core/models.py` | 修改 | 新增 KnowledgeCluster、EvolutionRecord；SkillMeta 增加 3 个字段 |
| `core/database.py` | 修改 | 组合 _ClusterMixin |
| `core/db_cluster.py` | 新增 | 聚类和进化记录的 DB 操作 |
| `config.py` | 修改 | 5 个进化配置项 |
| `services/skill/skill_cluster.py` | 新增 | KnowledgeClusterService |
| `services/skill/skill_evolution.py` | 新增 | SkillEvolutionEngine |
| `utils/llm_orchestrator.py` | 修改 | 4 个新 LLM 方法 |
| `api/schemas.py` | 修改 | EvolveSkillRequest、SkillFeedbackRequest |
| `api/routers/skills.py` | 修改 | 4 个新端点 |
| `server_state.py` | 修改 | cluster_service、evolution_engine 引用 |
| `server.py` | 修改 | 初始化进化服务 + 背景任务 |
| `services/memory/memory_service.py` | 修改 | 上传时自动加入 cluster |
