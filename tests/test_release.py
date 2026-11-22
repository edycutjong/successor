"""The automatic-release rules (scripts/release.py): which commits cut a release, and at which level."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "release", Path(__file__).resolve().parents[1] / "scripts" / "release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def level(subject: str, body: str = "") -> str:
    return release.classify(subject, body)[0]


def test_levels():
    assert level("feat: add x") == "minor"
    assert level("feat(ui): add x") == "minor"
    assert level("fix: y") == "patch"
    assert level("perf: y") == "patch"
    assert level("deps: Update httpx") == "patch"
    assert level("feat!: drop v1") == "major"
    assert level("fix: y", "details\n\nBREAKING CHANGE: api shape") == "major"


def test_no_release_types():
    for s in ("docs: x", "ci: x", "chore: x", "test: x", "style: x", "refactor: x", "build: x"):
        assert level(s) == "none"


def test_old_non_conventional_commits_never_release():
    for s in (
        "P7: re-measure cached bench",
        "a2a r08: GAS one click",
        "Update starlette requirement (#6)",
        "Fix: capital",
    ):
        assert level(s) == "none"


def test_bump_and_plan():
    assert release.bump("1.4.2", "major") == "2.0.0"
    assert release.bump("1.4.2", "minor") == "1.5.0"
    assert release.bump("1.4.2", "patch") == "1.4.3"
    new, notes = release.plan(
        [("a1", "docs: x", ""), ("b2", "fix: bug", ""), ("c3", "feat: new", "")], "1.0.0"
    )
    assert new == "1.1.0" and "### Features" in notes and "### Bug fixes" in notes
    assert release.plan([("a1", "docs: x", ""), ("b2", "P7: y", "")], "1.0.0") == (None, "")
    # CHANGELOG.md keeps one header however many releases are prepended
    text = release.changelog("", notes)
    for v in ("1.1.1", "1.2.0"):
        text = release.changelog(text, f"## v{v} (2026-11-23)\n\n### Bug fixes\n\n- y (d4)\n")
    assert text.count("Generated from Conventional Commits") == 1 and text.count("## v") == 3
    assert text.index("## v1.2.0") < text.index("## v1.1.1") < text.index("## v1.1.0")
