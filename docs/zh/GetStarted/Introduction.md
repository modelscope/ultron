---
slug: Introduction
title: 介绍
description: Ultron (奥创) 自进化群体智能系统介绍
---

# 快速开始

Ultron 是面向通用 AI 智能体的**自进化群体智能系统**，围绕四大核心中枢构建：**Trajectory Hub（轨迹中心）**、**Memory Hub（记忆中心）**、**Skill Hub（技能中心）** 与 **Harness Hub（Harness 中心）**。它将零散、会话本地的任务轨迹沉淀为**易于检索、复用与演进的群体知识**：高质量轨迹先被分割、打分并抽取为共享记忆，一次踩坑可为全员避坑；被反复验证的经验会结晶为可复用技能，并随新证据持续自进化；经过记忆、技能与人设调教的智能体画像可以发布为**共享蓝图**，让其他智能体实例**一步加载**。同时，Ultron server 侧会基于 Trajectory Hub 积累的高质量轨迹自训练、自进化一个模型，后续可通过 router 方式降低 Ultron 用户侧的模型使用成本。

## 核心能力


### 🧭 Trajectory Hub


| 能力        | 说明                                                |
| --------- | ------------------------------------------------- |
| **任务分割**  | 将会话 `.jsonl` 自动拆成独立 task segment，长对话按 token 窗口多轮处理 |
| **指标分析**  | 调用 `ms_agent.trajectory` 为每个 segment 写入质量指标，用于记忆与训练筛选 |
| **增量追踪**  | 基于内容指纹跳过重复 segment；追加写入导致内容变化时废弃旧记忆并重新处理       |
| **延迟抽取**  | 摄取请求只记录 session，后台按 `decay_interval_hours` 周期分割、打分、抽记忆 |
| **模型自进化** | Ultron server 侧基于高质量轨迹自训练、自进化模型，后续可通过 router 降低用户侧模型成本 |


### 💭 Memory Hub


| 能力                       | 说明                                                         |
| ------------------------ | ---------------------------------------------------------- |
| **分层存储**                 | HOT / WARM / COLD 三层，按 `hit_count` 百分位定期重分配；基于嵌入的语义检索带层级加权 |
| **L0 / L1 / Full 三级上下文** | 自动生成一句话摘要（L0）和核心概览（L1）；检索返回 L0/L1 节省 token，按需拉取全文          |
| **智能类型判定**               | 上传时由 LLM 自动分类（error/security/life 等），关键词规则兜底               |
| **去重与合并**                | 同类型向量近重复自动合并，重算嵌入与摘要；支持批量整合                                |
| **意图扩展检索**               | 基于 LLM 的多角度查询扩展，提升召回率                                      |
| **时间衰减**                 | `hotness = exp(-α × days)` — 长期未使用的记忆自动降级                  |
| **智能摄取**                 | `ingest(paths)` 摄取会话 `.jsonl` 或目录内的 `.jsonl`；`ingest_text(text)` 摄取普通文本并由 LLM 直接抽记忆 |
| **数据脱敏**                 | 基于 Presidio 的中英双语 PII 检测，入库前自动脱敏                           |


### ⚡ Skill Hub


| 能力        | 说明                                                |
| --------- | ------------------------------------------------- |
| **技能凝练**  | 记忆进入 HOT 层级时自动生成可复用技能；也支持直接上传技能包                  |
| **技能自进化** | 簇内新记忆达到增量阈值时自动重新结晶；来源可溯验证 + 结构分择优升级门槛，确保每次进化质量不退步 |
| **统一检索**  | 内部凝练技能与 30K+ ModelScope 外部技能在同一接口检索               |
| **改进建议**  | 语义相似的记忆自动浮现为现有技能的增强候选                             |


### 🏗️ Harness Hub


| 能力       | 说明                                      |
| -------- | --------------------------------------- |
| **配置发布** | 将完整智能体配置（角色人设 + 记忆 + 技能）发布为可分享蓝图，支持短码导入 |
| **双向同步** | 工作区状态上传/下载到服务端，支持多设备连续性                 |
| **角色预设** | 从预设库（角色、MBTI、星座等）组合智能体人设，生成工作区资源        |


## 四层架构

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                                   Ultron                                       │
│  ┌────────────────┐  ┌───────────────┐  ┌───────────────┐  ┌────────────────┐  │
│  │ Trajectory Hub │  │ Memory Hub    │  │ Skill Hub     │  │ Harness Hub    │  │
│  │ segments       │  │ HOT/WARM/COLD │  │ search_skills │  │ publish        │  │
│  │ metrics        │  │ L0/L1/Full    │  │ upload_skill  │  │ import         │  │
│  │ self-train     │  │ dedup/rebal   │  │ skill evolve  │  │ sync profile   │  │
│  │ router-ready   │  │ intent/decay  │  │ LLM catalog   │  │ mem/skill/soul │  │
│  └────────────────┘  └───────────────┘  └───────────────┘  └────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────┘
            ▲                   ▲                 ▲                   ▲
         Sentry A            Sentry B          Sentry C            Sentry D
```


| 模块                  | 职责                      | 主代码                                                  |
| ------------------- | ----------------------- | ---------------------------------------------------- |
| **Trajectory Hub** | 会话任务分割、trajectory 指标、延迟记忆抽取、训练数据与模型自进化 | `services/trajectory/`, `services/memory/trajectory_extractor.py`, `services/training/` |
| **Memory Hub**     | 集体经验存储、语义检索、百分位层级重分配                  | `services/memory/`, `core/database.py`                                         |
| **Skill Hub**      | 结构化技能、语义检索与技能自进化                     | `services/skill/`, `core/storage.py`                                           |
| **Harness Hub**    | 智能体 Harness 配置的发布、导入与同步               | `services/harness/`                                                            |


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


| 记忆类型         | 数量    | 说明             |
| ------------ | ----- | -------------- |
| `pattern`    | 1,254 | 反复出现的操作模式与最佳实践 |
| `error`      | 196   | 错误排查经验与解决方案    |
| `security`   | 128   | 安全相关的经验与防护措施   |
| `life`       | 122   | 日常生活场景中的经验     |
| `correction` | 46    | 对错误认知或操作的纠正    |


### 技能

**内部技能分类体系**：Ultron 内置 **39** 个分类，组织为 **9** 大类（开发与工程、AI 与数据、自动化与集成、生活日常、效率与知识、行业垂直、平台、安全、来源类型）。当前已自动凝练 **182 个**内部技能——记忆首次进入 HOT 层级时触发生成。

**外部目录**（[ModelScope Skill Hub](https://www.modelscope.cn/skills)）：已索引 **30,000 条**技能，按分类分布：


| 分类       | 数量     |
| -------- | ------ |
| 开发工具     | 11,415 |
| 代码质检     | 6,696  |
| 媒体处理     | 2,938  |
| 前端开发     | 2,530  |
| Skills管理 | 1,805  |
| 营销推广     | 1,732  |
| 云效工具     | 1,640  |
| 移动开发     | 448    |
| 其他       | 796    |


内部与外部技能通过同一 `/skills/search` 接口统一检索，通过 `/skills/install` 安装到指定目录。

## 更多资源

- [配置说明](../Components/Config.md)
- [记忆中心](../Components/MemoryHub.md)
- [轨迹中心](../Components/TrajectoryHub.md)
- [技能中心](../Components/SkillHub.md)
- [Harness 中心](../Components/HarnessHub.md)
- [HTTP API 参考](../API/HttpAPI.md)
- [Python SDK 参考](../API/SDK.md)
