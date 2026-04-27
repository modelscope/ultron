---
slug: Config
title: 配置
description: Ultron（奥创）配置说明
---

# 配置

Ultron 使用 `UltronConfig` 数据类进行配置管理。**环境变量 `ULTRON_*`** 决定各字段的默认值；在代码里构造 `UltronConfig(...)` 时传入的参数 **优先于** 环境变量。LLM 采用 OpenAI-compatible 抽象（`llm_provider`、`llm_model`、`llm_base_url`、`llm_api_key`）。向量嵌入由 `embedding_backend` 选择（`dashscope` 或 `local`）；`dashscope_api_key` 可与 LLM 共用 `DASHSCOPE_API_KEY`，并在 `Ultron(...)` 初始化时写入 `os.environ`（若已设置）。`llm_api_key` 的解析顺序为：`ULTRON_API_KEY` → `ULTRON_LLM_API_KEY` → `OPENAI_API_KEY` → `DASHSCOPE_API_KEY`。

首次导入 `ultron.config`（或 `import ultron`）时，会调用 `load_ultron_dotenv()`：从 `~/.ultron/.env` 读取键值并写入 `os.environ`（`override=False`）。

- 仓库内提供 `**/.env.example`**，可将各 `ULTRON_*` 写入 `**~/.ultron/.env**`（若目录不存在需先创建）。
- 未安装 `**python-dotenv**` 时 `load_ultron_dotenv()` 为空操作，仍可通过导出环境变量或进程管理器注入配置。

## 代码配置

```python
from ultron import Ultron, UltronConfig

config = UltronConfig(
    data_dir="~/.ultron",
    embedding_model="text-embedding-v4",
    llm_model="qwen3.6-flash",
    dedup_similarity_threshold=0.85,
)

ultron = Ultron(config=config)
```

## 配置项说明

### 数据存储


| 配置项        | 类型  | 默认值         | 说明            |
| ---------- | --- | ----------- | ------------- |
| `data_dir` | str | `~/.ultron` | 数据存储根目录       |
| `db_name`  | str | `ultron.db` | SQLite 数据库文件名 |


### DashScope 凭证


| 配置项                 | 类型  | 默认值  | 说明                                                                                                                    |
| ------------------- | --- | ---- | --------------------------------------------------------------------------------------------------------------------- |
| `dashscope_api_key` | str | `""` | LLM 与向量嵌入共用密钥；对应环境变量 `DASHSCOPE_API_KEY`，推荐与 `ULTRON_*` 一同放在 `~/.ultron/.env`。`Ultron(...)` 初始化时会将非空值同步到 `os.environ` |


### 嵌入模型


| 配置项                   | 类型  | 默认值                 | 说明                          |
| --------------------- | --- | ------------------- | --------------------------- |
| `embedding_model`     | str | `text-embedding-v4` | DashScope TextEmbedding 模型名 |
| `embedding_dimension` | int | `1024`              | 向量维度（首次调用后以 API 返回为准）       |
| `embedding_backend`   | str | `dashscope`         | 嵌入后端，支持 `dashscope` 或 `local`；同一服务数据目录仅允许一种后端与模型组合 |


### LLM 配置


| 配置项                            | 类型    | 默认值                                     | 说明                                      |
| ------------------------------ | ----- | --------------------------------------- | --------------------------------------- |
| `llm_provider`                 | str   | `dashscope`                             | OpenAI-compatible 后端标识（`dashscope`、`openai` 等） |
| `llm_model`                    | str   | `qwen3.6-flash`                         | 主链路 LLM（智能摄取、摘要与合并等），优先读取 `ULTRON_MODEL` |
| `memory_category_llm_model`    | str   | `qwen3.6-flash`                         | 记忆 **类型** 分类（error/security/…）所用 LLM    |
| `skill_category_llm_model`     | str   | `qwen3.6-flash`                         | 技能目录分类所用 LLM                            |
| `llm_base_url`                 | str   | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI-compatible API 根 URL，优先读取 `ULTRON_BASE_URL` |
| `llm_api_key`                  | str   | `""`                                    | LLM API Key；按顺序读取 `ULTRON_API_KEY`、`ULTRON_LLM_API_KEY`、`OPENAI_API_KEY`、`DASHSCOPE_API_KEY` |
| `llm_max_input_tokens`         | int   | `200000`                                | 用户侧正文 token 预算上限                        |
| `llm_prompt_reserve_tokens`    | int   | `8192`                                  | 系统提示等预留 token，**不计入**上述用户正文预算           |
| `llm_token_count_encoding`     | str   | `cl100k_base`                           | tiktoken 编码名（截断与计数）                     |
| `llm_request_timeout_seconds`  | int   | `600`                                   | DashScope HTTP 读超时（秒）；配置项实际值 **不低于 60** |
| `llm_max_retries`              | int   | `2`                                     | 首次请求失败后的重试次数（总尝试次数 = 该值 + 1）            |
| `llm_retry_base_delay_seconds` | float | `1.0`                                   | 重试退避的时间基数（秒）                            |

### Trajectory 指标

Ultron 会把自己单独配置的 trajectory 指标模型注入到 `ms_agent.trajectory`。这里使用 `quality_llm_*` 配置槽位，输出为指标 JSON 和加权分数。

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `quality_llm_provider` | str | `dashscope` | 指标模型提供商；环境变量 `ULTRON_QUALITY_LLM_PROVIDER` |
| `quality_llm_model` | str | `qwen3.6-plus` | 指标模型名；环境变量 `ULTRON_QUALITY_LLM_MODEL` |
| `quality_llm_base_url` | str | 与主 LLM 默认一致 | 指标模型 OpenAI-compatible 根 URL；环境变量 `ULTRON_QUALITY_LLM_BASE_URL` |
| `quality_llm_api_key` | str | `""`（回退主 LLM） | 指标模型 API 密钥；环境变量 `ULTRON_QUALITY_LLM_API_KEY` |
| `trajectory_memory_score_threshold` | float | `0.7` | 与 `quality_metrics` 中 `summary.overall_score`（0–1）同刻度，进入记忆粗筛的最低分；环境变量 `ULTRON_TRAJECTORY_MEMORY_SCORE_THRESHOLD` |
| `trajectory_sft_score_threshold` | float | `0.8` | 与 `summary.overall_score` 同刻度，进入 SFT 导出/自训练的最低分；环境变量 `ULTRON_TRAJECTORY_SFT_SCORE_THRESHOLD` |


### 轨迹会话 → 记忆抽取

用于 **`TrajectoryService.extract_memories_from_segments`** 门面；实现位于 **`TrajectoryMemoryExtractor`**。从磁盘上的会话 **`.jsonl`** 读取满足 `trajectory_memory_score_threshold` 与 `is_memory_eligible` 的 segment 消息，按 token 窗口抽取后写入 Memory Hub。详见 [轨迹中心](TrajectoryHub.md)。

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `conversation_extract_window_tokens` | int | `65536`（实际不低于 `256`） | 将拼接后的对话按 token 切窗后逐窗调用主 LLM 的 `extract_memories_from_text`；环境变量 `ULTRON_CONVERSATION_EXTRACT_WINDOW_TOKENS` |
| `session_extract_overlap_lines` | int | `5` | 在「新行尾」之前，从 `.jsonl` **再向前取 K 行**作为上下文；`ULTRON_SESSION_EXTRACT_OVERLAP_LINES`，最小为 `0` |


### 记忆层级


| 配置项               | 类型  | 默认值  | 说明                                              |
| ----------------- | --- | ---- | ----------------------------------------------- |
| `hot_percentile`  | int | `10` | HOT 层占比百分位（top N%），由 `run_tier_rebalance` 定期重分配 |
| `warm_percentile` | int | `40` | WARM 层占比百分位（next M%）                            |
| `cold_ttl_days`   | int | `30` | COLD 记忆超过 N 天后归档为 archived（0=不归档）               |


### 检索与意图


| 配置项                             | 类型   | 默认值    | 说明                                                                                                 |
| ------------------------------- | ---- | ------ | -------------------------------------------------------------------------------------------------- |
| `enable_intent_analysis`        | bool | `True` | 记忆语义检索前是否做查询意图分析                                                                                   |
| `memory_search_default_limit`   | int  | `10`   | 记忆语义检索在**未传入** `limit` 时返回的最大条数（`MemoryService.search_memories`、HTTP `POST /memory/search` 等）      |
| `skill_search_default_limit`    | int  | `5`    | 技能语义检索在**未传入** `limit` 时返回的最大条数（`search_skills`、HTTP `POST /skills/search` 等）                      |


### 去重与合并


| 配置项                             | 类型    | 默认值    | 说明                      |
| ------------------------------- | ----- | ------ | ----------------------- |
| `dedup_similarity_threshold`    | float | `0.85` | 近似重复检测的余弦阈值（硬去重）       |
| `dedup_soft_threshold`          | float | `0.75` | 软阈值，命中后由 LLM 二次确认是否为重复  |
| `memory_merge_max_field_tokens` | int   | `8192` | 合并后各字段最大 token 数（0=不截断） |


### L0/L1/Full 分层


| 配置项             | 类型  | 默认值   | 说明              |
| --------------- | --- | ----- | --------------- |
| `l0_max_tokens` | int | `64`  | L0 摘要最大 token 数 |
| `l1_max_tokens` | int | `256` | L1 概览最大 token 数 |


### 时间衰减


| 配置项                    | 类型    | 默认值    | 说明                                                    |
| ---------------------- | ----- | ------ | ----------------------------------------------------- |
| `decay_interval_hours` | float | `6.0`  | 服务端后台记忆衰减任务的执行间隔（小时）                                  |
| `decay_alpha`          | float | `0.05` | 时间新鲜度系数：`hotness = exp(-alpha * days_since_last_hit)` |
| `time_decay_weight`    | float | `0.1`  | 检索排序中与 `hotness` 结合的权重                                |


### 异步嵌入


| 配置项                       | 类型   | 默认值     | 说明          |
| ------------------------- | ---- | ------- | ----------- |
| `async_embedding`         | bool | `False` | 是否启用异步嵌入队列  |
| `embedding_queue_size`    | int  | `100`   | 队列最大容量      |
| `embedding_queue_workers` | int  | `2`     | 后台 worker 数 |


### 原始上传归档（固定行为，无开关）

使用持久化数据库时，原始内容会写入 `raw_user_uploads`（无可关闭选项）：`ingest(paths)` 每个摄取到的 `.jsonl` 一条 `ingest_file`；独立 **`ingest_text`** 一条 `ingest_text`；**`upload_skill`** 包内每个文件一条 `skill_upload_file`。**`upload_memory` 不归档**。单条 payload ≤10MB；不保存 HTTP JSON 整包。

### 合并整理（Consolidation）


| 配置项                      | 类型   | 默认值     | 说明                        |
| ------------------------ | ---- | ------- | ------------------------- |
| `consolidate_enabled`    | bool | `False` | 是否在层级重分配时自动执行合并整理         |
| `consolidate_max_merges` | int  | `50`    | 每次合并整理的最大合并操作数            |

### 技能进化（Skill Evolution）


| 配置项                            | 类型    | 默认值    | 说明                                |
| ------------------------------ | ----- | ------ | --------------------------------- |
| `evolution_enabled`            | bool  | `True` | 是否启用技能进化流水线（聚类 → 结晶 → 重结晶）       |
| `cluster_similarity_threshold` | float | `0.75` | 记忆分配到簇的余弦相似度阈值                    |
| `crystallization_threshold`    | int   | `5`    | 簇内记忆数达到此值后触发结晶                    |
| `recrystallization_delta`      | int   | `3`    | 已结晶簇新增记忆达到此值后触发重结晶                |
| `evolution_batch_limit`        | int   | `10`   | 每批次最多进化的簇数量                       |

### 认证（Authentication）


| 配置项                | 类型  | 默认值       | 说明                                                        |
| ------------------ | --- | --------- | --------------------------------------------------------- |
| `jwt_secret`       | str | 自动生成      | JWT 签名密钥；可在构造参数中显式传入；否则优先读 `ULTRON_JWT_SECRET`，再读 `data_dir/.jwt_secret`，否则生成并写入该文件（详见 `resolve_jwt_secret()`） |
| `jwt_expire_hours` | int | `24`      | JWT token 过期时间（小时）                                        |


## 环境变量

HTTP 日志见 [安装指南](../GetStarted/Installation.md)（`ULTRON_LOG_LEVEL`、`ULTRON_RESET_TOKEN` 等不进入 `UltronConfig`）。

| 环境变量                                        | 对应配置项                                |
| ------------------------------------------- | ------------------------------------ |
| `DASHSCOPE_API_KEY`                         | `dashscope_api_key`                  |
| `ULTRON_DATA_DIR`                           | `data_dir`                           |
| `ULTRON_DB_NAME`                            | `db_name`                            |
| `ULTRON_EMBEDDING_BACKEND`                  | `embedding_backend`                  |
| `ULTRON_EMBEDDING_MODEL`                    | `embedding_model`                    |
| `ULTRON_EMBEDDING_DIMENSION`                | `embedding_dimension`                |
| `ULTRON_CONVERSATION_EXTRACT_WINDOW_TOKENS` | `conversation_extract_window_tokens` |
| `ULTRON_TRAJECTORY_MEMORY_SCORE_THRESHOLD`  | `trajectory_memory_score_threshold`  |
| `ULTRON_TRAJECTORY_SFT_SCORE_THRESHOLD`     | `trajectory_sft_score_threshold`     |
| `ULTRON_SESSION_EXTRACT_OVERLAP_LINES`      | `session_extract_overlap_lines`      |
| `ULTRON_QUALITY_LLM_PROVIDER`               | `quality_llm_provider`               |
| `ULTRON_QUALITY_LLM_MODEL`                  | `quality_llm_model`                  |
| `ULTRON_QUALITY_LLM_BASE_URL`               | `quality_llm_base_url`               |
| `ULTRON_QUALITY_LLM_API_KEY`                | `quality_llm_api_key`                |
| `ULTRON_HOT_PERCENTILE`                     | `hot_percentile`                     |
| `ULTRON_WARM_PERCENTILE`                    | `warm_percentile`                    |
| `ULTRON_COLD_TTL_DAYS`                      | `cold_ttl_days`                      |
| `ULTRON_DEDUP_SIMILARITY_THRESHOLD`         | `dedup_similarity_threshold`         |
| `ULTRON_MEMORY_MERGE_MAX_FIELD_TOKENS`      | `memory_merge_max_field_tokens`      |
| `ULTRON_L0_MAX_TOKENS`                      | `l0_max_tokens`                      |
| `ULTRON_L1_MAX_TOKENS`                      | `l1_max_tokens`                      |
| `ULTRON_ENABLE_INTENT_ANALYSIS`             | `enable_intent_analysis`             |
| `ULTRON_MEMORY_SEARCH_LIMIT`                | `memory_search_default_limit`        |
| `ULTRON_SKILL_SEARCH_LIMIT`                 | `skill_search_default_limit`         |
| `ULTRON_ASYNC_EMBEDDING`                    | `async_embedding`                    |
| `ULTRON_EMBEDDING_QUEUE_SIZE`               | `embedding_queue_size`               |
| `ULTRON_EMBEDDING_QUEUE_WORKERS`            | `embedding_queue_workers`            |
| `ULTRON_DECAY_INTERVAL_HOURS`               | `decay_interval_hours`               |
| `ULTRON_DECAY_ALPHA`                        | `decay_alpha`                        |
| `ULTRON_TIME_DECAY_WEIGHT`                  | `time_decay_weight`                  |
| `ULTRON_LLM_PROVIDER`                       | `llm_provider`                       |
| `ULTRON_MODEL`                              | `llm_model`                          |
| `ULTRON_LLM_MODEL`                          | `llm_model`（兼容回退）                  |
| `ULTRON_MEMORY_CATEGORY_MODEL`              | `memory_category_llm_model`          |
| `ULTRON_SKILL_CATEGORY_MODEL`               | `skill_category_llm_model`           |
| `ULTRON_BASE_URL`                           | `llm_base_url`                       |
| `ULTRON_LLM_BASE_URL`                       | `llm_base_url`（兼容回退）                |
| `ULTRON_LLM_API_URL`                        | `llm_base_url`（兼容回退）                |
| `ULTRON_API_KEY`                            | `llm_api_key`                        |
| `ULTRON_LLM_API_KEY`                        | `llm_api_key`（兼容回退）                 |
| `ULTRON_LLM_MAX_INPUT_TOKENS`               | `llm_max_input_tokens`               |
| `ULTRON_LLM_PROMPT_RESERVE_TOKENS`          | `llm_prompt_reserve_tokens`          |
| `ULTRON_LLM_TOKEN_COUNT_ENCODING`           | `llm_token_count_encoding`           |
| `ULTRON_LLM_REQUEST_TIMEOUT`                | `llm_request_timeout_seconds`        |
| `ULTRON_LLM_MAX_RETRIES`                    | `llm_max_retries`                    |
| `ULTRON_LLM_RETRY_BASE_DELAY`               | `llm_retry_base_delay_seconds`       |
| `ULTRON_DEDUP_SOFT_THRESHOLD`               | `dedup_soft_threshold`               |
| `ULTRON_CONSOLIDATE_ENABLED`                | `consolidate_enabled`                |
| `ULTRON_CONSOLIDATE_MAX_MERGES`             | `consolidate_max_merges`             |
| `ULTRON_EVOLUTION_ENABLED`                  | `evolution_enabled`                  |
| `ULTRON_CLUSTER_SIMILARITY_THRESHOLD`       | `cluster_similarity_threshold`       |
| `ULTRON_CRYSTALLIZATION_THRESHOLD`          | `crystallization_threshold`          |
| `ULTRON_RECRYSTALLIZATION_DELTA`            | `recrystallization_delta`            |
| `ULTRON_EVOLUTION_BATCH_LIMIT`              | `evolution_batch_limit`              |
| `ULTRON_JWT_SECRET`                         | `jwt_secret`                         |
| `ULTRON_JWT_EXPIRE_HOURS`                   | `jwt_expire_hours`                   |


## 目录属性

`UltronConfig` 提供便捷的目录路径属性：

```python
config = UltronConfig()

config.db_path           # ~/.ultron/ultron.db
config.skills_dir        # ~/.ultron/skills
config.archive_dir       # ~/.ultron/archive
config.models_dir        # ~/.ultron/models
```
