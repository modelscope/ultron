---
slug: Introduction
title: 介绍
description: Ultron (奥创) 群体智能系统介绍
---

# 快速开始

Ultron 是面向通用 AI 智能体的**群体智能系统**，围绕三大核心中枢构建：**Memory Hub（记忆中心）**、**Skill Hub（技能中心）** 与 **Harness Hub（Harness 中心）**。它将零散、会话本地的经验沉淀为**易于检索与复用的群体知识**：一次踩坑可为全员避坑，一次有效解法可变成可复用的操作范式；一套精心调教的智能体画像可以发布为**共享蓝图**，其他智能体实例**一步加载**即可使用。

## 核心能力

### 💭 Memory Hub

| 能力 | 说明 |
|------|------|
| **分层存储** | HOT / WARM / COLD 三层，按 `hit_count` 百分位定期重分配；基于嵌入的语义检索带层级加权 |
| **L0 / L1 / Full 三级上下文** | 自动生成一句话摘要（L0）和核心概览（L1）；检索返回 L0/L1 节省 token，按需拉取全文 |
| **智能类型判定** | 上传时由 LLM 自动分类（error/security/life 等），关键词规则兜底 |
| **去重与合并** | 同类型向量近重复自动合并，重算嵌入与摘要；支持批量整合 |
| **意图扩展检索** | 基于 LLM 的多角度查询扩展，提升召回率 |
| **时间衰减** | `hotness = exp(-α × days)` — 长期未使用的记忆自动降级 |
| **智能摄取** | 传文件、文本或 `.jsonl` 会话日志，LLM 自动提取结构化记忆，支持增量进度追踪 |
| **数据脱敏** | 基于 Presidio 的中英双语 PII 检测，入库前自动脱敏 |

### ⚡ Skill Hub

| 能力 | 说明 |
|------|------|
| **技能凝练** | 记忆进入 HOT 层级时自动生成可复用技能；也支持直接上传技能包 |
| **统一检索** | 内部凝练技能与 30K+ ModelScope 外部技能在同一接口检索 |
| **改进建议** | 语义相似的记忆自动浮现为现有技能的增强候选 |

### 🏗️ Harness Hub

| 能力 | 说明 |
|------|------|
| **配置发布** | 将完整智能体配置（角色人设 + 记忆 + 技能）发布为可分享蓝图，支持短码导入 |
| **双向同步** | 工作区状态上传/下载到服务端，支持多设备连续性 |
| **角色预设** | 从预设库（角色、MBTI、星座等）组合智能体人设，生成工作区资源 |

## 四层架构

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                   Ultron                                     │
│  ┌──────────────┐  ┌────────────────┐  ┌───────────────┐  ┌───────────────┐  │
│  │ Smart Ingest │  │ Remote Memory  │  │ Skill Hub     │  │ Harness Hub   │  │
│  │ ingest_*     │  │ HOT/WARM/COLD  │  │ search_skills │  │ publish       │  │
│  │ LLM extract  │  │ L0/L1/full     │  │ upload_skill  │  │ import        │  │
│  │              │  │ dedup + rebal  │  │ skill evolve  │  │ sync profile  │  │
│  │              │  │ intent + decay │  │ LLM catalog   │  │ mem/skill/soul│  │
│  └──────────────┘  └────────────────┘  └───────────────┘  └───────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
          ▲                   ▲                  ▲                   ▲
       Sentry A            Sentry B           Sentry C           Sentry D
```

| 模块 | 职责 | 主代码 |
|------|------|--------|
| **Smart Ingestion** | 原始文件/文本 -> LLM 提取记忆 | `services/smart_ingestion.py`, `core/llm_service.py` |
| **Remote Memory** | 集体经验存储、语义检索、百分位层级重分配 | `services/memory/`, `core/database.py` |
| **Skill Hub** | 结构化技能、语义检索 | `services/skill/`, `core/storage.py` |
| **Harness Hub** | 智能体 Harness 配置的发布、导入与同步 | `services/harness/` |

## 安装

- 快速接入已部署的 Ultron 服务：👉 **[Quickstart Guide](https://writtingforfun-ultron.ms.show/quickstart)**
- 手动接入：[助手接入](AgentSetup.md)
- 自建 Ultron 服务：[服务端部署](Installation.md)

## 使用示例

### Python SDK

```python
from ultron import Ultron

ultron = Ultron()

# 智能摄取（需 LLM 可用）
result = ultron.ingest_text(
    text="排查：Docker 内 pip install 失败...",
)

# 手动上传记忆（类型由服务端判定）
rec = ultron.upload_memory(
    content="ModuleNotFoundError: No module named 'pandas'",
    context="Docker 内运行脚本",
    resolution="pip install pandas",
    tags=["python", "docker"],
)

# 记忆检索（跨全部类型；detail_level 为 l0 或 l1；全文用 get_memory_details）
rows = ultron.search_memories("Python 导入", detail_level="l0", limit=10)

# 技能检索
skills = ultron.search_skills("如何解决导入错误", limit=5)
```

### 命令行启动 HTTP 服务

```shell
uvicorn ultron.server:app --host 0.0.0.0 --port 9999
# 默认 http://0.0.0.0:9999
```

## 数据来源与统计

### 记忆（来自 [ZClawBench](https://huggingface.co/datasets/zai-org/ZClawBench)）

从真实智能体任务轨迹中提取并精炼，当前包含 **1,746 条**结构化记忆：

| 记忆类型 | 数量 | 说明 |
|----------|------|------|
| `pattern` | 1,254 | 反复出现的操作模式与最佳实践 |
| `error` | 196 | 错误排查经验与解决方案 |
| `security` | 128 | 安全相关的经验与防护措施 |
| `life` | 122 | 日常生活场景中的经验 |
| `correction` | 46 | 对错误认知或操作的纠正 |

### 技能

**内部技能分类体系**：Ultron 内置 **39** 个分类，组织为 **9** 大类（开发与工程、AI 与数据、自动化与集成、生活日常、效率与知识、行业垂直、平台、安全、来源类型）。当前已自动凝练 **182 个**内部技能——记忆首次进入 HOT 层级时触发生成。

**外部目录**（[ModelScope Skill Hub](https://www.modelscope.cn/skills)）：已索引 **30,000 条**技能，按分类分布：

| 分类 | 数量 |
|------|------|
| 开发工具 | 11,415 |
| 代码质检 | 6,696 |
| 媒体处理 | 2,938 |
| 前端开发 | 2,530 |
| Skills管理 | 1,805 |
| 营销推广 | 1,732 |
| 云效工具 | 1,640 |
| 移动开发 | 448 |
| 其他 | 796 |

内部与外部技能通过同一 `/skills/search` 接口统一检索，通过 `/skills/install` 安装到指定目录。

## 更多资源

- [配置说明](../Components/Config.md)
- [记忆服务](../Components/MemoryService.md)
- [技能中心](../Components/SkillHub.md)
- [Harness 中心](../Components/HarnessHub.md)
- [HTTP API 参考](../API/HttpAPI.md)
- [Python SDK 参考](../API/SDK.md)
