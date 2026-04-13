# Copyright (c) ModelScope Contributors. All rights reserved.
import json
from datetime import datetime, timezone
from typing import Dict

from .allowlist import ClawWorkspaceAllowlist


class HarnessBundle:
    """Packages workspace files into a JSON-serializable bundle for sync and sharing."""

    def __init__(
        self,
        product: str,
        resources: Dict[str, str],
        collected_at: str,
    ):
        self.product = product
        self.resources = resources
        self.collected_at = collected_at

    @classmethod
    def from_workspace(cls, allowlist: ClawWorkspaceAllowlist) -> "HarnessBundle":
        resources = allowlist.collect()
        return cls(
            product=allowlist.product_name,
            resources=resources,
            collected_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_snapshot_json(self) -> str:
        return json.dumps({
            "product": self.product,
            "resources": self.resources,
            "collected_at": self.collected_at,
        }, ensure_ascii=False)

    @classmethod
    def from_snapshot_json(cls, raw: str) -> "HarnessBundle":
        data = json.loads(raw)
        return cls(
            product=data.get("product", ""),
            resources=data.get("resources", {}),
            collected_at=data.get("collected_at", ""),
        )

    def to_resources_json(self) -> str:
        return json.dumps(self.resources, ensure_ascii=False)
