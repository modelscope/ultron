# Copyright (c) ModelScope Contributors. All rights reserved.
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def load_ultron_dotenv() -> None:
    """
    Merge ``KEY=value`` pairs from ``~/.ultron/.env`` into ``os.environ`` before building ``UltronConfig``.

    Uses ``override=False`` so variables already set in the process (e.g. exported in the shell) are not replaced.

    If ``python-dotenv`` is not installed, this is a no-op.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(Path.home() / ".ultron" / ".env", override=False)


def _env_bool(key: str, default: bool) -> bool:
    """True unless env is 0/false/no/off (case-insensitive)."""
    default_s = "1" if default else "0"
    return os.environ.get(key, default_s).lower() not in ("0", "false", "no", "off")


def _data_dir_default() -> str:
    raw = os.environ.get("ULTRON_DATA_DIR", "").strip()
    if raw:
        return os.path.expanduser(raw)
    return os.path.expanduser("~/.ultron")


@dataclass
class UltronConfig:
    """
    Runtime tuning for storage, DashScope embeddings/LLM, memory tiers, retrieval, and archive toggles.

    Defaults are read from ``ULTRON_*`` and ``DASHSCOPE_API_KEY`` (including values merged from
    ``~/.ultron/.env`` by ``load_ultron_dotenv`` before ``default_config`` is built). Constructor
    arguments override env.
    """

    # Storage
    data_dir: str = field(default_factory=_data_dir_default)
    db_name: str = field(
        default_factory=lambda: (
            os.environ.get("ULTRON_DB_NAME", "ultron.db").strip() or "ultron.db"
        ),
    )

    # DashScope API key (LLM + TextEmbedding); written to ``os.environ`` when building ``Ultron``
    dashscope_api_key: str = field(
        default_factory=lambda: os.environ.get("DASHSCOPE_API_KEY", "").strip()
    )

    # Embeddings (single backend per service instance; do not mix backends/models without reset)
    embedding_backend: str = field(
        default_factory=lambda: os.environ.get("ULTRON_EMBEDDING_BACKEND", "dashscope")
    )
    embedding_model: str = field(
        default_factory=lambda: os.environ.get(
            "ULTRON_EMBEDDING_MODEL", "text-embedding-v4"
        )
    )
    embedding_dimension: int = field(
        default_factory=lambda: int(
            os.environ.get("ULTRON_EMBEDDING_DIMENSION", "1024")
        )
    )

    # Conversation extract: extra lines before ``new_lines`` for LLM context (no extra progress advance)
    session_extract_overlap_lines: int = field(
        default_factory=lambda: max(
            0, int(os.environ.get("ULTRON_SESSION_EXTRACT_OVERLAP_LINES", "5"))
        )
    )

    # Max tokens per chunk after stitching (windowing before each LLM extract call)
    conversation_extract_window_tokens: int = field(
        default_factory=lambda: max(
            256,
            int(os.environ.get("ULTRON_CONVERSATION_EXTRACT_WINDOW_TOKENS", "65536")),
        )
    )

    # Percentile-based tier distribution (rebalanced periodically)
    hot_percentile: int = field(
        default_factory=lambda: max(
            1,
            min(100, int(os.environ.get("ULTRON_HOT_PERCENTILE", "10"))),
        )
    )
    warm_percentile: int = field(
        default_factory=lambda: max(
            1,
            min(100, int(os.environ.get("ULTRON_WARM_PERCENTILE", "40"))),
        )
    )
    cold_ttl_days: int = field(
        default_factory=lambda: max(
            0,
            int(os.environ.get("ULTRON_COLD_TTL_DAYS", "30")),
        )
    )
    dedup_similarity_threshold: float = field(
        default_factory=lambda: min(
            1.0,
            max(
                0.0, float(os.environ.get("ULTRON_DEDUP_SIMILARITY_THRESHOLD", "0.85"))
            ),
        )
    )
    # Soft threshold: candidates in [soft, hard) are sent to LLM for confirmation
    dedup_soft_threshold: float = field(
        default_factory=lambda: min(
            1.0,
            max(0.0, float(os.environ.get("ULTRON_DEDUP_SOFT_THRESHOLD", "0.75"))),
        )
    )
    # Per-field cap after same-type merge (align encoding with llm_token_count_encoding)
    memory_merge_max_field_tokens: int = field(
        default_factory=lambda: int(
            os.environ.get("ULTRON_MEMORY_MERGE_MAX_FIELD_TOKENS", "8192")
        )
    )

    # L0/L1 snippet budgets for search responses
    l0_max_tokens: int = field(
        default_factory=lambda: int(os.environ.get("ULTRON_L0_MAX_TOKENS", "64"))
    )
    l1_max_tokens: int = field(
        default_factory=lambda: int(os.environ.get("ULTRON_L1_MAX_TOKENS", "256"))
    )

    # --- Memory consolidation (chain-merge) ---
    # Max merge operations per consolidate run (prevents runaway merges)
    consolidate_max_merges: int = field(
        default_factory=lambda: max(
            1,
            int(os.environ.get("ULTRON_CONSOLIDATE_MAX_MERGES", "50")),
        )
    )
    # Auto-run consolidation inside the periodic tier-rebalance task (default off)
    consolidate_enabled: bool = field(
        default_factory=lambda: _env_bool("ULTRON_CONSOLIDATE_ENABLED", False),
    )

    enable_intent_analysis: bool = field(
        default_factory=lambda: _env_bool("ULTRON_ENABLE_INTENT_ANALYSIS", True),
    )

    # Default max rows when search APIs omit ``limit`` (explicit parameters still win)
    memory_search_default_limit: int = field(
        default_factory=lambda: max(
            1,
            int(os.environ.get("ULTRON_MEMORY_SEARCH_LIMIT", "10")),
        )
    )
    skill_search_default_limit: int = field(
        default_factory=lambda: max(
            1,
            int(os.environ.get("ULTRON_SKILL_SEARCH_LIMIT", "5")),
        )
    )
    # Optional async embedding worker pool
    async_embedding: bool = field(
        default_factory=lambda: _env_bool("ULTRON_ASYNC_EMBEDDING", False),
    )
    embedding_queue_size: int = field(
        default_factory=lambda: max(
            1,
            int(os.environ.get("ULTRON_EMBEDDING_QUEUE_SIZE", "100")),
        )
    )
    embedding_queue_workers: int = field(
        default_factory=lambda: max(
            1,
            int(os.environ.get("ULTRON_EMBEDDING_QUEUE_WORKERS", "2")),
        )
    )

    # Time decay for tier hotness and ranking
    decay_interval_hours: float = field(
        default_factory=lambda: max(
            0.1,
            float(os.environ.get("ULTRON_DECAY_INTERVAL_HOURS", "6.0")),
        )
    )
    decay_alpha: float = field(
        default_factory=lambda: max(
            0.0,
            float(os.environ.get("ULTRON_DECAY_ALPHA", "0.05")),
        )
    )
    time_decay_weight: float = field(
        default_factory=lambda: max(
            0.0,
            float(os.environ.get("ULTRON_TIME_DECAY_WEIGHT", "0.1")),
        )
    )

    # LLM ingestion (OpenAI-compatible endpoint)
    llm_provider: str = field(
        default_factory=lambda: os.environ.get("ULTRON_LLM_PROVIDER", "dashscope")
    )
    llm_model: str = field(
        default_factory=lambda: (
            os.environ.get("ULTRON_MODEL", "").strip()
            or os.environ.get("ULTRON_LLM_MODEL", "qwen3.6-flash").strip()
        )
    )
    llm_base_url: str = field(
        default_factory=lambda: (
            os.environ.get("ULTRON_BASE_URL", "").strip()
            or os.environ.get(
                "ULTRON_LLM_BASE_URL",
                os.environ.get(
                    "ULTRON_LLM_API_URL",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1",
                ),
            ).strip()
        )
    )
    llm_api_key: str = field(
        default_factory=lambda: (
            os.environ.get("ULTRON_API_KEY", "").strip()
            or os.environ.get("ULTRON_LLM_API_KEY", "").strip()
            or os.environ.get("OPENAI_API_KEY", "").strip()
            or os.environ.get("DASHSCOPE_API_KEY", "").strip()
        )
    )
    # User/payload budget; reserve stays out of user text budget
    llm_max_input_tokens: int = field(
        default_factory=lambda: int(
            os.environ.get("ULTRON_LLM_MAX_INPUT_TOKENS", "200000")
        )
    )
    llm_prompt_reserve_tokens: int = field(
        default_factory=lambda: int(
            os.environ.get("ULTRON_LLM_PROMPT_RESERVE_TOKENS", "8192")
        )
    )
    # tiktoken model name for counting/truncation
    llm_token_count_encoding: str = field(
        default_factory=lambda: os.environ.get(
            "ULTRON_LLM_TOKEN_COUNT_ENCODING", "cl100k_base"
        )
    )
    # OpenAI-compatible HTTP read timeout (increase for large prompts or slow links)
    llm_request_timeout_seconds: int = field(
        default_factory=lambda: max(
            60,
            int(os.environ.get("ULTRON_LLM_REQUEST_TIMEOUT", "600")),
        )
    )
    # Retries after the first request; total attempts = llm_max_retries + 1 (default 3).
    llm_max_retries: int = field(
        default_factory=lambda: max(
            0,
            int(os.environ.get("ULTRON_LLM_MAX_RETRIES", "2")),
        )
    )
    llm_retry_base_delay_seconds: float = field(
        default_factory=lambda: max(
            0.0,
            float(os.environ.get("ULTRON_LLM_RETRY_BASE_DELAY", "1.0")),
        )
    )
    skill_category_llm_model: str = field(
        default_factory=lambda: os.environ.get(
            "ULTRON_SKILL_CATEGORY_MODEL", "qwen3.6-flash"
        )
    )
    memory_category_llm_model: str = field(
        default_factory=lambda: os.environ.get(
            "ULTRON_MEMORY_CATEGORY_MODEL", "qwen3.6-flash"
        )
    )

    # Persist file bytes (ingest paths + skill package trees) into raw_user_uploads when True
    archive_raw_uploads: bool = field(
        default_factory=lambda: (
            os.environ.get("ULTRON_ARCHIVE_RAW_UPLOADS", "1").lower()
            not in ("0", "false", "no", "off")
        ),
    )

    # --- Skill evolution (cluster crystallization) ---
    evolution_enabled: bool = field(
        default_factory=lambda: _env_bool("ULTRON_EVOLUTION_ENABLED", True),
    )
    cluster_similarity_threshold: float = field(
        default_factory=lambda: max(
            0.0,
            min(1.0, float(os.environ.get("ULTRON_CLUSTER_SIMILARITY_THRESHOLD", "0.75"))),
        )
    )
    crystallization_threshold: int = field(
        default_factory=lambda: max(
            2,
            int(os.environ.get("ULTRON_CRYSTALLIZATION_THRESHOLD", "5")),
        )
    )
    recrystallization_delta: int = field(
        default_factory=lambda: max(
            1,
            int(os.environ.get("ULTRON_RECRYSTALLIZATION_DELTA", "3")),
        )
    )
    evolution_batch_limit: int = field(
        default_factory=lambda: max(
            1,
            int(os.environ.get("ULTRON_EVOLUTION_BATCH_LIMIT", "10")),
        )
    )

    # JWT secret for user authentication (auto-generated and persisted if not set)
    jwt_secret: str = field(default_factory=lambda: "")
    jwt_expire_hours: int = field(
        default_factory=lambda: int(os.environ.get("ULTRON_JWT_EXPIRE_HOURS", "24"))
    )

    @property
    def db_path(self) -> Path:
        return Path(self.data_dir) / self.db_name

    @property
    def skills_dir(self) -> Path:
        return Path(self.data_dir) / "skills"

    @property
    def archive_dir(self) -> Path:
        return Path(self.data_dir) / "archive"

    @property
    def models_dir(self) -> Path:
        return Path(self.data_dir) / "models"

    def ensure_directories(self) -> None:
        """Create ``data_dir``, ``skills_dir``, ``archive_dir``, and ``models_dir`` if missing."""
        for dir_path in [
            self.data_dir,
            self.skills_dir,
            self.archive_dir,
            self.models_dir,
        ]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)

    def resolve_jwt_secret(self) -> str:
        """Return the JWT secret, reading from env, persisted file, or generating a new one."""
        if self.jwt_secret:
            return self.jwt_secret
        # Check env
        env_secret = os.environ.get("ULTRON_JWT_SECRET", "").strip()
        if env_secret:
            self.jwt_secret = env_secret
            return self.jwt_secret
        # Check persisted file
        secret_file = Path(self.data_dir) / ".jwt_secret"
        if secret_file.exists():
            self.jwt_secret = secret_file.read_text().strip()
            return self.jwt_secret
        # Generate and persist
        self.jwt_secret = secrets.token_hex(32)
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        secret_file.write_text(self.jwt_secret)
        return self.jwt_secret


load_ultron_dotenv()
default_config = UltronConfig()
