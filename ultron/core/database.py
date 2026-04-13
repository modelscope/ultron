# Copyright (c) ModelScope Contributors. All rights reserved.
from .db_base import _DatabaseBase
from .db_skill import _SkillMixin
from .db_memory import _MemoryMixin
from .db_catalog_skill import _CatalogSkillMixin
from .db_harness import _HarnessMixin
from .db_user import _UserMixin


class Database(_DatabaseBase, _SkillMixin, _MemoryMixin, _CatalogSkillMixin, _HarnessMixin, _UserMixin):
    """SQLite persistence — composed from domain mixins."""
    pass
