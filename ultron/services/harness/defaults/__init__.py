# Copyright (c) ModelScope Contributors. All rights reserved.
"""Load default workspace templates for each product."""

import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

_DEFAULTS_DIR = Path(__file__).parent


def get_defaults(product: str) -> Dict[str, str]:
    """Read all files under defaults/{product}/ and return {rel_path: content}.

    Returns an empty dict if the product directory doesn't exist or is empty.
    """
    product_dir = _DEFAULTS_DIR / product
    if not product_dir.is_dir():
        return {}
    result: Dict[str, str] = {}
    for f in sorted(product_dir.rglob("*")):
        if not f.is_file():
            continue
        try:
            rel = str(f.relative_to(product_dir))
            result[rel] = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.debug("Skip default file %s: %s", f, e)
    return result
