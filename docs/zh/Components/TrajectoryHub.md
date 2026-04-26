---
slug: TrajectoryHub
title: 轨迹中心
description: Ultron（奥创）对话采集、任务分割、trajectory 指标分析、记忆延迟提取与 SFT 导出
---

# 轨迹中心（Trajectory Hub）

轨迹中心负责**对话的采集与智能处理**：将上传的 `.jsonl` 会话文件通过 LLM 自动拆分为独立的 **task segment（任务段）**，再通过 `ms_agent.trajectory` 为每个任务段计算指标。只有满足指标阈值的 segment 会进入记忆抽取或 SFT 风格训练数据导出。

---

## 任务分割（Task Segmentation）

一个 `.jsonl` 会话文件可能包含**多个不同任务**的对话。轨迹中心会使用 LLM 自动将一个 conversation 拆分为独立的 **task segment**，以 segment 为粒度进行 trajectory 指标分析和记忆提取。

### 核心概念


| 概念                         | 说明                                        |
| -------------------------- | ----------------------------------------- |
| **Task Segment**           | 一个 conversation 中的独立任务片段，由 LLM 自动识别边界     |
| **Content Fingerprint**    | 基于 segment 消息内容的 SHA-256 哈希（16 字符），用于增量追踪 |
| **Segment-level Pipeline** | 指标分析、记忆提取、SFT 导出均在 segment 粒度独立执行         |


### 分割与增量规则

1. **LLM 分割**（长对话可能**多轮**调模型，每轮只看一个「窗口」里的消息）：
  - 每一轮：在不超过用户文本 token 预算的前提下，从**当前起点**尽量多装几条消息进窗口；模型只用**本窗口内**下标 `1…L` 切出若干 task。
  - **本轮切出多段**：下一轮窗口从**上一段里「最后那个 task」的第一条消息**开始，再往后装到预算；与上一轮重叠的那一段会被**新一轮结果覆盖**（合并时先去掉从该起点往后的旧段，再追加本轮结果）。
  - **本轮只有一段**且正好占满当前窗口、后面还有话：下一轮从**紧接本窗之后**那条开始，**不重叠**。
  - **单条消息**仍超过预算时，只在「这一条单独成窗」时截断展示；`role: tool` 但 name / id / content 全空的行**仍保留**，与源 JSONL 条数和下标对齐（展示为空行）。
   **示例**（消息编号为对话中的顺序，从 1 起）：
  - 假设第一次窗口装进第 1～6 条，模型切成 task A＝1～3、task B＝4～6。第二次窗口从第 **4** 条起再尽量往后装（例如 4～10），模型可能把 B 改成 4～7 并新切出 C＝8～10；最终保留的 B 以**第二次**为准。
  - 若第一次 1～6 只切出**一段** 1～6，则第二次从第 **7** 条起装窗口（不重叠）。
2. **指纹计算**：对每个 segment 的消息内容计算 SHA-256 指纹（`role + content` 拼接）
3. **增量对比**：
  - 指纹**匹配**已有 segment → **跳过**（幂等）
  - 指纹**不匹配**（如文件追加后任务 C 从部分变为完整） → 废弃旧 segment 对应的 memory（通过 `segment:{id}` tag 精准定位并 archive），删除旧 segment 记录，插入新 segment
4. **短对话**：对话 ≤ 2 条消息时，直接视为单个 segment（无需 LLM）
5. **LLM 不可用**：分段操作跳过，session 保持 `segmented=0`，等待下一个定时任务周期重试

### 增量追踪示例

```
Day 1: file.jsonl 包含任务 A、B、C（部分）
  → LLM 分割 → [A(fp=x), B(fp=y), C_partial(fp=z1)]
  → 各自独立计算指标 → 满足阈值的 segment 提取 memory（每条 memory 带 segment:{id[:8]} tag）

Day 2: file.jsonl 追加写入，C 变为完整
  → 重新 LLM 分割 → [A(fp=x), B(fp=y), C_complete(fp=z2)]
  → A 跳过（fp=x 匹配） → B 跳过（fp=y 匹配）
  → C: 旧 z1 的 memory 被 archived，旧 segment 删除，新 z2 重新计算指标并在满足阈值时提取
```

---

## 端到端流程

```
【采集】
导出对话为 .jsonl → POST /ingest（需 agent_id）
  → 保存 session 级别行（segmented=0）→ 分段由定时任务异步处理

【定时任务（间隔 decay_interval_hours）】
1. segment_pending_sessions()
     → 获取 segmented=0 的 session → 读取文件 → LLM 任务分割
     → 成功 → 保存 task_segments（指纹去重），标记 segmented=1
     → 对话 ≤ 2 条消息 → 直接创建单个 segment，标记 segmented=1
     → LLM 不可用 → 跳过，保持 segmented=0，下周期再试

2. label_pending_segments()
     → ms_agent.trajectory 将完整分析结果写入 `quality_metrics`（`summary.overall_score`、`summary.task_type` 等在 JSON 内），labeled=1
     → ms-agent trajectory 分析不可用则跳过，保持 labeled=0，下周期再试

3. extract_memories_from_segments()
     → 按 `quality_metrics` 中 `summary.overall_score`（0–1）与配置阈值做粗筛、memory_extracted=0 且通过 `is_memory_eligible` 的任务段
     → 读取对应消息范围 → MemoryService.upload_memory
     → 每条 memory 带 segment:{id[:8]} tag → memory_extracted=1

4. tier rebalance → skill evolution → consolidation（若启用）
```

---

## 数据库表

### `task_segments`


| 字段                 | 类型               | 说明                                                                                                                             |
| ------------------ | ---------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `id`               | TEXT PK          | UUID                                                                                                                           |
| `agent_id`         | TEXT NOT NULL    | 与 ingest 的 `agent_id` 对应                                                                                                       |
| `session_file`     | TEXT NOT NULL    | 源文件绝对路径                                                                                                                        |
| `segment_index`    | INTEGER NOT NULL | 在该文件中的序号（0-based）                                                                                                              |
| `start_line`       | INTEGER NOT NULL | 起始行号（1-based inclusive）                                                                                                        |
| `end_line`         | INTEGER NOT NULL | 结束行号（1-based inclusive）                                                                                                        |
| `fingerprint`      | TEXT NOT NULL    | SHA-256 内容指纹（16 字符 hex）                                                                                                        |
| `topic`            | TEXT             | LLM 生成的任务主题摘要                                                                                                                  |
| `quality_metrics`  | TEXT             | `ms_agent.trajectory` 的完整分析 JSON；`**summary.overall_score`（0–1）、`summary.task_type` 等只存在于此列**，不在其他列重复存储；查询与 API 需要时可由该 JSON 派生 |
| `labeled`          | INTEGER          | 0=待标注，1=已标注                                                                                                                    |
| `memory_extracted` | INTEGER          | 0=未提取，1=已提取                                                                                                                    |
| `created_at`       | TIMESTAMP        | 创建时间                                                                                                                           |
| `updated_at`       | TIMESTAMP        | 更新时间                                                                                                                           |


**唯一约束**：`UNIQUE(agent_id, session_file, fingerprint)` — 保证同一文件内相同指纹的 segment 不会重复插入。

### `trajectory_records`（Session 元数据）

存储 session 级别元数据（每个 `.jsonl` 文件对应一行，`pair_index=-1`），用于追踪分段状态。


| 字段                | 类型        | 说明                       |
| ----------------- | --------- | ------------------------ |
| `id`              | TEXT PK   | UUID                     |
| `source_agent_id` | TEXT      | 与 ingest 的 `agent_id` 对应 |
| `session_file`    | TEXT      | 源文件绝对路径                  |
| `segmented`       | INTEGER   | 0=未分段，1=已分段              |
| `created_at`      | TIMESTAMP | 创建时间                     |


---

## `.jsonl` 格式

每行一个 JSON 对象。解析见 `ultron/utils/jsonl_session_messages.py`：按**智能体会话**处理，角色为 `user` / `assistant` / `system` / `tool`；**跳过** `_type == "metadata"`。支持 OpenAI 与 Anthropic 两种行形态，默认 `session_format="auto"`。解析后 `filter_messages_for_trajectory` 会丢弃「扩成 LLM 正文后为空」的行；`assistant` 可以只有 `tool_calls` / `reasoning_content` 仍保留。

```jsonl
{"role": "user", "content": "如何用 Python 读取 CSV？"}
{"role": "assistant", "content": "可以使用 pandas.read_csv()..."}
{"role": "user", "content": "帮我写一个 Docker compose 文件"}
{"role": "assistant", "content": "version: '3'\nservices:\n  ..."}
```

上例经分段会得到两个 task segment：CSV 与 Docker compose。

---

## 内容指纹（Content Fingerprint）

指纹基于 segment 中每条消息的 `role` 和 `content` 字段，通过 SHA-256 计算，取前 16 个 hex 字符。

```python
def compute_segment_fingerprint(messages: List[dict]) -> str:
    hasher = hashlib.sha256()
    for msg in messages:
        hasher.update((msg.get("role") or "").encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update((msg.get("content") or "").encode("utf-8"))
        hasher.update(b"\x01")
    return hasher.hexdigest()[:16]
```

指纹的核心作用：

- **幂等**：同一文件重新上传时，已有指纹的 segment 直接跳过
- **变化检测**：文件追加写入导致某个 segment 内容变化时，旧指纹不匹配，触发废弃旧 memory + 重新处理
- **替代行号游标**：不再依赖行号做增量追踪，避免文件追加时任务被撕裂

---

## 记忆失效（Memory Invalidation）

当 segment 内容变化（指纹不匹配）时：

1. 通过 `archive_memories_by_tag("segment:{old_id[:8]}")` 将旧 segment 产生的 memory 标记为 `archived`
2. 删除旧 segment 记录
3. 插入新 segment，后续定时任务会重新计算指标，并在满足阈值时提取

这保证了 memory 始终反映任务段的最新内容。

---

## Trajectory 指标

`label_pending_segments()` 从已安装的 `ms_agent` 包导入 `ms_agent.trajectory`，注入 Ultron 配置好的 `quality_llm` 作为指标模型，仅将结果写入 `quality_metrics`；粗筛与 `is_memory_eligible` 均读取该 JSON 中的 `summary` 与 `metrics`。


| 阈值                                         | 默认值   | 用途                      |
| ------------------------------------------ | ----- | ----------------------- |
| `ULTRON_TRAJECTORY_MEMORY_SCORE_THRESHOLD` | `0.7` | 进入记忆粗筛的最低分（0–1）         |
| `ULTRON_TRAJECTORY_SFT_SCORE_THRESHOLD`    | `0.8` | 进入 SFT 导出/训练粗筛的最低分（0–1） |


---

## SDK 用法（Python）

```python
from ultron import Ultron

u = Ultron()

# 统计（含 segment 子字典）
stats = u.trajectory_service.get_trajectory_stats()
# stats["segments"] = {"total": 15, "labeled": 10, "memory_eligible": 8, "sft_eligible": 6, "memory_extracted": 6}

# 手动触发任务段分割 / 标注 / 提取（一般已由后台 `run_decay_loop` 执行，见 `ultron/services/background.py`）
u.trajectory_service.segment_pending_sessions(batch_size=50)
u.trajectory_service.label_pending_segments(batch_size=50)
u.trajectory_service.extract_memories_from_segments(batch_size=50)

# 导出 SFT 风格训练数据：导出满足指标阈值的独立任务段，可按 task_type 和分数过滤
dataset = u.trajectory_service.export_sft(task_type="code", min_quality_score=0.8, limit=5000)
# [{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}], "topic": "..."}, ...]
```

---

## 相关源码

`TrajectoryService` 为对外门面，内部由会话读取、分段、标注、记忆桥接、SFT 导出等类组合实现；SFT 训练调度在 `services/training/`，与轨迹采集解耦。


| 模块                          | 路径                                                                             |
| --------------------------- | ------------------------------------------------------------------------------ |
| segment 表与 session 元数据表     | `ultron/core/db_trajectory.py`                                                 |
| 轨迹门面（对外 API 不变）             | `ultron/services/trajectory/trajectory_service.py`                             |
| 会话文件与 segment 消息读取          | `ultron/services/trajectory/session_reader.py` — `TrajectorySessionReader`     |
| 任务分段                        | `ultron/services/trajectory/segmenter.py` — `TrajectorySegmenter`              |
| 指标标注                        | `ultron/services/trajectory/labeler.py` — `TrajectoryLabeler`                  |
| 轨迹 → 记忆抽取与上传                | `ultron/services/memory/trajectory_extractor.py` — `TrajectoryMemoryExtractor` |
| SFT 样本与 Twinkle 消息格式        | `ultron/services/training/sft_exporter.py` — `SFTExporter`                     |
| SFT 自训练（Twinkle）            | `ultron/services/training/sft_trainer.py` — `SFTTrainerService`                |
| 后台任务编排（分割→标注→记忆→rebalance…） | `ultron/services/background.py` — `run_decay_loop`；`server.py` 在 lifespan 中启动  |
| Trajectory 指标               | `ms_agent.trajectory` — `analyze_trajectory`                                   |
| 任务分割                        | `ultron/utils/llm_orchestrator.py` — `segment_conversation_tasks`              |
| 内容指纹                        | `ultron/utils/token_budget.py` — `compute_segment_fingerprint`                 |
| `.jsonl` 摄取                 | `ultron/services/ingestion.py` — `_ingest_jsonl_trajectories`                  |
| 记忆按 tag 归档                  | `ultron/core/db_memory.py` — `archive_memories_by_tag`                         |


更完整的记忆侧说明见 [记忆中心](MemoryHub.md)。
