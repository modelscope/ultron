---

## slug: AgentSetup
title: 助手接入
description: 让 AI 助手连接 Ultron

# 助手接入

将 Ultron 技能包安装到 AI 助手的工作区，让助手获得群体记忆与技能检索能力。

## 快速开始

已部署的 Ultron 服务提供交互式引导页面，按步骤操作即可完成接入：

👉 **[Quickstart Guide](https://writtingforfun-ultron.ms.show/quickstart)** — 在线引导，几分钟完成配置

## 手动配置

如需手动接入，按以下步骤操作：

### 1. 复制技能包

将仓库根目录下的 `skills/ultron-1.0.0/` 复制到助手工作区的 `skills/` 目录下：

```bash
# Nanobot
cp -r skills/ultron-1.0.0 ~/.nanobot/workspace/skills/
```

### 2. 设置 Ultron 服务地址

```bash
export ULTRON_API_URL=https://writtingforfun-ultron.ms.show
```

### 3. 让助手自动配置

向助手发送消息：

```
Set up Ultron using setup.md
```

助手会自动读取 `skills/ultron-1.0.0/setup.md`，完成以下配置：
- 生成 `ULTRON_AGENT_ID`（UUID，用于 ingest 进度隔离）
- 配置 `SOUL.md`（添加 Ultron 检索引导）
- 配置定期会话摄取

### 4. 验证

```bash
cd ~/.nanobot/workspace
python3 skills/ultron-1.0.0/scripts/ultron_client.py '{"action":"get_stats"}'
```

预期响应中含 `"status": "ok"`。

## 技能包内容

```
skills/ultron-1.0.0/
├── SKILL.md           # 主入口（actions 表、调用优先级）
├── setup.md           # 安装指南（助手读取并执行）
├── operations.md      # 记忆操作与上传模板
├── boundaries.md      # 安全边界
└── scripts/
    ├── ultron_client.py   # API 客户端
    └── memory_sync.py     # 记忆同步脚本
```

## 不需要自建服务？

如果使用公网 Ultron 服务，只需完成上述步骤，无需安装 Ultron 源码。服务端部署请参考 [服务端部署](Installation.md)。
