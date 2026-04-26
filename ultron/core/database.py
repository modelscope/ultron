# Copyright (c) ModelScope Contributors. All rights reserved.
from .db_base import _DatabaseBase
from .db_skill import _SkillMixin
from .db_memory import _MemoryMixin
from .db_catalog_skill import _CatalogSkillMixin
from .db_harness import _HarnessMixin
from .db_user import _UserMixin
from .db_cluster import _ClusterMixin
from .db_trajectory import _TrajectoryMixin
from .db_ingestion import _IngestionMixin
from .db_sft_training import _SFTTrainingMixin


class Database(
    _DatabaseBase,
    _SkillMixin,
    _MemoryMixin,
    _CatalogSkillMixin,
    _HarnessMixin,
    _UserMixin,
    _ClusterMixin,
    _IngestionMixin,
    _TrajectoryMixin,
    _SFTTrainingMixin,
):
    """SQLite persistence — composed from domain mixins."""

    def _init_tables(self) -> None:
        super()._init_tables()
        self._ensure_cluster_tables()
        self._ensure_trajectory_tables()
        self._ensure_task_segments_table()
        self._ensure_sft_training_table()
