# Copyright (c) ModelScope Contributors. All rights reserved.

SOURCE_ONLY_SLUGS = frozenset({
    "evolution",
    "catalog",
})

CATEGORY_DEFINITIONS = {
    "coding-agents-ides": (
        "Coding Agents & IDEs — agent and IDE integrations"
    ),
    "web-frontend": (
        "Web & Frontend — web and front-end development"
    ),
    "devops-cloud": (
        "DevOps & Cloud — infra, containers, and delivery"
    ),
    "git-github": (
        "Git & GitHub — version control and collaboration"
    ),
    "cli-utilities": (
        "CLI Utilities — shells, scripts, and command-line tooling"
    ),
    "ios-macos-dev": (
        "iOS & macOS — Apple platform development"
    ),
    "ai-llms": (
        "AI & LLMs — models, prompts, and AI applications"
    ),
    "data-analytics": (
        "Data & Analytics — ingestion, analysis, and BI-style workflows"
    ),
    "image-video-gen": (
        "Image & Video — generative media"
    ),
    "speech-transcription": (
        "Speech & Transcription — ASR, TTS, and voice UX"
    ),
    "browser-automation": (
        "Browser Automation — scraping and UI automation"
    ),
    "self-hosted-automation": (
        "Self-Hosted Automation — workflows and DIY integration"
    ),
    "agent-protocols": (
        "Agent Protocols — interoperable agent-to-agent interfaces"
    ),
    "smart-home-iot": (
        "Smart Home & IoT — home and device automation"
    ),
    "life-daily": (
        "Life & Daily — household tips, etiquette, routines (no personal secrets)"
    ),
    "cooking-meal-prep": (
        "Cooking & Meal Prep — recipes and prep ideas (not individualized medical nutrition)"
    ),
    "productivity-tasks": (
        "Productivity & Tasks — task and project systems"
    ),
    "search-research": (
        "Search & Research — discovery and synthesis"
    ),
    "notes-pkm": (
        "Notes & PKM — knowledge bases and note systems"
    ),
    "pdf-documents": (
        "PDF & Documents — document processing"
    ),
    "calendar-scheduling": (
        "Calendar & Scheduling — time and meetings"
    ),
    "communication": (
        "Communication — chat, email, and messaging"
    ),
    "marketing-sales": (
        "Marketing & Sales — growth and revenue workflows"
    ),
    "finance": (
        "Finance — money, markets, and accounting basics"
    ),
    "health-fitness": (
        "Health & Fitness — wellness and activity habits (general guidance)"
    ),
    "shopping-ecommerce": (
        "Shopping & E-commerce — buying and retail flows"
    ),
    "media-streaming": (
        "Media & Streaming — entertainment consumption"
    ),
    "transportation": (
        "Transportation — travel and mobility"
    ),
    "gaming": (
        "Gaming — games and related tooling"
    ),
    "personal-development": (
        "Personal Development — skills and habits"
    ),
    "apple-apps": (
        "Apple Apps & Services — first-party Apple ecosystem"
    ),
    "clawhub-tools": (
        "Clawhub Tools — platform-specific helpers"
    ),
    "moltbook": (
        "Moltbook — Moltbook integrations"
    ),
    "security-passwords": (
        "Security & Passwords — auth, secrets, and hardening"
    ),
    "evolution": (
        "Source: crystallized from a knowledge cluster (skill evolution)"
    ),
    "catalog": (
        "Source: ModelScope Skill Hub catalog"
    ),
    "general": (
        "General / uncategorized"
    ),
}

KEYWORD_MAP = {
    "coding-agents-ides": [
        "agent", "ide", "vscode", "cursor", "copilot", "claude",
        "code completion", "编码", "代码生成",
    ],
    "web-frontend": [
        "react", "vue", "angular", "html", "css", "tailwind",
        "next.js", "nuxt", "svelte", "frontend", "前端", "web",
        "javascript", "typescript", ".js", ".ts", "npm", "yarn", "node",
    ],
    "devops-cloud": [
        "docker", "kubernetes", "k8s", "terraform", "ansible",
        "aws", "gcp", "azure", "ci/cd", "jenkins", "github actions",
        "deploy", "container", "部署", "云", "运维",
    ],
    "git-github": [
        "git", "github", "commit", "branch", "merge", "pull request",
        "pr", "rebase", "版本控制",
    ],
    "cli-utilities": [
        "bash", "shell", "zsh", "terminal", "command line", "cli",
        "脚本", "命令行",
    ],
    "ios-macos-dev": [
        "swift", "swiftui", "xcode", "ios", "macos", "apple",
        "objective-c", "cocoa",
    ],
    "ai-llms": [
        "llm", "gpt", "claude", "openai", "anthropic", "langchain",
        "prompt", "embedding", "大模型", "大语言模型", "ai",
    ],
    "data-analytics": [
        "pandas", "numpy", "data", "csv", "analytics", "dataset",
        "数据分析", "数据处理", "etl",
    ],
    "image-video-gen": [
        "image generation", "stable diffusion", "midjourney", "dall-e",
        "video", "图像生成",
    ],
    "speech-transcription": [
        "speech", "transcription", "whisper", "tts", "stt",
        "语音", "转录",
    ],
    "browser-automation": [
        "browser", "selenium", "playwright", "puppeteer", "scrape",
        "crawl", "爬虫", "浏览器",
    ],
    "self-hosted-automation": [
        "self-hosted", "automation", "workflow", "n8n", "zapier",
        "自动化", "工作流",
    ],
    "agent-protocols": [
        "a2a", "mcp", "protocol", "agent-to-agent", "协议",
    ],
    "smart-home-iot": [
        "home assistant", "iot", "smart home", "mqtt", "智能家居",
    ],
    "life-daily": [
        "家务", "育儿", "带娃", "清洁", "收纳", "洗衣", "打扫",
        "礼仪", "做客", "送礼", "节日", "搬家", "租房",
        "生活窍门", "日常", "过日子", "routine", "chores",
    ],
    "cooking-meal-prep": [
        "菜谱", "做饭", "烹饪", "备餐", "食材", "调味", "快手菜",
        "meal prep", "recipe", "cook",
    ],
    "productivity-tasks": [
        "todo", "task", "productivity", "project management",
        "任务", "生产力",
    ],
    "search-research": [
        "search", "research", "google", "bing", "搜索", "研究",
    ],
    "notes-pkm": [
        "obsidian", "notion", "note", "pkm", "knowledge base",
        "笔记", "知识库",
    ],
    "pdf-documents": [
        "pdf", "document", "docx", "word", "文档",
    ],
    "calendar-scheduling": [
        "calendar", "schedule", "meeting", "日历", "日程",
    ],
    "communication": [
        "slack", "discord", "email", "telegram", "chat", "message",
        "消息", "沟通",
    ],
    "marketing-sales": [
        "marketing", "sales", "seo", "campaign", "营销", "销售",
    ],
    "finance": [
        "finance", "stock", "crypto", "payment", "invoice",
        "金融", "财务",
    ],
    "health-fitness": [
        "health", "fitness", "medical", "健康", "健身", "作息", "睡眠",
        "运动习惯", "拉伸", "久坐", "wellness",
    ],
    "transportation": [
        "flight", "train", "地铁", "公交", "打车", "导航", "出行",
        "旅行", "行李", "登机", "commute", "travel",
    ],
    "shopping-ecommerce": [
        "shopping", "ecommerce", "product", "cart", "购物", "电商",
    ],
    "security-passwords": [
        "security", "password", "auth", "encryption", "vulnerability",
        "cve", "密钥", "安全", "认证", "加密",
    ],
    "general": [
        "python", ".py", "pip", "java", "sql", "database",
        "file", "config", "test", "debug", "error", "fix",
        "log", "monitor",
    ],
}

CATEGORY_TREE = {
    "development_engineering": [
        "coding-agents-ides", "web-frontend", "devops-cloud",
        "git-github", "cli-utilities", "ios-macos-dev",
    ],
    "ai_data": [
        "ai-llms", "data-analytics", "image-video-gen",
        "speech-transcription",
    ],
    "automation_integration": [
        "browser-automation", "self-hosted-automation",
        "agent-protocols", "smart-home-iot",
    ],
    "life_daily": [
        "life-daily", "cooking-meal-prep",
    ],
    "productivity_knowledge": [
        "productivity-tasks", "search-research", "notes-pkm",
        "pdf-documents", "calendar-scheduling", "communication",
    ],
    "industry_vertical": [
        "marketing-sales", "finance", "health-fitness",
        "shopping-ecommerce", "media-streaming", "transportation",
        "gaming", "personal-development",
    ],
    "platforms": [
        "apple-apps", "clawhub-tools", "moltbook",
    ],
    "security": ["security-passwords"],
    "source_types": [
        "evolution",
        "catalog",
    ],
    "general": ["general"],
}
