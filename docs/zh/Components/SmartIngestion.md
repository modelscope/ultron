---
slug: SmartIngestion
title: 智能摄取
description: Ultron (奥创) 智能摄取服务
---

# 智能摄取

智能摄取（Smart Ingestion）是 Ultron 的统一知识提取服务。只需传入文件/目录路径或原始文本，Ultron 会按文件类型自动分发：`.jsonl` 会话文件走 ConversationExtractor（增量提取），其他文件走 LLM 文本提取。

## 核心能力

| 能力 | 说明 |
|------|------|
| **统一摄取** | 单一 `ingest(paths)` 入口，按扩展名自动分发 |
| **文本摄取** | 直接处理原始文本 |
| **会话提取** | `.jsonl` 文件自动走增量提取 |
| **目录展开** | 传目录路径递归展开其下所有常规文件（跳过隐藏路径段、符号链接） |
| **类型判定** | 自动判断记忆类型 |
| **去重处理** | 自动与已有记忆合并 |
| **原文归档** | 开启 `archive_raw_uploads` 时：`ingest(paths)` 每文件一条 `ingest_file`；纯 `ingest_text`（非由文件读入）一条 `ingest_text`；由文件读入再提取时只归档文件字节，不重复存解码正文 |

## 使用示例

### 统一摄取

```python
from ultron import Ultron

ultron = Ultron()

# 摄取文件（支持混合类型：普通文件 + .jsonl + 目录）
result = ultron.ingest(
    paths=["/path/to/debug_log.txt", "/path/to/sessions/"],
)

print(f"处理文件数: {result['total_files']}")
print(f"总记忆数: {result['total_memories']}")
```

### 文本摄取

```python
# 摄取原始文本
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

## 工作流程

### 统一分发

```
输入路径列表
    ↓
递归展开目录内文件
    ↓
对每个文件：归档原始字节到 raw_user_uploads
 （跳过超过 10MB 的文件；归档失败不阻塞摄取）
    ↓
按扩展名分发
 ├─ .jsonl → ConversationExtractor（增量）
 └─ 其他   → LLM 文本提取
    ↓
上传到记忆服务
 (去重、晋升)
    ↓
汇总结果
```

### 会话提取（.jsonl）

```
session .jsonl 文件
    ↓
读取新增行（增量）
    ↓
滑窗分段
 (conversation_extract_window_tokens)
    ↓
LLM 提取可复用经验
    ↓
上传到记忆服务
```

## 增量处理

会话提取支持增量处理，避免重复处理已摄取的内容：

1. 服务端按文件路径追踪已处理行数
2. 每次只处理新增行
3. 可配置 `session_extract_overlap_lines` 在新增行前加入上文衔接

```python
# 第一次调用：处理全部内容
result1 = ultron.ingest(
    paths=["/path/to/session.jsonl"],
)
# processed_lines: 0 -> 100

# 文件新增内容后再次调用：只处理新增部分
result2 = ultron.ingest(
    paths=["/path/to/session.jsonl"],
)
# processed_lines: 100 -> 150
```

## LLM 提取逻辑

智能摄取使用 LLM（默认 `qwen3.5-flash`）进行内容理解：

### 记忆提取 Prompt

LLM 会被指示提取以下类型的可复用经验：

- **错误与解决方案**：遇到的错误及其解决方法
- **安全相关**：安全问题与防护措施
- **模式与规律**：观察到的通用模式
- **生活经验**：可共享的客观经验（非个人隐私）

### 输出格式

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

## Token 管理

摄取时会进行 token 预算管理：

| 配置项 | 作用 |
|--------|------|
| `llm_max_input_tokens` | 输入内容的最大 token 数 |
| `llm_prompt_reserve_tokens` | 预留给回复的 token |
| `conversation_extract_window_tokens` | 会话分段的窗口大小 |

超长内容会被自动截断或分段处理。

## HTTP API

### 统一摄取

```
POST /ingest
{
    "paths": ["/path/to/file.txt", "/path/to/sessions/"]
}
```

### 文本摄取

```
POST /ingest/text
{
    "text": "原始文本内容..."
}
```

## 依赖

智能摄取需要：

1. **DashScope API Key**：环境变量 `DASHSCOPE_API_KEY`
2. **LLM 可用**：默认使用 `qwen3.5-flash`

如果 LLM 不可用，会回退到规则推断记忆类型。

## 最佳实践

1. **混合路径批量处理**：使用 `ingest(paths=[...])` 一次传入文件和目录
2. **定期提取会话**：Heartbeat 中传 sessions 目录给 `ingest`，`.jsonl` 自动增量处理
3. **调整置信度阈值**：根据质量需求调整 `min_confidence`
