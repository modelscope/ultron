# Copyright (c) ModelScope Contributors. All rights reserved.
from .db_base import _DatabaseBase
from .db_skill import _SkillMixin
from .db_memory import _MemoryMixin
from .db_catalog_skill import _CatalogSkillMixin
from .db_harness import _HarnessMixin
from .db_user import _UserMixin
from .db_cluster import _ClusterMixin


class Database(_DatabaseBase, _SkillMixin, _MemoryMixin, _CatalogSkillMixin, _HarnessMixin, _UserMixin, _ClusterMixin):
    """SQLite persistence — composed from domain mixins."""

    def _init_tables(self) -> None:
        super()._init_tables()
        self._ensure_cluster_tables()
