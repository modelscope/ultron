## 文档维护指南

### 1. 构建文档

```shell
# 在 ultron 根目录:
cd docs/zh
make html
```

### 2. 文档字符串格式

我们采用 Google 风格的 docstring 格式作为标准，请参考以下文档：

1. Google Python 风格指南 docstring [链接](http://google.github.io/styleguide/pyguide.html#381-docstrings)
2. Google docstring 示例 [链接](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html)

示例：

```python
def upload_memory(
    self,
    content: str,
    context: str,
    resolution: str,
    tags: Optional[List[str]] = None,
) -> MemoryRecord:
    """Upload a memory record to the remote shared memory store.

    The memory type is determined automatically by the server-side LLM (or rules);
    callers cannot specify memory_type. Near-duplicates are merged and hit count
    incremented. See MemoryService.upload_memory for details.

    Args:
        content: Memory content (error message, experience description, etc.)
        context: Context or scenario description
        resolution: Solution or handling approach
        tags: Optional list of tags

    Returns:
        MemoryRecord: Newly created or merged memory record

    Examples:
        >>> ultron.upload_memory(
        ...     content="ModuleNotFoundError: No module named 'pandas'",
        ...     context="Running script inside Docker container",
        ...     resolution="pip install pandas",
        ... )
    """
```

### 3. 目录结构

```
docs/
├── README.md              # 本文件
├── en/                    # English docs (mirror of zh layout)
│   ├── index.rst
│   ├── GetStarted/
│   │   ├── Introduction.md
│   │   ├── Installation.md
│   │   └── AgentSetup.md
│   ├── Components/
│   │   ├── Config.md
│   │   ├── MemoryHub.md
│   │   ├── TrajectoryHub.md
│   │   ├── SkillHub.md
│   │   └── HarnessHub.md
│   ├── API/
│   │   ├── HttpAPI.md
│   │   └── SDK.md
│   └── Showcase/
│       └── financebot.md
└── zh/                    # 中文文档
    ├── index.rst          # 主索引
    ├── GetStarted/        # 快速开始
    │   ├── Introduction.md
    │   ├── Installation.md
    │   └── AgentSetup.md
    ├── Components/        # 核心组件
    │   ├── Config.md
    │   ├── MemoryHub.md
    │   ├── TrajectoryHub.md
    │   ├── SkillHub.md
    │   └── HarnessHub.md
    ├── API/               # 接口文档
    │   ├── HttpAPI.md
    │   └── SDK.md
    └── Showcase/          # 案例展示
        └── financebot.md
```
