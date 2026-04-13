---

## slug: SkillHub
title: 技能中心
description: Ultron (奥创) 技能中心

# 技能中心

技能中心（Skill Hub）是 Ultron 的结构化知识库，存储从记忆中凝练或由 agent 上传的可复用技能，支持语义检索与自动分类。

## 核心概念

### 技能结构

每个技能由以下部分组成：


| 组成部分 | 文件           | 说明                             |
| ---- | ------------ | ------------------------------ |
| 元数据  | `_meta.json` | 所有者、版本、发布时间、状态、嵌入向量            |
| 内容   | `SKILL.md`   | YAML frontmatter + Markdown 正文 |
| 脚本   | `scripts/`   | 可选的辅助脚本                        |


### 技能状态


| 状态         | 说明   |
| ---------- | ---- |
| `active`   | 活跃可用 |
| `archived` | 已归档  |


### 技能来源


| 来源                       | 说明                         |
| ------------------------ | -------------------------- |
| `memory_crystallization` | 从高频记忆自动凝练生成                |
| `error_learning`         | 从错误记忆生成                    |
| `security_learning`      | 从安全记忆生成                    |
| `generation`             | 通用生成（兜底）                   |
| `catalog`                | 来自 ModelScope Skill Hub 目录 |


## 使用示例

### 检索技能

```python
from ultron import Ultron

ultron = Ultron()

# 语义检索技能
results = ultron.search_skills(
    query="如何解决 Python 导入错误",
    limit=5,
)

for r in results:
    print(f"技能: {r.skill.name}")
    print(f"  描述: {r.skill.description}")
    print(f"  相似度: {r.similarity_score:.4f}")
```

### 上传技能

```python
# 从目录上传（目录需包含 SKILL.md + _meta.json）
result = ultron.upload_skills(
    paths=["/path/to/my-skill-dir"],
)

# 批量：扫描父目录下所有含 SKILL.md 的子目录
result = ultron.upload_skills(
    paths=["/path/to/skills-folder"],
)
```

## 技能目录结构

```
~/.ultron/skills/
├── python-import-error-1.0.0/
│   ├── _meta.json
│   ├── SKILL.md
│   └── scripts/
│       └── check_imports.py
├── docker-debugging-1.0.0/
│   ├── _meta.json
│   └── SKILL.md
└── ...
```

## SKILL.md 格式

```markdown
---
name: python-import-error
description: 解决 Python 模块导入错误
metadata:
  ultron:
    categories:
      - debugging
      - python
    complexity: low
    source_type: error_learning
---

# Python 导入错误解决方案

## 问题描述

当遇到 `ModuleNotFoundError` 错误时...

## 解决步骤

1. 检查模块是否安装
2. ...

## 示例

```python
# 示例代码
```

```

## 与记忆的关系

技能是从高频记忆中凝练的结构化知识：

| 记忆 (Memory) | → | 技能 (Skill) |
|---|---|---|
| 具体错误案例 | 凝练 | 通用解决方案 |
| 多次命中，进入 HOT | → | 结构化文档，可复用 |

自动批量生成（`auto_detect_and_generate`）的候选条件（见 `get_promotion_candidates`）：
- 记忆进入 HOT 层级
- 尚未生成关联技能（`generated_skill_slug` 为空）

随后按 `hit_count`、时间新鲜度等打分排序；未传 `limit` 时处理条数由 `UltronConfig.skill_auto_detect_batch_limit`（`ULTRON_SKILL_AUTO_DETECT_LIMIT`）决定，显式传入 `limit` 时优先。

## 外部技能目录（ModelScope Skill Hub）

Ultron 支持从 ModelScope Skill Hub 检索技能（5700+ 条），与内部技能统一检索、按相似度排序返回。

### 导入目录

通过 `scripts/import_skill_catalog.py` 将 `skills.json` 导入本地数据库并预计算嵌入向量：

```bash
python scripts/import_skill_catalog.py --catalog skills.json --batch-size 20 --sleep 0.3
```

支持参数：`--catalog`（skills.json 路径）、`--batch-size`（每批嵌入数量）、`--sleep`（批次间隔秒数）、`--skip-existing`（跳过已有嵌入的条目）。

### 统一检索

调用 `search_skills` 时，搜索结果同时包含内部技能和目录技能，按相似度排序。每条结果带以下字段用于区分来源：


| 字段          | 说明                                    |
| ----------- | ------------------------------------- |
| `source`    | `"internal"`（内部技能）或 `"catalog"`（目录技能） |
| `full_name` | 目录技能的完整名称，如 `@ns/skill-name`          |


### 安装技能

`install_skill_to` 统一处理两个来源：优先查找 Ultron 内部技能（按 slug），找不到则通过 `modelscope skill add` 从 ModelScope 安装。

```python
# 安装内部技能（直接用 slug）
result = ultron.install_skill_to(
    full_name="ultron",
    target_dir="~/.nanobot/workspace/skills",
)
# result: {"success": true, "source": "internal", "installed_path": "..."}

# 安装 ModelScope 目录技能
result = ultron.install_skill_to(
    full_name="@anthropics/minimax-pdf",
    target_dir="~/.nanobot/workspace/skills",
)
# result: {"success": true, "source": "catalog", "installed_path": "..."}
```

