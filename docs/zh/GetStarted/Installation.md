---
slug: Installation
title: 服务端部署
description: Ultron（奥创）服务端部署指南
---

# 服务端部署

本文档介绍如何自建 Ultron 服务。如果只需让助手连接已有的 Ultron 服务（自建或公网），请参考 [助手接入](AgentSetup.md)。

## 源码安装

```shell
git clone https://github.com/modelscope/ultron.git
cd ultron
pip install -e .
```

## 依赖说明

核心依赖（见 `requirements.txt`）：


| 依赖          | 用途                  |
| ----------- | ------------------- |
| `fastapi`   | HTTP 服务框架           |
| `uvicorn`   | ASGI 服务器            |
| `pydantic`  | 数据验证                |
| `tiktoken`  | Token 计数            |
| `dashscope` | TextEmbedding |
| `openai` | OpenAI-compatible LLM |


## 运行环境


| 环境     | 要求                      |
| ------ | ----------------------- |
| Python | >= 3.8                  |
| 系统     | Linux / macOS / Windows |


Ultron 主要使用 LLM API，因此只需 CPU 环境即可运行。

## 环境变量

智能摄取与 LLM 分类需要配置 OpenAI-compatible LLM 参数。**推荐**在 `**~/.ultron/.env`** 中设置 `ULTRON_LLM_PROVIDER`、`ULTRON_MODEL`、`ULTRON_BASE_URL`、`ULTRON_API_KEY`。向量嵌入仍使用 `DASHSCOPE_API_KEY`。

也可在 shell 中导出（适用于一次性调试）：

```shell
export ULTRON_LLM_PROVIDER="openai"
export ULTRON_MODEL="gpt-5"
export ULTRON_BASE_URL="https://api.openai.com/v1"
export ULTRON_API_KEY="your-api-key"
```

使用 `**~/.ultron/.env**` 需已安装 `python-dotenv`；可参考仓库根目录的 `.env.example`。导入 `ultron` 时仅自动加载 `**~/.ultron/.env**`（见 [配置文档](../Components/Config.md)）。在 systemd、Docker 等环境中也可注入同名环境变量。

其他可选环境变量（*完整 `ULTRON_` 列表**见 [配置文档](../Components/Config.md)，代码里 `UltronConfig(...)` 入参会覆盖环境变量）。

### 模型


| 变量                             | 说明                  | 默认值                                     |
| ------------------------------ | ------------------- | --------------------------------------- |
| `ULTRON_EMBEDDING_MODEL`       | TextEmbedding 模型名   | `text-embedding-v4`                     |
| `ULTRON_EMBEDDING_BACKEND`     | 嵌入后端（`dashscope` 或 `local`） | `dashscope`                     |
| `ULTRON_EMBEDDING_DIMENSION`   | 向量维度                | `1024`                                  |
| `ULTRON_LLM_PROVIDER`          | OpenAI-compatible 提供方标识 | `dashscope`                          |
| `ULTRON_MODEL`                 | 智能摄取与记忆提取所用 LLM     | `qwen3.6-flash`                          |
| `ULTRON_MEMORY_CATEGORY_MODEL` | 记忆类型分类所用 LLM        | `qwen3.6-flash`                         |
| `ULTRON_SKILL_CATEGORY_MODEL`  | 技能分类所用 LLM          | `qwen3.6-flash`                         |
| `ULTRON_BASE_URL`              | OpenAI-compatible API 地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `ULTRON_API_KEY`               | LLM API Key | `""` |


### LLM 请求控制


| 变量                                 | 说明                   | 默认值           |
| ---------------------------------- | -------------------- | ------------- |
| `ULTRON_LLM_MAX_INPUT_TOKENS`      | 用户文本最大 token 数       | `200000`      |
| `ULTRON_LLM_PROMPT_RESERVE_TOKENS` | 系统 prompt 预留 token 数 | `8192`        |
| `ULTRON_LLM_TOKEN_COUNT_ENCODING`  | tiktoken 编码名         | `cl100k_base` |
| `ULTRON_LLM_REQUEST_TIMEOUT`       | HTTP 读超时（秒）          | `600`         |
| `ULTRON_LLM_MAX_RETRIES`           | 失败后重试次数              | `2`           |
| `ULTRON_LLM_RETRY_BASE_DELAY`      | 重试基础等待时间（秒）          | `1.0`         |


### 记忆提取


| 变量                                          | 说明                   | 默认值     |
| ------------------------------------------- | -------------------- | ------- |
| `ULTRON_SESSION_EXTRACT_OVERLAP_LINES`      | 增量提取时向前重叠的行数         | `5`     |
| `ULTRON_CONVERSATION_EXTRACT_WINDOW_TOKENS` | 每次送 LLM 的最大 token 窗口 | `65536` |
| `ULTRON_MEMORY_MERGE_MAX_FIELD_TOKENS`      | 合并记忆时单字段最大 token 数   | `8192`  |


### 检索响应


| 变量                     | 说明                   | 默认值   |
| ---------------------- | -------------------- | ----- |
| `ULTRON_L0_MAX_TOKENS` | 搜索结果 L0 摘要最大 token 数 | `64`  |
| `ULTRON_L1_MAX_TOKENS` | 搜索结果 L1 片段最大 token 数 | `256` |


### 记忆层级、去重与衰减（节选）


| 变量                                  | 说明                                   | 默认值         |
| ----------------------------------- | ------------------------------------ | ----------- |
| `ULTRON_DATA_DIR`                   | 数据根目录（支持 `~` 展开）                     | `~/.ultron` |
| `ULTRON_DB_NAME`                    | SQLite 文件名                           | `ultron.db` |
| `ULTRON_HOT_MAX_ENTRIES`            | HOT 层最大条数                            | `500`       |
| `ULTRON_WARM_MAX_ENTRIES`           | WARM 层最大条数                           | `1000`      |
| `ULTRON_HOT_PERCENTILE`             | HOT 层占比百分位                           | `10`        |
| `ULTRON_DEDUP_SIMILARITY_THRESHOLD` | 上传近重复判定余弦下限                          | `0.85`      |
| `ULTRON_ENABLE_INTENT_ANALYSIS`     | 检索前意图分析（`0` 关闭）                      | `1`         |
| `ULTRON_MEMORY_SEARCH_LIMIT`        | 记忆检索默认返回条数（未传 `limit` 时）             | `10`        |
| `ULTRON_SKILL_SEARCH_LIMIT`         | 技能检索默认返回条数（未传 `limit` 时）             | `5`         |
| `ULTRON_DECAY_INTERVAL_HOURS`       | 后台衰减任务间隔（小时）                         | `6.0`       |
| `ULTRON_DECAY_ALPHA`                | 时间新鲜度系数                              | `0.05`      |
| `ULTRON_COLD_TTL_DAYS`              | COLD 保留天数（`0` 表示不删）                  | `30`        |


### 服务与存储


| 变量                           | 说明                                                               | 默认值    |
| ---------------------------- | ---------------------------------------------------------------- | ------ |
| `ULTRON_LOG_LEVEL`           | 日志级别                                                             | `INFO` |
| `ULTRON_RESET_TOKEN`         | `/reset` 接口鉴权 token（不设则禁用）                                       | 无      |
| `ULTRON_ARCHIVE_RAW_UPLOADS` | 是否归档：`ingest` 文件、`ingest_text` 纯文本、技能包文件（**不含** `upload_memory`） | `1`    |


更多字段（异步嵌入队列、热点摘要条数等）见 [配置文档](../Components/Config.md)。

> 注意：同一个 `ULTRON_DATA_DIR` 只能使用一种 embedding 后端与模型组合。切换 embedding 后端或模型前请先执行 `reset_all`，否则会触发启动校验失败，避免混合向量导致检索异常。

## 启动服务

### HTTP 服务

```shell
uvicorn ultron.server:app --host 0.0.0.0 --port 9999
# 默认 http://0.0.0.0:9999
```

### 作为库使用

```python
from ultron import Ultron

ultron = Ultron()
# 开始使用...
```

## 数据目录

默认 `UltronConfig.data_dir` 为 `~/.ultron/`，库会在该目录下创建并使用：


| 路径          | 用途         |
| ----------- | ---------- |
| `ultron.db` | SQLite 数据库 |
| `skills/`   | 技能内容       |
| `archive/`  | 归档技能       |
| `models/`   | 本地模型缓存     |


使用 uvicorn 启动 `ultron.server:app` 时，结构化 JSON 日志由轮转文件处理器写入 `**~/.ultron/logs/**`（`ultron.log` 及备份）。

可通过环境变量 `ULTRON_DATA_DIR`、构造 `Ultron(config=UltronConfig(data_dir=...))` 或 `Ultron(data_dir=...)` 修改数据库与技能等存储路径。

## 下一步

服务部署完成后，参考 [助手接入](AgentSetup.md) 将 AI 助手连接到 Ultron。

