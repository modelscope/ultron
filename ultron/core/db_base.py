# Copyright (c) ModelScope Contributors. All rights reserved.
import sqlite3
from pathlib import Path
from contextlib import contextmanager


class _DatabaseBase:
    """Connection management, schema initialization, and data wipe."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Skill metadata
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL,
                    version TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    published_at INTEGER NOT NULL,
                    parent_version TEXT,
                    status TEXT DEFAULT 'active',
                    name TEXT NOT NULL,
                    description TEXT,
                    categories TEXT,
                    complexity TEXT DEFAULT 'medium',
                    source_type TEXT DEFAULT 'generation',
                    embedding BLOB,
                    local_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(slug, version)
                )
            """)

            # Error learning records
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS error_learning_records (
                    id TEXT PRIMARY KEY,
                    error_type TEXT NOT NULL,
                    error_message_sanitized TEXT,
                    context_sanitized TEXT,
                    debug_process TEXT,
                    solution TEXT,
                    generated_skill_slug TEXT,
                    embedding BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Security learning records
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS security_learning_records (
                    id TEXT PRIMARY KEY,
                    incident_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'medium',
                    summary_sanitized TEXT,
                    context_sanitized TEXT,
                    investigation TEXT,
                    remediation TEXT,
                    data_class TEXT,
                    generated_skill_slug TEXT,
                    embedding BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Skill usage records
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skill_usage_records (
                    id TEXT PRIMARY KEY,
                    skill_slug TEXT NOT NULL,
                    skill_version TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    execution_time REAL,
                    feedback TEXT,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Category table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_skills_slug ON skills(slug)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_skill ON skill_usage_records(skill_slug)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_time ON skill_usage_records(used_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_type ON error_learning_records(error_type)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_security_incident ON security_learning_records(incident_type)"
            )

            # Memory system tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_records (
                    id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    context TEXT,
                    resolution TEXT,
                    tier TEXT DEFAULT 'warm',
                    hit_count INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'active',
                    generated_skill_slug TEXT,
                    tags TEXT,
                    embedding BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_hit_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_contributions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT NOT NULL,
                    content TEXT,
                    context TEXT,
                    resolution TEXT,
                    contributed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contributions_memory ON memory_contributions(memory_id)")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_records(memory_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_tier ON memory_records(tier)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_status ON memory_records(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_hit_count ON memory_records(hit_count)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_last_hit ON memory_records(last_hit_at)")

            # Session extract progress
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_extract_progress (
                    agent_id TEXT NOT NULL,
                    session_file TEXT NOT NULL,
                    last_processed_lines INTEGER DEFAULT 0,
                    last_extract_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (agent_id, session_file)
                )
            """)

            # Raw user uploads
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS catalog_skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    display_name TEXT,
                    path TEXT,
                    description TEXT,
                    description_en TEXT,
                    owner TEXT,
                    category_id TEXT,
                    category_name TEXT,
                    embedding BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_full_name ON catalog_skills(full_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_category ON catalog_skills(category_id)")

            # Raw user uploads
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS raw_user_uploads (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    http_method TEXT DEFAULT '',
                    http_path TEXT DEFAULT '',
                    payload_blob BLOB NOT NULL,
                    meta_json TEXT DEFAULT '{}',
                    payload_size INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_raw_uploads_created ON raw_user_uploads(created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_raw_uploads_source ON raw_user_uploads(source)"
            )

            # User accounts (authentication)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)")

            # Legacy: drop users.display_name (SQLite 3.35+)
            try:
                cursor.execute("PRAGMA table_info(users)")
                user_cols = {row["name"] for row in cursor.fetchall()}
                if "display_name" in user_cols:
                    cursor.execute("ALTER TABLE users DROP COLUMN display_name")
            except sqlite3.OperationalError:
                pass

            # HarnessHub: per-user agent registry and per-(user, agent) workspace profiles
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS harness_agents (
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    display_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_sync_at TIMESTAMP,
                    PRIMARY KEY (user_id, agent_id)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_harness_agents_user ON harness_agents(user_id)"
            )

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS harness_profiles (
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    resources_json TEXT NOT NULL DEFAULT '{}',
                    product TEXT DEFAULT 'nanobot',
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, agent_id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS harness_shares (
                    token TEXT PRIMARY KEY,
                    short_code TEXT UNIQUE,
                    source_user_id TEXT NOT NULL,
                    source_agent_id TEXT NOT NULL,
                    visibility TEXT DEFAULT 'link',
                    snapshot_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_harness_shares_source ON harness_shares(source_user_id, source_agent_id)"
            )

            # Safe column migration: add short_code to existing harness_shares
            try:
                cursor.execute("ALTER TABLE harness_shares ADD COLUMN short_code TEXT")
            except sqlite3.OperationalError:
                pass
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_harness_shares_short_code ON harness_shares(short_code)"
            )

            # Safe column migration
            for col, default in [("summary_l0", "''"), ("overview_l1", "''")]:
                try:
                    cursor.execute(f"ALTER TABLE memory_records ADD COLUMN {col} TEXT DEFAULT {default}")
                except sqlite3.OperationalError:
                    pass

    def wipe_all_data(self) -> dict:
        """Delete all rows from business tables (schema preserved)."""
        deleted: dict = {}
        tables = [
            "harness_shares",
            "harness_profiles",
            "harness_agents",
            "session_extract_progress",
            "memory_contributions",
            "memory_records",
            "skill_usage_records",
            "error_learning_records",
            "security_learning_records",
            "skills",
            "categories",
        ]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for name in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {name}")
                    before = int(cursor.fetchone()[0])
                    cursor.execute(f"DELETE FROM {name}")
                    deleted[name] = {"rows_deleted": before}
                except sqlite3.OperationalError as e:
                    deleted[name] = {"error": str(e)}
        return deleted
