---

## slug: Config

title: 配置
description: Ultron (奥创) 配置说明

# 配置

Ultron 使用 `UltronConfig` 数据类进行配置管理。**环境变量 `ULTRON_*`** 决定各字段的默认值；在代码里构造 `UltronConfig(...)` 时传入的参数 **优先于** 环境变量。LLM 采用 OpenAI-compatible 抽象（`llm_provider`、`llm_model`、`llm_base_url`、`llm_api_key`），向量嵌入仍使用 DashScope（`dashscope_api_key`）。

首次导入 `ultron.config`（或 `import ultron`）时，会调用 `load_ultron_dotenv()`：从 `~/.ultron/.env` 读取键值并写入 `os.environ`（`override=False`）。

- 仓库内提供 `**/.env.example`**，可将各 `ULTRON_*` 写入 `**~/.ultron/.env**`（若目录不存在需先创建）。
- 未安装 `**python-dotenv**` 时 `load_ultron_dotenv()` 为空操作，仍可通过导出环境变量或进程管理器注入配置。

## 代码配置

```python
from ultron import Ultron, UltronConfig

config = UltronConfig(
    data_dir="~/.ultron",
    embedding_model="text-embedding-v4",
    llm_model="qwen3.5-flash",
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
| `llm_model`                    | str   | `qwen3.5-flash`                         | 主链路 LLM（智能摄取、摘要与合并等），优先读取 `ULTRON_MODEL` |
| `memory_category_llm_model`    | str   | `qwen3.5-flash`                         | 记忆 **类型** 分类（error/security/…）所用 LLM    |
| `skill_category_llm_model`     | str   | `qwen3.5-flash`                         | 技能目录分类所用 LLM                            |
| `llm_base_url`                 | str   | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI-compatible API 根 URL，优先读取 `ULTRON_BASE_URL` |
| `llm_api_key`                  | str   | `""`                                    | LLM API Key，优先读取 `ULTRON_API_KEY` |
| `llm_max_input_tokens`         | int   | `200000`                                | 用户侧正文 token 预算上限                        |
| `llm_prompt_reserve_tokens`    | int   | `8192`                                  | 系统提示等预留 token，**不计入**上述用户正文预算           |
| `llm_token_count_encoding`     | str   | `cl100k_base`                           | tiktoken 编码名（截断与计数）                     |
| `llm_request_timeout_seconds`  | int   | `600`                                   | DashScope HTTP 读超时（秒）；配置项实际值 **不低于 60** |
| `llm_max_retries`              | int   | `2`                                     | 首次请求失败后的重试次数（总尝试次数 = 该值 + 1）            |
| `llm_retry_base_delay_seconds` | float | `1.0`                                   | 重试退避的时间基数（秒）                            |


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
| `skill_auto_detect_batch_limit` | int  | `5`    | 自动批量技能检测（`auto_detect_and_generate` / `auto_generate_skills`）在**未传入** `limit` 时处理的 HOT 候选上限（按打分截取） |


### 去重与合并


| 配置项                             | 类型    | 默认值    | 说明                      |
| ------------------------------- | ----- | ------ | ----------------------- |
| `dedup_similarity_threshold`    | float | `0.85` | 近似重复检测的余弦阈值             |
| `memory_merge_max_field_tokens` | int   | `8192` | 合并后各字段最大 token 数（0=不截断） |


### L0/L1/Full 分层


| 配置项             | 类型  | 默认值   | 说明              |
| --------------- | --- | ----- | --------------- |
| `l0_max_tokens` | int | `64`  | L0 摘要最大 token 数 |
| `l1_max_tokens` | int | `256` | L1 概览最大 token 数 |


### 会话记忆提取


| 配置项                                  | 类型  | 默认值     | 说明                               |
| ------------------------------------ | --- | ------- | -------------------------------- |
| `session_extract_overlap_lines`      | int | `5`     | 增量提取时前置上文行数                      |
| `conversation_extract_window_tokens` | int | `65536` | 滑窗每段对话 token 上限（解析后 **不低于 256**） |


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


### 归档（摄取与技能包）


| 配置项                   | 类型   | 默认值    | 说明                                                                                                                                                                                                                                                                  |
| --------------------- | ---- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `archive_raw_uploads` | bool | `True` | 为真时：`ingest(paths)` 将**路径下每个待处理文件**的原始字节写入 `raw_user_uploads`（`source=ingest_file`）；**独立调用的** `ingest_text`（无来源文件路径）将整段 UTF-8 文本写入（`source=ingest_text`）；`upload_skill` 递归写入技能目录内文件（`skill_upload_file`）。`**upload_memory` 不归档**。单条 payload ≤10MB。不保存 HTTP JSON 整包。 |


## 环境变量

HTTP 日志与 `/reset` 鉴权见 [安装指南](../GetStarted/Installation.md)（`ULTRON_LOG_LEVEL`、`ULTRON_RESET_TOKEN` 不进入 `UltronConfig`）。


| 环境变量                                        | 对应配置项                                |
| ------------------------------------------- | ------------------------------------ |
| `DASHSCOPE_API_KEY`                         | `dashscope_api_key`                  |
| `ULTRON_DATA_DIR`                           | `data_dir`                           |
| `ULTRON_DB_NAME`                            | `db_name`                            |
| `ULTRON_EMBEDDING_MODEL`                    | `embedding_model`                    |
| `ULTRON_EMBEDDING_DIMENSION`                | `embedding_dimension`                |
| `ULTRON_HOT_PERCENTILE`                     | `hot_percentile`                     |
| `ULTRON_WARM_PERCENTILE`                    | `warm_percentile`                    |
| `ULTRON_COLD_TTL_DAYS`                      | `cold_ttl_days`                      |
| `ULTRON_DEDUP_SIMILARITY_THRESHOLD`         | `dedup_similarity_threshold`         |
| `ULTRON_SESSION_EXTRACT_OVERLAP_LINES`      | `session_extract_overlap_lines`      |
| `ULTRON_CONVERSATION_EXTRACT_WINDOW_TOKENS` | `conversation_extract_window_tokens` |
| `ULTRON_MEMORY_MERGE_MAX_FIELD_TOKENS`      | `memory_merge_max_field_tokens`      |
| `ULTRON_L0_MAX_TOKENS`                      | `l0_max_tokens`                      |
| `ULTRON_L1_MAX_TOKENS`                      | `l1_max_tokens`                      |
| `ULTRON_ENABLE_INTENT_ANALYSIS`             | `enable_intent_analysis`             |
| `ULTRON_MEMORY_SEARCH_LIMIT`                | `memory_search_default_limit`        |
| `ULTRON_SKILL_SEARCH_LIMIT`                 | `skill_search_default_limit`         |
| `ULTRON_SKILL_AUTO_DETECT_LIMIT`            | `skill_auto_detect_batch_limit`      |
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
| `ULTRON_ARCHIVE_RAW_UPLOADS`                | `archive_raw_uploads`                |


## 目录属性

`UltronConfig` 提供便捷的目录路径属性：

```python
config = UltronConfig()

config.db_path           # ~/.ultron/ultron.db
config.skills_dir        # ~/.ultron/skills
config.archive_dir       # ~/.ultron/archive
config.models_dir        # ~/.ultron/models
```

