# Copyright (c) ModelScope Contributors. All rights reserved.
import os
import json
from typing import Optional

from ...config import UltronConfig, default_config
from ...core.database import Database
from ...core.embeddings import EmbeddingService
from ...core.llm_service import LLMService
from ...core.storage import SkillStorage
from ...services.harness import HarnessService
from ...services.memory import ConversationExtractor, MemoryService
from ...services.skill import (
    SkillCatalogService,
    SkillRetriever,
)
from ...services.smart_ingestion import SmartIngestionService
from ...utils.llm_orchestrator import LLMOrchestrator
from ...utils.sanitizer import DataSanitizer
from ...utils.skill_parser import SkillParser
from ._core import CoreMixin
from ._harness import HarnessMixin
from ._memory import MemoryMixin
from ._skills import SkillMixin


class Ultron(MemoryMixin, SkillMixin, HarnessMixin, CoreMixin):
    """
    Ultron: collective intelligence system for assistant ecosystems (OpenClaw, Nanobot, etc.).

    Besides technical know-how, it supports general life-style shareable experience
    (server-side classification) and skill evolution from knowledge clusters.

    API layers:
    - Memory Hub: ``upload_memory``, ``search_memories``, ``get_memory_details``.
    - Skill Hub: ``search_skills``, ``upload_skill``, ``install_skill``.
    - Harness Hub: ``harness_sync_up``, ``harness_sync_down``, ``get_harness_profile``, ``create_harness_share``, ``list_harness_shares``, ``delete_harness_share``.
    """

    def __init__(
        self,
        data_dir: Optional[str] = None,
        config: Optional[UltronConfig] = None,
    ):
        self.config = config or default_config
        if data_dir:
            self.config.data_dir = data_dir

        if self.config.dashscope_api_key:
            os.environ["DASHSCOPE_API_KEY"] = self.config.dashscope_api_key
        if self.config.llm_api_key:
            if (self.config.llm_provider or "").strip().lower() == "dashscope":
                os.environ["DASHSCOPE_API_KEY"] = self.config.llm_api_key
            else:
                os.environ["OPENAI_API_KEY"] = self.config.llm_api_key

        self.config.ensure_directories()

        self.db = Database(str(self.config.db_path))
        self.storage = SkillStorage(
            str(self.config.skills_dir),
            str(self.config.archive_dir),
        )
        self.embedding = EmbeddingService(
            backend=self.config.embedding_backend,
            model_name=self.config.embedding_model,
            embedding_dimension_hint=self.config.embedding_dimension,
            request_timeout_seconds=self.config.llm_request_timeout_seconds,
        )
        self._write_embedding_profile()

        self.parser = SkillParser()
        self.sanitizer = DataSanitizer()

        self.llm_service = LLMService(
            provider=self.config.llm_provider,
            model=self.config.llm_model,
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key,
            max_input_tokens=self.config.llm_max_input_tokens,
            prompt_reserve_tokens=self.config.llm_prompt_reserve_tokens,
            tiktoken_encoding=self.config.llm_token_count_encoding,
            request_timeout_seconds=self.config.llm_request_timeout_seconds,
            max_retries=self.config.llm_max_retries,
            retry_base_delay_seconds=self.config.llm_retry_base_delay_seconds,
        )
        self.memory_category_llm_service = LLMService(
            provider=self.config.llm_provider,
            model=self.config.memory_category_llm_model,
            base_url=self.config.llm_base_url,
            api_key=self.config.llm_api_key,
            max_input_tokens=self.config.llm_max_input_tokens,
            prompt_reserve_tokens=self.config.llm_prompt_reserve_tokens,
            tiktoken_encoding=self.config.llm_token_count_encoding,
            request_timeout_seconds=self.config.llm_request_timeout_seconds,
            max_retries=self.config.llm_max_retries,
            retry_base_delay_seconds=self.config.llm_retry_base_delay_seconds,
        )
        self.llm_orchestrator = LLMOrchestrator(
            self.llm_service,
            classify_llm_service=self.memory_category_llm_service,
        )

        self.catalog = SkillCatalogService(self.db, self.config)

        self.memory_service = MemoryService(
            self.db,
            self.embedding,
            self.sanitizer,
            self.config,
            llm_service=self.llm_service,
            llm_orchestrator=self.llm_orchestrator,
        )

        self.retriever = SkillRetriever(
            self.db,
            self.embedding,
            memory_service=self.memory_service,
            config=self.config,
            llm_service=self.llm_service,
        )

        self.conversation_extractor = ConversationExtractor(
            memory_service=self.memory_service,
            llm_orchestrator=self.llm_orchestrator,
            database=self.db,
            config=self.config,
        )

        self.smart_ingestion = SmartIngestionService(
            memory_service=self.memory_service,
            llm_service=self.llm_service,
            llm_orchestrator=self.llm_orchestrator,
            config=self.config,
            conversation_extractor=self.conversation_extractor,
            database=self.db,
        )

        self.harness = HarnessService(self.db)

    def _write_embedding_profile(self) -> None:
        """Persist current embedding settings for observability (no consistency enforcement)."""
        profile_file = self.config.models_dir / "embedding_profile.json"
        current = {
            "backend": self.config.embedding_backend,
            "model": self.config.embedding_model,
            "dimension": int(self.embedding.dimension),
        }
        profile_file.write_text(
            json.dumps(current, ensure_ascii=True, indent=2), encoding="utf-8"
        )
