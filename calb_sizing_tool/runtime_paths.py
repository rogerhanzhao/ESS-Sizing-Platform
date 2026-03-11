# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

import os
from pathlib import Path


def get_outputs_dir() -> Path:
    return Path(os.environ.get("CALB_OUTPUTS_DIR", "outputs"))


def ensure_outputs_dir() -> Path:
    outputs_dir = get_outputs_dir()
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return outputs_dir


def get_preferences_file() -> Path:
    return Path(os.environ.get("CALB_PREFERENCES_FILE", "user_preferences.json"))


def ensure_preferences_parent() -> Path:
    preferences_file = get_preferences_file()
    preferences_file.parent.mkdir(parents=True, exist_ok=True)
    return preferences_file
