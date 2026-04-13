# Copyright (c) ModelScope Contributors. All rights reserved.
import os

_DASHBOARD_DIR = os.path.join(os.path.dirname(__file__), "..", "dashboard")
DASHBOARD_DIR = os.path.normpath(_DASHBOARD_DIR)
DASHBOARD_DIST = os.path.join(DASHBOARD_DIR, "dist")
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AGENT_SKILL_PACKAGE_DIR = os.path.join(_REPO_ROOT, "skills", "ultron-1.0.0")
SKILLS_ROOT = os.path.join(_REPO_ROOT, "skills")
