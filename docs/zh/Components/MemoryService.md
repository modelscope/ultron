---

## slug: MemoryService

title: 记忆服务
description: Ultron (奥创) 远程记忆管理服务

# 记忆服务

记忆服务（MemoryService）是 Ultron 的核心组件，负责多智能体共享记忆的管理，包括上传、去重、百分位层级重分配、语义检索等功能。

## 核心概念

### 记忆层级 (Tier)


| 层级       | 说明            | 行为                                  |
| -------- | ------------- | ----------------------------------- |
| **HOT**  | 高频命中（top N%）  | 对所有智能体即时可用                          |
| **WARM** | 中频命中（next M%） | 上下文匹配时返回                            |
| **COLD** | 低频命中（剩余）      | 默认参与检索，但排名靠后（tier boost 0.8 + 时间衰减） |


层级由 `**run_tier_rebalance`** 定期批量重分配（后台任务，间隔 `decay_interval_hours`）：

1. 按 `hit_count` DESC、`last_hit_at` DESC 排序所有活跃记忆
2. 前 `hot_percentile`%（默认 10%）→ HOT
3. 接下来 `warm_percentile`%（默认 40%）→ WARM
4. 其余 → COLD
5. 首次进入 HOT 的记忆自动触发技能生成（`_try_auto_generate_skill`）
6. 超过 `cold_ttl_days` 的 COLD 记忆标记为 `archived`（不删除，但不再参与检索和重分配）

`hit_count` 由三种采纳信号驱动：


| 信号              | 权重  | 说明         |
| --------------- | --- | ---------- |
| Details（拉取全文）   | +2  | agent 主动选择 |
| Search（出现在检索结果） | +1  | 被检索到       |
| Merge（去重合并）     | +1  | 相似记忆上传     |


### 记忆状态 (Status)


| 状态         | 说明                        |
| ---------- | ------------------------- |
| `active`   | 所有活跃记忆的默认状态               |
| `archived` | 超过 COLD TTL 后归档，不参与检索和重分配 |


### 记忆类型 (MemoryType)

由服务端 LLM 自动判定，**调用方不可指定**。系统根据内容自动分类为以下类型之一：


| 类型           | 说明                     |
| ------------ | ---------------------- |
| `error`      | 错误经验（工程/工具等）           |
| `security`   | 安全事件                   |
| `correction` | 纠正/修正                  |
| `pattern`    | 观察到的模式                 |
| `preference` | 显式偏好                   |
| `life`       | 可共享的生活类客观经验（如「乘机选座窍门」） |


## 使用示例

### 上传记忆

```python
from ultron import Ultron

ultron = Ultron()

# 记忆类型由服务端自动判定
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

### 检索记忆

```python
# 语义检索（跨全部类型）
results = ultron.search_memories(
    query="Python 模块导入错误",
    detail_level="l1",  # l0=摘要向, l1=更多上下文字段；全文用 get_memory_details
    limit=10,
)

for r in results:
    print(f"[{r.record.memory_type}] {r.record.content[:50]}...")
    print(f"  相似度: {r.similarity_score:.4f}")
```

### 获取记忆全文

```python
memory_ids = ["id1", "id2", "id3"]
details = ultron.get_memory_details(memory_ids)
```

## 上传与去重合并（`upload_memory`）

入口方法为 `MemoryService.upload_memory`；命中近重复时的收尾逻辑在 `**_complete_near_duplicate_upload**`。

**扫描范围**：在同一 `**memory_type`** 下，对 **HOT**、**WARM** 和 **COLD** 嵌入做近重复检索。

**判定**：新向量与候选向量余弦相似度 **大于** `dedup_similarity_threshold`（默认 0.85）则视为同一条记忆。

**命中后的步骤**：

1. **日志**：`log_event`（如 `upload_memory.dedup_hit`）。
2. **统计与贡献**：`increment_memory_hit` 递增命中，本条原文写入 `**memory_contributions`**。
3. **合并正文**：`_merge_memory_fields` — 若配置了 `llm_service` 则尝试 `**LLMService.merge_memories`**（字段长度受 `memory_merge_max_field_tokens` 约束，解析后截断），失败则回退为规则合并 `**_merge_pair_fields`**（子串则保留较长文本，否则用 `---` 分隔块拼接），再经 `_cap_merge_field_by_tokens`。
4. **写回主表**：
  - 若 **content/context/resolution** 任一相对库中旧值变化：对新正文 **重算 embedding**，**再生 L0/L1**（`_generate_summaries`），`**update_memory_merged_body`**（含合并后的 `tags`）。
  - 若正文未变仅 **tags** 变化：`**update_memory_merged_body`** 只更新标签，保留原向量与摘要。

**未命中**：创建新 `**MemoryRecord`**（WARM、active），`save_memory_record`；日志 `upload_memory.created`。

## L0 / L1 / Full 三级上下文

每条记忆自动生成三个粒度的内容，检索时按需选择返回层级，节省 token：


| 级别     | 内容                                         | 用途                              |
| ------ | ------------------------------------------ | ------------------------------- |
| `l0`   | 一句话摘要（`summary_l0`），正文类字段清空                | 快速浏览，最省 token                   |
| `l1`   | 核心概览（`summary_l0` + `overview_l1`），保留更多上下文 | 缩小候选后再拉详情                       |
| `full` | 完整原始内容（`content`、`context`、`resolution`）   | 通过 `get_memory_details` 按 ID 拉取 |


语义检索（`search_memories`）仅支持 `l0` 和 `l1`；完整正文一律通过 `get_memory_details` 二次拉取。

```python
# L0 检索（最省 token）
results_l0 = ultron.search_memories(query, detail_level="l0")

# 根据 L0/L1 选择后获取全文
selected_ids = [r.record.id for r in results_l0[:3]]
full_records = ultron.get_memory_details(selected_ids)
```

## 时间衰减

记忆的"热度"随时间衰减：

```
hotness = exp(-decay_alpha * days_since_last_hit)
```

衰减影响检索排序（权重由 `time_decay_weight` 控制），但不直接导致层级变化。层级完全由 `run_tier_rebalance` 按 `hit_count` 百分位重分配。

## 记忆数据结构

主要字段与 `ultron.core.models.MemoryRecord` 一致，例如：`id`、`memory_type`、`content`、`context`、`resolution`、`tier`、`status`、`hit_count`、`tags`、`embedding`、`summary_l0`、`overview_l1`、`generated_skill_slug`、`created_at`、`last_hit_at`。

## 数据脱敏

记忆上传时，`content`、`context`、`resolution` 字段在写入数据库前会自动脱敏，防止敏感信息持久化。

脱敏基于 **[Microsoft Presidio](https://github.com/microsoft/presidio)**（开源 PII 检测框架），使用 spaCy 作为 NLP 后端，支持中英文双语（`en_core_web_sm` / `zh_core_web_sm`）。语言由文本中汉字占比自动判断。

在 Presidio 之外，额外用正则覆盖 API Key、Token、路径等场景：


| 类型                    | 替换标签                                          |
| --------------------- | --------------------------------------------- |
| 邮箱、电话、IP、人名等          | Presidio 默认标签（如 `<EMAIL_ADDRESS>`、`<PERSON>`） |
| OpenAI / LLM API Key  | `<LLM_API_KEY>`                               |
| GitHub Token          | `<GITHUB_TOKEN>`                              |
| AWS Access Key        | `<AWS_ACCESS_KEY>`                            |
| Bearer / Basic 认证头    | `<REDACTED_TOKEN>`                            |
| 通用凭证字段（`password=` 等） | `<REDACTED_CREDENTIAL>`                       |
| UUID                  | `<UUID>`                                      |
| 中国手机号                 | `<PHONE_NUMBER>`                              |
| Unix/Windows 用户路径     | `<USER>` / `<PATH>`                           |


脱敏在 `DataSanitizer`（`utils/sanitizer.py`）中实现，由 `MemoryService` 在写入前自动调用，调用方无需关心。