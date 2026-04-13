# Copyright (c) ModelScope Contributors. All rights reserved.
# Process-wide singletons; tests patch ultron.server_state.ultron.
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ultron import Ultron
    from ultron.services.auth import AuthService
    from ultron.services.harness.showcase import ShowcaseService
    from ultron.services.harness.soul_presets import SoulPresetService

ultron: Optional[Ultron] = None
auth_service: Optional[AuthService] = None
soul_preset_service: Optional[SoulPresetService] = None
showcase_service: Optional[ShowcaseService] = None
