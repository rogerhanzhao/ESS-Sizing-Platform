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

"""What version of this application is running — the ONE place that answers it.

THE DEFECT THIS EXISTS TO FIX (owner, 2026-08-06): the sidebar read
``st.caption("v2.1 · …")`` — a hard-coded literal. It could not change when the
code changed, so it was worse than no version at all: after deploying, it showed
"v2.1" whether the deploy had worked or not, and an operator checking it would
be reassured by a string that proved nothing.

TWO NUMBERS, BECAUSE THEY ANSWER DIFFERENT QUESTIONS
----------------------------------------------------
- ``release_version()`` — "which release is this" — the VERSION file, bumped by
  hand when the release changes. Stable across ordinary deploys, on purpose.
- ``build_revision()`` — "did my deploy actually land" — the commit the image
  was built from. Changes on EVERY deploy, which is the only thing that can
  verify one.

Showing only the first is what made this useless. Showing only the second would
lose the release identity a proposal is issued under.

WHY THE REVISION IS BAKED IN AT BUILD TIME
------------------------------------------
``.dockerignore`` excludes ``.git``, so there is no git metadata inside the
container and a runtime lookup ALWAYS fails on the server. The revision is
therefore passed as a build argument (see docker-compose.ubuntu.yml and
deploy/docker/calb-serverctl.sh) and read back from the environment here. The
git fallback below is for a developer checkout only, where ``.git`` does exist.
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_VERSION_FILE = _PROJECT_ROOT / "VERSION"

#: Shown when the release version cannot be read at all. Deliberately not a
#: plausible-looking number — an operator must be able to tell "unknown" from
#: "2.2" at a glance.
UNKNOWN_VERSION = "V?"
#: Shown when the build revision is unavailable: a developer checkout without
#: git, or an image built before the build argument existed.
UNKNOWN_REVISION = "dev"


def release_version() -> str:
    """The release, ALWAYS with a capital V (owner, 2026-08-06: "V 请大写").

    The VERSION file holds the bare number ("2.2"); the V is applied here so it
    cannot drift between call sites. A file that already carries a v/V prefix is
    normalised rather than doubled.

    Uncached, like the revision: a cached read would keep serving the release a
    long-running process started on, so bumping VERSION and pulling would not
    change what the page says — the very complaint this module answers. One
    small file read per rerun.
    """
    try:
        raw = _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return UNKNOWN_VERSION
    if not raw:
        return UNKNOWN_VERSION
    return "V" + raw.lstrip("vV").strip()


#: Longest revision we will print. A short SHA is 7; the rest of the budget is
#: for the ``+dirty`` marker, which must NEVER be clipped — "5db9aca+dirt" reads
#: as a typo, and a warning that looks like a typo is not a warning.
_MAX_REVISION_CHARS = 24


def build_revision() -> str:
    """The commit this build came from — the part that proves a deploy landed.

    NOT cached. Caching this is how the original defect comes back in miniature:
    on a developer checkout the revision is read from git, and a process that
    cached it would keep showing the commit it started on long after a pull —
    a version number that does not change when the code changes, which is
    exactly what the owner reported. The git call costs ~2 ms and only happens
    where there is no build stamp; in a container the environment answers
    immediately and there is nothing to cache anyway.
    """
    env_rev = os.environ.get("CALB_BUILD_REV", "").strip()
    if env_rev:
        return env_rev[:_MAX_REVISION_CHARS]
    # Developer checkout fallback. Never fires in the container: .dockerignore
    # excludes .git, which is exactly why the build argument exists.
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=5, check=False,
        )
        revision = result.stdout.strip()
        if result.returncode == 0 and revision:
            return revision
    except (OSError, subprocess.SubprocessError):
        pass
    return UNKNOWN_REVISION


def build_branch() -> str:
    """The branch the image was built from. Empty when it was not recorded.

    Uncached for the same reason as ``build_revision``: on a developer checkout
    this comes from git, and switching branches must be reflected.

    "Latest on GitHub" is a per-branch statement, so a revision alone cannot be
    compared against it — a1b2c3d being absent from `main` proves nothing if the
    deploy tracks another branch.
    """
    env_branch = os.environ.get("CALB_BUILD_BRANCH", "").strip()
    if env_branch:
        return env_branch
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=5, check=False,
        )
        branch = result.stdout.strip()
        if result.returncode == 0 and branch and branch != "HEAD":
            return branch
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


@lru_cache(maxsize=1)
def build_time() -> str:
    """When the image was built, UTC. Empty when it was not recorded.

    Safe to cache — unlike the release and the revision this has no on-disk
    source that can change under a running process; it is the environment, which
    is fixed for the life of the container.
    """
    return os.environ.get("CALB_BUILD_TIME", "").strip()


def version_label() -> str:
    """Release and revision together: ``V2.2 · a1b2c3d``.

    This is what the sidebar's last line shows. The revision is what an operator
    watches across an upgrade — compare it with the head commit of
    ``build_branch()`` on GitHub — while the release is what a proposal is
    issued under.
    """
    return f"{release_version()} · {build_revision()}"


def version_detail() -> str:
    """Everything needed to check the running build against GitHub, in one line.

    The sidebar caption stays short; this is its tooltip, and it carries the
    branch, because a revision without one cannot be compared with "the latest
    on GitHub".
    """
    parts = [version_label()]
    branch = build_branch()
    if branch:
        parts.append(f"branch {branch}")
    stamp = build_time()
    if stamp:
        parts.append(f"built {stamp}")
    return " · ".join(parts)


__all__ = [
    "UNKNOWN_REVISION",
    "UNKNOWN_VERSION",
    "build_branch",
    "build_revision",
    "build_time",
    "release_version",
    "version_detail",
    "version_label",
]
