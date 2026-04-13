# Copyright (c) ModelScope Contributors. All rights reserved.
from typing import List, Optional


_LLM_PROMPT = """\
You are the search planner for the Ultron knowledge base.

Break the user query below into 2–4 distinct search phrases for semantic retrieval over memories and skills.

Steps:
1. Infer task type (debugging, how-to, factual lookup, or everyday/life-hack style tips).
2. Rephrase from different angles (wording, root cause, fix, scenario).
3. Each phrase at most 40 characters (count characters, not bytes). Keep the same primary language as the query.

Rules:
- The first element MUST be the exact original query.
- Other elements paraphrase the same intent from other angles.
- Output ONLY a JSON array of strings—no markdown, no prose.

Example input: "pip install fails inside Docker container"
Example output: ["pip install fails inside Docker container", "Docker pip install error fix", "Python dependency permission in container"]

Query: {query}"""


class IntentAnalyzer:
    """
    Expands a search query into several paraphrases for embedding retrieval.

    When ``llm_service`` is available, uses an LLM (temperature 0) to produce
    a JSON string array. On any failure or missing LLM, returns only the original query.
    """

    def __init__(self, llm_service=None):
        self.llm = llm_service

    def analyze(self, query: str) -> List[str]:
        """
        Return an expanded query list, or ``[query]`` if the LLM is unavailable
        or the call fails or yields no usable phrases.
        """
        if not query or not query.strip():
            return [query]

        if self.llm and self.llm.is_available:
            result = self._analyze_llm(query)
            if result:
                return result

        return [query.strip()]

    def _analyze_llm(self, query: str) -> Optional[List[str]]:
        prompt = _LLM_PROMPT.format(query=query)
        try:
            resp = self.llm.call(self.llm.dashscope_user_messages(prompt))
            if not resp:
                return None
            parsed = self.llm.parse_json_response(resp, expect_array=True)
            if not isinstance(parsed, list) or not parsed:
                return None
            queries = [str(q).strip() for q in parsed if str(q).strip()]
            if not queries:
                return None
            if queries[0].strip().lower() != query.strip().lower():
                queries.insert(0, query.strip())
            return self._dedup(queries)
        except Exception:
            return None

    @staticmethod
    def _dedup(queries: List[str]) -> List[str]:
        seen: set = set()
        out = []
        for q in queries:
            k = q.strip().lower()
            if k and k not in seen:
                seen.add(k)
                out.append(q.strip())
        return out
