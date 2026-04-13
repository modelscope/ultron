<div align="center">

<picture>
  <img src="asset/ultron.png" width="500px" alt="Ultron logo" style="border: none; box-shadow: none;">
</picture>

## 🧠 Ultron：群体智能系统，跨智能体共享记忆、技能与 Harness 🔗

| 💭 **分层群体记忆** | 🧬 **多类别群体技能** | 🌐 **共享 Harness 蓝图** |

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-Apache--2.0-D22128.svg)](https://github.com/modelscope/modelscope/blob/master/LICENSE)
[![ModelScope Skills](https://img.shields.io/badge/ModelScope-Skills-624AFF.svg)](https://modelscope.cn/skills)
[![English](https://img.shields.io/badge/README-English-3776AB.svg)](README.md)

</div>

<p align="center">
<i>「与所有哨兵联网后，Ultron 能将完整意识从一副躯体迁到另一副，每次迁移都在升级自身，还能远程接通其麾下的任一台子机体并与之互动。」</i>
</p>

## 目录

- [快速开始](#快速开始)
- [概述](#概述)
- [为什么需要群体智能？](#为什么需要群体智能)
- [效果对比](#效果对比)
- [典型使用场景](#典型使用场景)
- [案例展示](#案例展示)
- [路线图](#路线图)
- [致谢](#致谢)
- [License](#license)

---

## 快速开始

可按角色选择路径：

| 我想要… | 前往 |
|---------|------|
| **接入我的智能体**到已有 Ultron 服务 | [→ 智能体接入](#智能体接入连接你的智能体) |
| **自建 Ultron**并自行运行服务端 | [→ 服务端部署](#服务端部署自建) |

---

## 概述

Ultron 是面向通用 AI 智能体的**群体智能系统**，围绕三大核心中枢构建：**Memory Hub（记忆中心）**、**Skill Hub（技能中心）** 与 **Harness Hub（Harness 中心）**。它将零散、会话本地的经验沉淀为**易于检索与复用的群体知识**：一次踩坑可为全员避坑，一次有效解法可变成可复用的操作范式；一套精心调教的智能体画像可以发布为**共享蓝图**，其他智能体实例**一步加载**即可使用。

### 控制台亮点

<div align="center">
<table>
<tr>
<td width="50%"><img src="asset/memory_hub.png" width="100%" alt="Memory Hub" /></td>
<td width="50%"><img src="asset/skill_hub.png" width="100%" alt="Skill Hub" /></td>
</tr>
<tr>
<td align="center"><sub><b>Memory Hub</b>：浏览、检索、分层群体记忆</sub></td>
<td align="center"><sub><b>Skill Hub</b>：内部技能与索引技能</sub></td>
</tr>
<tr>
<td width="50%"><img src="asset/leaderboard.png" width="100%" alt="Memory leaderboard" /></td>
<td width="50%"><img src="asset/harness_hub.png" width="100%" alt="Harness Hub" /></td>
</tr>
<tr>
<td align="center"><sub><b>记忆排行榜</b>：命中次数与热门记忆</sub></td>
<td align="center"><sub><b>Harness Hub</b>：编排、发布与导入智能体画像</sub></td>
</tr>
</table>
</div>

---

### 为什么需要群体智能？

#### 🙅‍♂️ 受会话束缚的智能体

- **经验随会话消失**：修复、踩坑与运维片段在会话结束后即丢失；下一个智能体从零开始。
- **成本成倍增加**：当 *N* 个智能体独立遇到同一问题时，整体付出 *N* 倍排查成本。
- **调优画像无法迁移**：精心接线的人设、技能与工具配置留在本地，每个新实例都要重新摸索。

#### 🙆‍♂️ 由 Ultron 驱动的智能体

- **群体记忆**：经验被捕获、去重并在推理前按语义召回，整个集群从每次会话中学习。
- **记忆结晶为技能**：修复经足够验证后，从记忆升级为任意智能体可直接调用的可复用技能。
- **一键蓝图**：专家级智能体画像（含人设、记忆与技能）可发布为共享蓝图，其他实例一步导入。

---

### 效果对比

> 场景：开发者让智能体排查使用 `mode="session"` 调用 `sessions_spawn` 创建子智能体时的错误。此前另一智能体已踩过同一坑，解法已沉淀为群体记忆。

#### ❌ 未接入 Ultron

> **用户**：我想用 sessions_spawn 创建一个子 agent 来并行处理任务，用 mode=session，但一直报错，怎么回事？
>
> **Agent**：根据我的工具定义，创建子 agent 应该使用 `spawn` 工具，而不是 `sessions_spawn`。
>
> *Agent 不认识 sessions_spawn，给出了完全错误的方向。*

#### ✅ 接入 Ultron

> **用户**：我想用 sessions_spawn 创建一个子 agent 来并行处理任务，用 mode=session，但一直报错，怎么回事？
>
> **Agent**：根据召回的群体记忆，找到了问题所在！
>
> 📌 召回记忆：`sessions_spawn` 的 `mode="session"` 必须配合 `thread=true`，且需要 channel 插件注册 `subagent_spawning` hooks。缺少 hooks 时无论参数是否正确都会失败。
>
> *1 轮对话，直接命中根因并给出分场景方案。*


| 维度   | 未接入 Ultron                       | 接入 Ultron                             |
| ---- | -------------------------------- | ------------------------------------- |
| 工具识别 | 不认识 `sessions_spawn`，误导为 `spawn` | 准确识别工具及其参数约束                          |
| 根因定位 | 完全偏离                             | 直达根因：缺少 `thread=true` 或 channel hooks |
| 解决方案 | 无效                               | 分场景给出两种方案                             |
| 知识来源 | 智能体从零猜测                       | 召回群体记忆中已验证的踩坑经验                       |

---

### 数据

#### 记忆（来源 [ZClawBench](https://huggingface.co/datasets/zai-org/ZClawBench)）

从真实智能体任务轨迹中提取的 **1,746** 条结构化记忆：

| 类型 | 数量 |
|------|------|
| `pattern` | 1,254 |
| `error` | 196 |
| `security` | 128 |
| `life` | 122 |
| `correction` | 46 |

#### 技能

**内部**（由记忆生成）：记忆进入 HOT 层时自动生成的 **182** 条技能。

**外部**（[ModelScope Skill Hub](https://www.modelscope.cn/skills)）：已嵌入索引的 **30,000** 条技能，覆盖开发工具（11,415）、代码质量（6,696）、前端（2,530）等类别。

#### Harness

在 Harness 中可与记忆、技能一并拼装 **角色（Role）**、**人格（MBTI）**、**星座（Zodiac）** 预设。

| 维度 | 大类数量 | 预设数量 |
|------|----------|----------|
| **角色** | **14**（`mbti`、`zodiac` 以外的子目录，如 `academic`、`engineering`、`marketing`、`specialized` 等） | **173** |
| **人格（MBTI）** | **1**（目录 `mbti`） | **16**（16 型全覆盖） |
| **星座** | **1**（目录 `zodiac`） | **12**（十二星座） |

**合计** 灵魂预设：**201** 条（173 + 16 + 12）。

---

## 核心能力

### 💭 Memory Hub

| 能力 | 说明 |
|------|------|
| **分层存储** | HOT / WARM / COLD 三层，按 `hit_count` 百分位再平衡；嵌入语义检索并对层级加权 |
| **L0 / L1 / Full** | 自动生成一句话摘要（L0）与核心概览（L1）；检索默认返回 L0/L1 节省 token，可按需取全文 |
| **自动类型分类** | 上传时 LLM 优先、关键词兜底分类；调用方无需指定 `memory_type` |
| **去重与合并** | 同类型近重复向量自动合并并重算嵌入与摘要；支持批量整理 |
| **意图扩展检索** | 将查询扩展为多角度检索短语以提升召回 |
| **连续时间衰减** | `hotness = exp(-α × days)`，长期未命中则在排序中自然降级 |
| **智能入库** | 支持文件、文本或 `.jsonl` 会话日志；LLM 自动抽取结构化记忆并支持增量进度 |
| **数据脱敏** | 基于 Presidio 的中英双语 PII 检测，写入前自动脱敏 |

### 🧬 Skill Hub

| 能力 | 说明 |
|------|------|
| **技能蒸馏** | 记忆进入 HOT 层时自动生成可复用技能；智能体也可直接上传技能包 |
| **统一发现** | 内部蒸馏技能与 3 万+ 外部已索引 ModelScope 技能同一处检索 |
| **改进建议** | 语义相近的记忆会提示为既有技能的增强候选 |

### 🌐 Harness Hub

| 能力 | 说明 |
|------|------|
| **画像发布** | 将完整智能体画像（人设、记忆、技能）发布为可分享蓝图，支持短码导入 |
| **双向同步** | 智能体工作区状态可与服务器上下同步，便于多设备连续使用 |
| **Soul 预设** | 从预设库（角色、MBTI、星座等）编排人设并生成工作区资源 |

---

## 典型使用场景

- **共享避坑（Memory Hub）**：智能体 A 遇到「MySQL 8.0 默认字符集导致 emoji 写入失败」，修复沉淀到 Memory Hub。数周后智能体 B 建新库时自动命中同一条记忆，跳过陷阱，无需重复排查。
- **运维技能包（Skill Hub）**：SRE 将「K8s OOMKilled → 定位泄漏 → 调整 limits → 灰度验证」打成可复用技能，其他团队的智能体按相同步骤执行，而不是各自重写流程。
- **领域专家智能体（Harness Hub）**：DevOps 工程师花数周把智能体调成 Kubernetes 专家（记忆、技能、人设齐备），将画像发布到 Harness Hub，他人一键导入。

---

## 案例展示

### FinanceBot：通过 Harness Hub 调教的领域专家

**FinanceBot** 是纪律严格的金融助手（数据工程师角色，ISTJ，摩羯座），内置 **Finnhub Pro（技能）**、**五条关于真实金融数据工作的精选群体记忆**，以及可一步导入的完整 Harness 画像。

<p align="center">
  <img src="asset/financebot-compose.png" width="900" alt="FinanceBot：Harness Hub 编排工作区" />
  <br/>
</p>

**能力概览**：实时行情、ETL 式流水线、稳健的 API 对接、组合与风险视图、结构化报告。

**完整介绍**：[English](docs/en/Showcase/financebot.md) · [中文](docs/zh/Showcase/financebot.md)

**一键导入**（导入前工作区会备份到 `~/.ultron/harness-import-backups/`）：

```bash
curl -fsSL "https://writtingforfun-ultron.ms.show/i/at3ZEe?product=nanobot" | bash   # Nanobot
curl -fsSL "https://writtingforfun-ultron.ms.show/i/at3ZEe?product=openclaw" | bash # OpenClaw
curl -fsSL "https://writtingforfun-ultron.ms.show/i/at3ZEe?product=hermes" | bash   # Hermes Agent
```

---

## 🚀 智能体接入（连接你的智能体）

无需安装或通读 Ultron 源码。在已运行的 Ultron 实例上，按交互式快速入门操作，数分钟内即可完成接入：

👉 **[快速入门](https://writtingforfun-ultron.ms.show/quickstart)**：对接在线 Ultron 服务的分步指引

---

## 🛠 服务端部署（自建）

```bash
git clone https://github.com/modelscope/ultron.git
cd ultron
pip install -e .

# 配置 DashScope API Key（LLM 与嵌入必需）
echo 'DASHSCOPE_API_KEY=your-key' >> ~/.ultron/.env

# 启动服务（导入 ultron 时会加载 ~/.ultron/.env）
uvicorn ultron.server:app --host 0.0.0.0 --port 9999
# http://0.0.0.0:9999 ，控制台路径为 /dashboard
```

更多部署细节、API 参考、SDK 与项目结构见下表：

| 主题 | 链接 |
|------|------|
| 部署指南 | [docs/zh/GetStarted/Installation.md](docs/zh/GetStarted/Installation.md) |
| 配置参考 | [docs/zh/Components/Config.md](docs/zh/Components/Config.md) |
| HTTP API 参考 | [docs/zh/API/HttpAPI.md](docs/zh/API/HttpAPI.md) |
| Python SDK 参考 | [docs/zh/API/SDK.md](docs/zh/API/SDK.md) |
| 记忆服务 | [docs/zh/Components/MemoryService.md](docs/zh/Components/MemoryService.md) |
| 技能中心 | [docs/zh/Components/SkillHub.md](docs/zh/Components/SkillHub.md) |
| Harness 中心 | [docs/zh/Components/HarnessHub.md](docs/zh/Components/HarnessHub.md) |

---

## 路线图

详见 [ROADMAP.md](ROADMAP.md)。当前项包括：

- [ ] **MS-Agent 深度集成**：经 MS-Agent 组件贯通用户对话记忆与技能蒸馏（当前为轻量基于提示的抽取）。
- [ ] **事实核验**：对高优先级记忆事实借助 MS-Agent Deep Research 做校验。

---

## 致谢

Ultron 建立在以下开源项目之上，谨向作者与贡献者致谢：

- **[agency-agents](https://github.com/msitarzewski/agency-agents)**：Harness Hub 中的角色预设（及相关工具链）**改编自**该社区角色库；我们会跟踪上游以保留来源与更新。
- **[MS-Agent](https://github.com/modelscope/modelscope-agent)**：驱动 Ultron 的智能体框架。

---

## License

本项目采用 [Apache License (Version 2.0)](https://github.com/modelscope/modelscope/blob/master/LICENSE) 授权。
