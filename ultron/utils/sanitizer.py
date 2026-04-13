# Copyright (c) ModelScope Contributors. All rights reserved.
import re
from typing import List, Optional, Tuple

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine


class DataSanitizer:
    """
    PII and credential sanitizer for memory records.

    Uses Microsoft Presidio with spaCy for English and Chinese PII detection.
    Regex patterns cover API keys, tokens, and file paths not handled by Presidio.
    Called automatically by MemoryService before writing to the database.
    """

    # Path patterns (not handled by Presidio)
    PATH_PATTERNS = [
        (r"/Users/[^/\s]+", "/Users/<USER>"),
        (r"/home/[^/\s]+", "/home/<USER>"),
        (r"/root", "/<ROOT>"),
        (r"C:\\Users\\[^\\s]+", r"C:\\\\Users\\\\<USER>"),
        (r"[A-Z]:\\[^\\s]*\\[^\\s]*", "<PATH>"),
    ]

    # Specific key patterns must come before the generic credential pattern
    CREDENTIAL_PATTERNS = [
        (r"sk-[a-zA-Z0-9]{20,}", "<LLM_API_KEY>"),
        (r"ghp_[a-zA-Z0-9]{36}", "<GITHUB_TOKEN>"),
        (r"gho_[a-zA-Z0-9]{36}", "<GITHUB_OAUTH_TOKEN>"),
        (r"AKIA[0-9A-Z]{16}", "<AWS_ACCESS_KEY>"),
        (r"Bearer\s+[a-zA-Z0-9\-_\.]+", "Bearer <REDACTED_TOKEN>"),
        (r"Basic\s+[a-zA-Z0-9\+/=]+", "Basic <REDACTED>"),
        (
            r'["\']?[a-zA-Z_]*(?:api[_-]?key|apikey|token|secret|password|passwd|pwd)["\']?\s*[:=]\s*["\']?[\w\-\.]+["\']?',
            "<REDACTED_CREDENTIAL>",
        ),
        (r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<UUID>"),
        # Chinese phone numbers (may be missed by English Presidio model)
        (r"1[3-9]\d{9}", "<PHONE_NUMBER>"),
    ]

    # Presidio entities to exclude from anonymization:
    # - URL/NRP: cause false positives on technical text
    # - US_DRIVER_LICENSE: matches version strings
    # - DATE_TIME: matches release tags
    # - LOCATION: place names are core information in life/travel memories;
    #   redacting them (e.g. "从<LOCATION>赴开封") makes the memory useless
    # - PERSON: Chinese spaCy NER has very high false-positive rate on
    #   technical terms, tool names, and Chinese proper nouns (e.g.
    #   "万岁山" → "<PERSON>山", "User-Agent" → "<PERSON>-Agent");
    #   even correct hits (e.g. UP主 names) carry useful context
    # - ORGANIZATION: brand/hotel/school names are useful recommendation info
    _PRESIDIO_EXCLUDE = {
        "URL",
        "NRP",
        "US_DRIVER_LICENSE",
        "DATE_TIME",
        "LOCATION",
        "PERSON",
        "ORGANIZATION",
    }

    @staticmethod
    def _spacy_analyzer(lang_code: str, model_name: str) -> AnalyzerEngine:
        # Use *_sm models only: Presidio's default AnalyzerEngine() loads en_core_web_lg (~400MB).
        return AnalyzerEngine(
            nlp_engine=NlpEngineProvider(
                nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": lang_code, "model_name": model_name}],
                }
            ).create_engine(),
            supported_languages=[lang_code],
        )

    def __init__(self, custom_patterns: List[Tuple[str, str]] = None):
        self.custom_patterns = custom_patterns or []
        self._en_analyzer = self._spacy_analyzer("en", "en_core_web_sm")
        self._zh_analyzer = self._spacy_analyzer("zh", "zh_core_web_sm")
        self._anonymizer = AnonymizerEngine()

    def _presidio_sanitize(self, text: str, language: str = "en") -> str:
        """Detect and anonymize PII using Presidio."""
        analyzer = self._zh_analyzer if language == "zh" else self._en_analyzer
        all_entities = {
            e for r in analyzer.registry.recognizers for e in r.supported_entities
        } - self._PRESIDIO_EXCLUDE
        results = analyzer.analyze(
            text=text, entities=list(all_entities), language=language
        )
        if not results:
            return text
        return self._anonymizer.anonymize(text=text, analyzer_results=results).text

    def _regex_sanitize(self, text: str, patterns: List[Tuple[str, str]]) -> str:
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _detect_language(text: str) -> str:
        """Detect whether text is primarily Chinese or English."""
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        return "zh" if chinese_chars / max(len(text), 1) > 0.2 else "en"

    def sanitize(self, text: str) -> Optional[str]:
        """Sanitize text by removing PII, credentials, and sensitive paths."""
        if not text:
            return text
        result = self._regex_sanitize(text, self.PATH_PATTERNS)
        result = self._regex_sanitize(result, self.CREDENTIAL_PATTERNS)
        lang = self._detect_language(result)
        result = self._presidio_sanitize(result, language=lang)
        if self.custom_patterns:
            result = self._regex_sanitize(result, self.custom_patterns)
        return result
