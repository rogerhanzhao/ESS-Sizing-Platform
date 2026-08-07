"""The sidebar version must be able to prove a deploy landed.

Owner, 2026-08-06: the version in the left nav "并不会在更新时改变" — it was
`st.caption("v2.1 · …")`, a hard-coded literal. That is worse than showing
nothing: after an upgrade it read "v2.1" whether the upgrade had worked or not,
so an operator checking it was reassured by a string that proved nothing.

Two things are locked here:

- the RELEASE carries a capital V ("V 请大写"), and is read from VERSION rather
  than retyped at a call site;
- the REVISION comes from the build stamp, because .dockerignore excludes .git
  and a runtime git lookup always fails inside the container. If that stamp is
  not plumbed from Dockerfile through compose to calb-serverctl.sh, the sidebar
  silently reads "dev" forever and the defect is back.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from calb_sizing_tool import app_version


def _in_fresh_process(body: str, **env) -> str:
    """Run against a clean import — the accessors are lru_cached for the process."""
    import os

    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(body)],
        capture_output=True, text=True, cwd=os.getcwd(),
        env={**os.environ, **{k: str(v) for k, v in env.items()}},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# The release
# ---------------------------------------------------------------------------

def test_the_release_is_capitalised():
    """Owner asked for an uppercase V, and one place decides it."""
    assert app_version.release_version().startswith("V")
    assert not app_version.release_version().startswith("v")


@pytest.mark.parametrize("raw,expected", [
    ("2.1", "V2.1"),
    ("v2.1", "V2.1"),      # already prefixed -> not doubled
    ("V3.0", "V3.0"),
    ("  2.2  ", "V2.2"),   # whitespace in the file is not a version
])
def test_the_version_file_is_normalised(tmp_path, monkeypatch, raw, expected):
    path = tmp_path / "VERSION"
    path.write_text(raw, encoding="utf-8")
    monkeypatch.setattr(app_version, "_VERSION_FILE", path)
    assert app_version.release_version() == expected


@pytest.mark.parametrize("raw", ["", "   "])
def test_an_empty_version_file_reads_as_unknown(tmp_path, monkeypatch, raw):
    """"V?" over a plausible-looking number: unknown must be distinguishable."""
    path = tmp_path / "VERSION"
    path.write_text(raw, encoding="utf-8")
    monkeypatch.setattr(app_version, "_VERSION_FILE", path)
    assert app_version.release_version() == app_version.UNKNOWN_VERSION


def test_the_repository_ships_a_version_file():
    assert app_version._VERSION_FILE.is_file(), "VERSION is the release's only source"


# ---------------------------------------------------------------------------
# The revision — the half that verifies a deploy
# ---------------------------------------------------------------------------

def test_the_build_stamp_wins_over_git():
    """Inside the container there is no git; the stamp must be authoritative."""
    out = _in_fresh_process(
        "from calb_sizing_tool.app_version import version_label; print(version_label())",
        CALB_BUILD_REV="abc1234", CALB_BUILD_TIME="",
    )
    assert out.endswith("· abc1234")


def test_the_build_time_shows_only_when_recorded():
    with_time = _in_fresh_process(
        "from calb_sizing_tool.app_version import version_detail; print(version_detail())",
        CALB_BUILD_REV="abc1234", CALB_BUILD_TIME="2026-08-06T09:15Z",
    )
    assert with_time.endswith("built 2026-08-06T09:15Z")

    without = _in_fresh_process(
        "from calb_sizing_tool.app_version import version_detail; print(version_detail())",
        CALB_BUILD_REV="abc1234", CALB_BUILD_TIME="",
    )
    assert "built" not in without


def test_a_developer_checkout_falls_back_to_git():
    revision = _in_fresh_process(
        "from calb_sizing_tool.app_version import build_revision; print(build_revision())",
        CALB_BUILD_REV="",
    )
    head = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"],
                          capture_output=True, text=True, check=False).stdout.strip()
    if head:
        assert revision == head
    else:
        assert revision == app_version.UNKNOWN_REVISION


# ---------------------------------------------------------------------------
# The plumbing. Break any link and the sidebar silently says "dev" again.
# ---------------------------------------------------------------------------

def test_the_sidebar_does_not_hard_code_a_version():
    """The original defect, stated as a test.

    Scans STRING LITERALS only, via tokenize. A regex over the raw text also
    matches the comment that explains the defect, and rewording prose to please
    a test is how a test stops meaning what it says.
    """
    import io
    import re
    import tokenize

    source = open("app.py", encoding="utf-8").read()
    assert "version_label()" in source, "the sidebar must ask app_version"

    sidebar_line = source[:source.index("with st.sidebar:")].count("\n") + 1
    offenders = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.STRING and token.start[0] >= sidebar_line:
            if re.search(r"\bv\d+\.\d+", token.string, re.IGNORECASE):
                offenders.append((token.start[0], token.string))
    assert not offenders, (
        f"literal version(s) in the sidebar cannot change on deploy — that is "
        f"the whole defect: {offenders}"
    )


def test_the_dockerfile_bakes_the_stamp_in():
    dockerfile = open("Dockerfile", encoding="utf-8").read()
    for name in ("CALB_BUILD_REV", "CALB_BUILD_BRANCH", "CALB_BUILD_TIME"):
        assert f"ARG {name}" in dockerfile, f"{name} is never declared as a build arg"
        # ...and promoted to ENV, or the app cannot read it at runtime.
        assert name in dockerfile.split("ENV ")[-1], f"{name} is not carried into ENV"

    # After COPY, or every rebuild with a new revision re-runs pip install.
    assert dockerfile.index("COPY . .") < dockerfile.index("ARG CALB_BUILD_REV")


def test_compose_passes_the_stamp_as_a_build_arg():
    # Every stamp serverctl exports must have a build arg to travel through, or
    # it is set on the host and silently never reaches the image.
    for name in ("CALB_BUILD_REV", "CALB_BUILD_BRANCH", "CALB_BUILD_TIME"):
        assert f"        {name}: ${{{name}:-}}" in open(
            "deploy/docker/docker-compose.ubuntu.yml", encoding="utf-8"
        ).read(), f"{name} does not reach the image"


def test_serverctl_fills_the_stamp_from_the_checkout():
    script = open("deploy/docker/calb-serverctl.sh", encoding="utf-8").read()
    assert "export_build_stamp" in script
    assert "rev-parse --short=7 HEAD" in script
    # Exported, or compose substitution never sees it.
    assert "export CALB_BUILD_REV CALB_BUILD_BRANCH CALB_BUILD_TIME" in script
    # Every build goes through compose(), so the stamp must be set there.
    assert script.index("export_build_stamp\n  require_command docker") > 0
    # An image built from a dirty tree must not claim to be that commit.
    assert "+dirty" in script


def test_the_branch_is_carried_so_github_can_be_compared():
    """A revision alone cannot be checked against "the latest on GitHub"."""
    detail = _in_fresh_process(
        "from calb_sizing_tool.app_version import version_detail; print(version_detail())",
        CALB_BUILD_REV="abc1234", CALB_BUILD_BRANCH="release/x", CALB_BUILD_TIME="",
    )
    assert "branch release/x" in detail


def test_every_rebuild_action_ends_in_a_version_check():
    """Owner: "每次升级完，无论任何升级，版本号都要检验".

    Any action that rebuilds the image must verify afterwards — an upgrade that
    silently kept the old container is exactly what this catches.
    """
    script = open("deploy/docker/calb-serverctl.sh", encoding="utf-8").read()
    body = script[script.index('case "$ACTION" in'):]
    for action in ("start)", "restart)", "update)"):
        block = body[body.index(action):]
        block = block[:block.index(";;")]
        assert "compose up -d --build" in block, action
        assert "verify_version" in block, f"{action} rebuilds but never verifies"


def test_the_version_check_reports_unknown_rather_than_agreement():
    """An unreachable origin must never read as "matches GitHub"."""
    script = open("deploy/docker/calb-serverctl.sh", encoding="utf-8").read()
    check = script[script.index("verify_version() {"):]
    check = check[:check.index("\ncompose() {")]
    assert "UNREACHABLE" in check
    assert "origin/${branch}" in check, "the comparison must be branch-scoped"
    # The running image is a separate claim from the checkout, and is the one a
    # failed build leaves stale.
    assert "running app" in check and "MISMATCH" in check


# ---------------------------------------------------------------------------
# Re-review 2026-08-06: three defects found in the first cut of this feature
# ---------------------------------------------------------------------------

def test_the_dirty_marker_is_never_clipped():
    """It was: "5db9aca+dirty" came out as "5db9aca+dirt".

    A truncated warning reads as a typo, and a warning that looks like a typo
    stops being a warning — an operator would shrug at it rather than notice the
    image does not match any commit.
    """
    label = _in_fresh_process(
        "from calb_sizing_tool.app_version import version_label; print(version_label())",
        CALB_BUILD_REV="5db9aca+dirty", CALB_BUILD_TIME="",
    )
    assert label.endswith("5db9aca+dirty")


def test_a_hostile_build_arg_cannot_flood_the_sidebar():
    """The truncation still has to bound what a build arg can print."""
    label = _in_fresh_process(
        "from calb_sizing_tool.app_version import build_revision; print(build_revision())",
        CALB_BUILD_REV="x" * 500, CALB_BUILD_TIME="",
    )
    assert len(label) == app_version._MAX_REVISION_CHARS


def test_the_revision_is_not_frozen_for_the_process():
    """The original defect in miniature, and the reason not to cache.

    Streamlit keeps this module imported across reruns, so a cached revision
    would show the commit the process started on for as long as it lives — on a
    developer machine, `git pull` would change the code and not the version.
    """
    import inspect

    for name in ("build_revision", "build_branch", "release_version"):
        func = getattr(app_version, name)
        assert not hasattr(func, "cache_clear"), (
            f"{name} must not be cached — it has an on-disk source that changes "
            f"under a running process"
        )
        # And it must genuinely re-read, not just be uncached by accident.
        assert "lru_cache" not in inspect.getsource(func)


def test_the_release_follows_the_file_within_one_process():
    """Bumping VERSION must change what the page says, without a restart."""
    import pathlib
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "VERSION"
        original = app_version._VERSION_FILE
        try:
            app_version._VERSION_FILE = path
            path.write_text("2.1", encoding="utf-8")
            assert app_version.release_version() == "V2.1"
            path.write_text("2.2", encoding="utf-8")
            assert app_version.release_version() == "V2.2", "stale after a bump"
        finally:
            app_version._VERSION_FILE = original


def test_the_github_comparison_cannot_stop_on_a_credential_prompt():
    """origin is https; without credentials git asks for a username.

    This check runs at the end of every start/restart/update, normally over an
    interactive ssh — a deploy must not stop on a prompt unrelated to deploying.
    """
    script = open("deploy/docker/calb-serverctl.sh", encoding="utf-8").read()
    check = script[script.index("verify_version() {"):]
    check = check[:check.index("\ncompose() {")]
    # Comments mention the guard too; the CODE is what has to carry it.
    code = "\n".join(l for l in check.splitlines() if not l.strip().startswith("#"))
    assert "fetch" in code, "the check must consult the remote at all"
    assert "GIT_TERMINAL_PROMPT=0" in code
    assert "GIT_ASKPASS" in code
    # And on the fetch itself, not somewhere else in the function.
    assert 0 < code.index("fetch --quiet") - code.index("GIT_TERMINAL_PROMPT=0") < 200


# ---------------------------------------------------------------------------
# One release number, or the page and the proposal will disagree
# ---------------------------------------------------------------------------

def test_the_report_cannot_drift_from_the_release_file():
    """VERSION and the report brands are two independent sources today.

    Demonstrated: bump VERSION to 2.2 and the sidebar says V2.2 while the report
    cover and file name still say V2.1 — the same "a version that does not track
    the code" defect the owner reported, only in the document a customer keeps.

    The report's identity is NOT derived from VERSION here on purpose: cover
    titles and proposal file names are issued to customers, so changing how they
    are produced is the owner's call, not a refactor. What this test removes is
    the ability to ship the divergence SILENTLY — bump VERSION and this fails
    until the brands are updated with it, or the split is made deliberate.
    """
    from calb_sizing_tool.reporting.brand_profiles import BRAND_PROFILES

    release = app_version.release_version()          # e.g. "V2.1"
    for name, brand in BRAND_PROFILES.items():
        assert brand.version_tag.startswith(release), (
            f"brand {name!r} is tagged {brand.version_tag!r} while VERSION says "
            f"{release!r} — the sidebar and the proposal would disagree"
        )
        assert release in brand.tool_version_label, (
            f"brand {name!r} labels the tool {brand.tool_version_label!r}, "
            f"which does not carry {release!r}"
        )
        assert release in brand.cover_title, (
            f"brand {name!r} covers read {brand.cover_title!r}, "
            f"which does not carry {release!r}"
        )


def test_the_version_is_visible_before_signing_in():
    """The sidebar only exists after login; verifying a deploy must not need one."""
    import inspect

    from calb_sizing_tool.ui import login_view

    assert "version_label()" in inspect.getsource(login_view), (
        "an operator checking whether an upgrade landed should not have to log in"
    )
