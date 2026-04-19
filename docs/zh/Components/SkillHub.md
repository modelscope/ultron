---
slug: SkillHub
title: 技能中心
description: Ultron（奥创）技能中心：存储、检索、进化一体化
---

# 技能中心

技能中心（Skill Hub）是 Ultron 的结构化知识库，存储从记忆中凝练或由 Agent 上传的可复用技能，支持语义检索、自动分类与自进化。

Skill Hub 整合两大子系统：


| 子系统      | 职责                  |
| -------- | ------------------- |
| **技能管理** | 存储、检索、分类、上传、安装      |
| **技能进化** | 从知识簇结晶技能，随新知识持续重新结晶 |


---

## 核心概念

### 技能结构

每个技能由以下部分组成：


| 组成部分 | 文件           | 说明                             |
| ---- | ------------ | ------------------------------ |
| 元数据  | `_meta.json` | 所有者、版本、发布时间等                   |
| 内容   | `SKILL.md`   | YAML frontmatter + Markdown 正文 |
| 脚本   | `scripts/`   | 可选的辅助脚本                        |


### 技能来源


| 取值          | 说明                          |
| ----------- | --------------------------- |
| `evolution` | 从知识簇结晶或重新结晶                 |
| `catalog`   | 与 ModelScope Skill Hub 目录同步 |


## 使用示例

### 检索技能

```python
from ultron import Ultron

ultron = Ultron()

results = ultron.search_skills(
    query="如何解决 Python 导入错误",
    limit=5,
)

for r in results:
    print(f"技能: {r.skill.name}")
    print(f"  描述: {r.skill.description}")
    print(f"  相似度: {r.similarity_score:.4f}")
```

### 上传技能

```python
# 从目录上传（目录需包含 SKILL.md + _meta.json）
result = ultron.upload_skills(
    paths=["/path/to/my-skill-dir"],
)

# 批量：扫描父目录下所有含 SKILL.md 的子目录
result = ultron.upload_skills(
    paths=["/path/to/skills-folder"],
)
```

## 技能目录结构

```
~/.ultron/skills/
├── python-import-error-1.0.0/
│   ├── _meta.json
│   ├── SKILL.md
│   └── scripts/
│       └── check_imports.py
├── docker-debugging-1.0.0/
│   ├── _meta.json
│   └── SKILL.md
└── ...
```

## SKILL.md 格式

```markdown
---
name: python-import-error
description: 解决 Python 模块导入错误
metadata:
  ultron:
    categories:
      - debugging
      - python
    complexity: low
    source_type: evolution
---

# Python 导入错误解决方案

## 问题描述

当遇到 `ModuleNotFoundError` 错误时...

## 解决步骤

1. 检查模块是否安装
2. ...

## 示例

```python
# 示例代码
```

## 与记忆的关系

可复用技能主要由 **知识簇进化**（`evolution`）从多条相关记忆中结晶得到；记忆先经聚类入簇，再由进化引擎生成或更新对应技能。ModelScope 目录技能为 `**catalog`**，与记忆管线独立。

---

## 技能自进化

### 设计哲学

Skill Hub 是一个仓库服务，它无法执行技能、观察运行时表现。这个约束决定了进化的信号来源只能是 Ultron 自身可观察的数据：Memory 的积累速度、embedding 的语义聚集程度、以及 LLM 对结构质量的评估。

由此产生了一个核心设计决策：**技能不是手写的，也不是一次性生成的，而是从群体经验中"结晶"出来的**。当足够多的相关记忆聚集在同一语义空间时，它们共同指向一个可复用的工作流模式——这个模式就是技能的原型。随着新经验持续流入，技能不断"重新结晶"，但每次进化都必须在结构质量上严格优于上一版，否则拒绝发布，保留旧版。

这个设计解决了两个对立的风险：

- **过早结晶**：记忆太少时合成的技能缺乏代表性，容易产生幻觉或过拟合单一案例
- **无限漂移**：每次有新记忆就重写，会破坏已经验证过的有效内容

### 三层流水线

进化流程分三个阶段，由不同组件负责：


| 阶段       | 触发条件                     | 负责组件                      | 核心行为                                                                                    |
| -------- | ------------------------ | ------------------------- | --------------------------------------------------------------------------------------- |
| **知识聚类** | 每条新记忆入库时                 | `KnowledgeClusterService` | 按 embedding 余弦相似度（阈值 0.75）将记忆归入最近的 cluster，或新建 cluster；cluster 质心为成员 embedding 的均值，动态更新 |
| **结晶**   | cluster 内记忆数 ≥ 5 且尚无关联技能 | `SkillEvolutionEngine`    | LLM 从全部记忆中合成多步骤工作流型技能；通过质量门和来源可溯验证后落盘为 v1.0                                             |
| **重新结晶** | 已结晶的 cluster 新增记忆 ≥ 3 条  | `SkillEvolutionEngine`    | 以当前技能为骨架，纳入全部记忆重新合成；新结构分必须严格高于旧版才发布新版本                                                  |


聚类阶段是进化的"感知层"——纯粹依赖 embedding 相似度，无 LLM 调用，可在每次记忆入库时同步执行。结晶和重新结晶是"合成层"，涉及多次 LLM 调用，在后台批量执行。

### 结晶（Crystallization）

结晶是从零生成技能的过程。触发条件是 cluster 达到临界质量（默认 ≥5 条记忆）——单条记忆描述的是一个具体事件，五条以上相似记忆才能揭示出跨场景的通用模式。

LLM 被要求合成一个**多步骤工作流型技能**，而非简单汇总，具体要求包括：触发条件（何时使用）、步骤序列（≥3 步，每步有明确输入/输出）、边界处理（常见异常和回退策略）、决策分支（不同情况下的不同路径）。

如果记忆过于分散、无法形成连贯工作流，LLM 返回 `quality: insufficient`，不生成技能。这个"主动拒绝"机制避免了强行合成低质量技能。

### 重新结晶（Re-crystallization）

重新结晶以**当前技能为骨架**，而非从零开始。LLM 被明确要求"默认做定向修改而非重写"，优先保留已有内容，只在有实质新知识时才更新。

这个设计有两层考量：第一，已结晶的技能经过了质量门和来源可溯验证，是有保障的内容，重写意味着放弃这些保障；第二，定向修改更容易被升级门评估——如果新内容确实有价值，结构分会提升；如果只是噪声，结构分不会提升，升级门会拒绝发布。

如果新记忆无实质价值，LLM 返回 `evolution: unnecessary`，直接跳过，不进入后续验证流程。

### 两道质量门

#### 质量门（`_meets_quality_bar`）

质量门是轻量级启发式检查，在 LLM 验证之前执行，用于过滤明显不合格的输出，避免浪费验证调用。


| 检查项  | 判断方式                       | 说明           |
| ---- | -------------------------- | ------------ |
| 最小长度 | token 数 ≥ 150（无 LLM 时按字符数 ÷ 3 估算） | 硬性门槛，不满足直接拒绝 |
| 步骤结构 | 正则匹配编号/列表/标题，≥ 3 个         | 确保有实质性步骤     |
| 触发条件 | 关键词匹配（when/trigger/适用/触发等） | 确保说明了使用场景    |
| 边界处理 | 关键词匹配（error/fail/异常/回退等）   | 确保覆盖了异常情况    |


规则：最小长度必须满足，且后三项中满足 ≥ 2 项，才通过质量门。

#### 来源可溯验证（`verify_skill`）

来源可溯验证由**独立 LLM** 执行，与合成 LLM 分离，避免自我验证的偏差。验证器对技能中的每个步骤/声明做溯源判断：


| 溯源状态           | 含义            |
| -------------- | ------------- |
| `grounded`     | 可在源记忆中找到依据    |
| `hallucinated` | 源记忆中无对应证据（幻觉） |
| `contradicted` | 与源记忆内容矛盾      |


通过条件：`grounded_in_evidence ≥ 0.8` 且 `has_contradiction = false`。

这道门的存在是因为 LLM 合成过程天然有幻觉风险——它可能"补全"出听起来合理但实际上没有记忆支撑的步骤。来源可溯验证将技能内容锚定在真实经验上，确保技能是经验的提炼而非 LLM 的创作。

### 结构分与升级门

验证通过后，系统计算结构分（structure score），作为版本间比较的量化依据：


| 维度                            | 权重   | 含义                  |
| ----------------------------- | ---- | ------------------- |
| `workflow_clarity`            | 0.35 | 步骤是否清晰、有序、可执行       |
| `specificity_and_reusability` | 0.35 | 指令是否具体且可复用，而非泛泛建议   |
| `preserves_existing_value`    | 0.30 | 重新结晶时：是否保留了旧版本的有效内容 |


**结构分** = 0.35 × workflow_clarity + 0.35 × specificity_and_reusability + 0.30 × preserves_existing_value

**升级门**：重新结晶时，新结构分必须严格高于旧版本的结构分，才发布新版本。否则记录 `revert` 状态，保留旧版。

升级门解决了一个根本问题：如何防止"进化"实际上是退化？纯粹依赖 LLM 判断"新版本是否更好"是不可靠的，因为 LLM 倾向于认为更长、更详细的内容更好。结构分提供了一个可量化、可比较的标准，使版本间的优劣判断有据可查，并且可以在进化历史中追溯。

### 进化记录

每次结晶、重新结晶或被拒绝，都写入一条 `EvolutionRecord`：

```python
EvolutionRecord:
    skill_slug: str          # 技能标识
    cluster_id: str          # 来源 cluster
    old_version: str         # 旧版本号（结晶时为 None）
    new_version: str         # 新版本号（被拒绝时为空）
    old_score: float         # 旧结构分
    new_score: float         # 新结构分
    status: str              # crystallized | recrystallized | revert | constraint_failed
    trigger: str             # initial_clustering | new_memory | manual | background
    memory_count: int        # 参与合成的记忆总数
    mutation_summary: str    # 本次变更摘要
```

`revert` 表示升级门拒绝，`constraint_failed` 表示来源可溯验证失败。可通过 `/skills/evolution-history` 查询完整进化历史。

### 后台执行

进化没有独立的定时器。`run_evolution_cycle()` 在 `_decay_loop` 的同一节拍执行（紧跟 tier rebalance 之后），间隔由 `decay_interval_hours` 控制。每轮进化分两个阶段，共享一个批次上限（默认 3）：


| 阶段  | 处理对象                       | 优先级  |
| --- | -------------------------- | ---- |
| 阶段一 | 待结晶的 cluster（已达临界质量，尚无技能）  | 优先   |
| 阶段二 | 待重新结晶的 cluster（新增记忆已达增量阈值） | 剩余配额 |


阶段一优先的原因：结晶是从无到有，价值更高；重新结晶是增量改进，可以等下一轮。

---

## 外部技能目录（ModelScope Skill Hub）

Ultron 支持从 ModelScope Skill Hub 检索技能（80,364 条），与内部技能统一检索、按相似度排序返回。

### 统一检索

调用 `search_skills` 时，搜索结果同时包含内部技能和目录技能，按相似度排序。每条结果带以下字段用于区分来源：


| 字段          | 说明                                    |
| ----------- | ------------------------------------- |
| `source`    | `"internal"`（内部技能）或 `"catalog"`（目录技能） |
| `full_name` | 目录技能的完整名称，如 `@ns/skill-name`          |


### 安装技能

`install_skill_to` 统一处理两个来源：优先查找 Ultron 内部技能（按 slug），找不到则通过 `modelscope skill add` 从 ModelScope 安装。

```python
# 安装内部技能（直接用 slug）
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

---

## HTTP API


| 端点                          | 方法   | 说明                   |
| --------------------------- | ---- | -------------------- |
| `/skills/search`            | POST | 语义检索技能（内部 + 目录统一返回）  |
| `/skills/upload`            | POST | 上传技能包                |
| `/skills/install`           | POST | 安装技能到指定目录            |
| `/skills/clusters`          | GET  | 查看所有 cluster 及其状态    |
| `/skills/evolution-history` | GET  | 查看进化历史（结晶/重新结晶/拒绝记录） |


---

## 配置


| 环境变量                                  | 默认值    | 说明                    |
| ------------------------------------- | ------ | --------------------- |
| `ULTRON_EVOLUTION_ENABLED`            | `true` | 是否启用进化                |
| `ULTRON_EVOLUTION_BATCH_LIMIT`        | `3`    | 每个进化周期最多处理的 cluster 数 |
| `ULTRON_CLUSTER_SIMILARITY_THRESHOLD` | `0.75` | 记忆归入 cluster 的余弦相似度阈值 |
| `ULTRON_CRYSTALLIZATION_THRESHOLD`    | `5`    | 触发结晶所需的最少记忆数          |
| `ULTRON_RECRYSTALLIZATION_DELTA`      | `3`    | 触发重新结晶所需的新增记忆数        |


