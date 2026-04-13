# Copyright (c) ModelScope Contributors. All rights reserved.
from __future__ import annotations

# English + Chinese security-oriented markers
_SECURITY_MARKERS = (
    "cve-",
    "cwe-",
    "xss",
    "sql injection",
    "sqli",
    "ssrf",
    "csrf",
    "rce",
    "lfi",
    "rfi",
    "idor",
    "xxe",
    "privilege escalation",
    "0day",
    "zero-day",
    "pentest",
    "penetration",
    "malware",
    "ransomware",
    "phishing",
    "trojan",
    "backdoor",
    "数据泄露",
    "信息泄露",
    "未授权访问",
    "越权",
    "权限提升",
    "入侵",
    "攻击面",
    "漏洞",
    "安全事件",
    "安全告警",
    "违规外联",
    "恶意软件",
    "钓鱼",
    "勒索",
    "木马",
    "后门",
    "撞库",
    "暴破",
    "爆破",
    "暴力破解",
    "供应链攻击",
)

# Troubleshooting / exception-oriented markers
_ERROR_MARKERS = (
    "traceback",
    "stack trace",
    "stacktrace",
    "exception:",
    "error:",
    "errno",
    "modulenotfound",
    "importerror",
    "syntaxerror",
    "typeerror",
    "valueerror",
    "keyerror",
    "attributeerror",
    "segmentation fault",
    "core dumped",
    "exit code",
    "exit status",
    "报错",
    "异常栈",
    "堆栈",
    "未捕获",
    "执行失败",
    "运行失败",
    "启动失败",
    "编译失败",
    "构建失败",
    "test failed",
    "assertionerror",
)


def infer_memory_type(content: str, context: str = "", resolution: str = "") -> str:
    """
    Heuristic fallback for memory_type when LLM classification is unavailable.

    Returns one of: error, security, pattern. When memory_type is auto,
    LLMService.classify_memory_type runs first; MemoryService._resolve_memory_type_auto
    uses this only if the LLM path fails.

    - security: incident / vuln / intrusion-style text
    - error: debugging and failure triage
    - pattern: default generalized reusable note
    """
    blob = f"{content}\n{context}\n{resolution}".lower()
    if any(m in blob for m in _SECURITY_MARKERS):
        return "security"
    if any(m in blob for m in _ERROR_MARKERS):
        return "error"
    return "pattern"
