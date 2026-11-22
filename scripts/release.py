"""Automatic semantic versioning from Conventional Commits (stdlib only; run by the CI release job).

  python scripts/release.py            # compute, then write __version__ + CHANGELOG.md + release-notes.md
  python scripts/release.py --dry-run  # print the next version (or "none") and the reason
  python scripts/release.py --stamp    # write only __version__ (CI stage 3, before `vercel build`: the deployment
                                       # reports the version the release job will tag for this same commit)

Rules, over the commits since the last v*.*.* tag:
  feat -> minor; fix / perf / deps -> patch; "!" after the type or a "BREAKING CHANGE:" footer -> major.
  docs, ci, chore, test, style, refactor, build and any non-conventional subject ("P7: ...") never cause a release.
The single version source is successor/__init__.py; pyproject.toml reads it (dynamic) and /api/health reports it.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "successor" / "__init__.py"
SUBJECT = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?: (?P<desc>.+)$")
BUMP = {"feat": "minor", "fix": "patch", "perf": "patch", "deps": "patch"}
SECTIONS = {"feat": "Features", "fix": "Bug fixes", "perf": "Performance", "deps": "Dependencies"}
RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}
HEADER = "# Changelog\n\nGenerated from Conventional Commits by scripts/release.py.\n\n"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def last_tag() -> str | None:
    try:
        return git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*.[0-9]*.[0-9]*")
    except subprocess.CalledProcessError:
        return None


def classify(subject: str, body: str) -> tuple[str, str, str]:
    """-> (bump level, section type, description); ("none", "", "") when the commit makes no release."""
    m = SUBJECT.match(subject.strip())
    if not m:
        return "none", "", ""
    breaking = bool(m["bang"]) or re.search(r"^BREAKING[ -]CHANGE:", body, re.M) is not None
    level = "major" if breaking else BUMP.get(m["type"], "none")
    if level == "none":
        return "none", "", ""
    return level, m["type"], m["desc"]


def bump(version: str, level: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def commits_since(tag: str | None) -> list[tuple[str, str, str]]:
    rng = f"{tag}..HEAD" if tag else "HEAD"
    raw = git("log", rng, "--format=%h%x1f%s%x1f%b%x1e")
    out = []
    for rec in raw.split("\x1e"):
        if rec.strip():
            sha, subject, body = (rec.strip("\n").split("\x1f") + ["", ""])[:3]
            out.append((sha, subject, body))
    return out


def plan(commits: list[tuple[str, str, str]], current: str) -> tuple[str | None, str]:
    level, entries = "none", []
    for sha, subject, body in commits:
        lv, typ, desc = classify(subject, body)
        if lv == "none":
            continue
        if RANK[lv] > RANK[level]:
            level = lv
        entries.append((typ, desc, sha, lv == "major"))
    if level == "none":
        return None, ""
    new = bump(current, level)
    lines = [f"## v{new} ({dt.date.today().isoformat()})", ""]
    for typ, title in SECTIONS.items():
        rows = [e for e in entries if e[0] == typ]
        if rows:
            lines += (
                [f"### {title}", ""]
                + [f"- {'**BREAKING** ' if e[3] else ''}{e[1]} ({e[2]})" for e in rows]
                + [""]
            )
    breaking_other = [e for e in entries if e[3] and e[0] not in SECTIONS]
    if breaking_other:
        lines += ["### Breaking changes", ""] + [f"- {e[1]} ({e[2]})" for e in breaking_other] + [""]
    return new, "\n".join(lines).rstrip() + "\n"


def changelog(old: str, notes: str) -> str:
    """New CHANGELOG.md text: one header, the new notes, then every earlier release (old header dropped)."""
    k = old.find("\n## v")
    earlier = old[k + 1 :] if k >= 0 else ""
    return HEADER + notes + ("\n" + earlier if earlier else "")


def main() -> int:
    dry = "--dry-run" in sys.argv
    stamp = "--stamp" in sys.argv
    current = re.search(r'__version__ = "(\d+\.\d+\.\d+)"', INIT.read_text())
    assert current, "no __version__ in successor/__init__.py"
    tag = last_tag()
    new, notes = plan(commits_since(tag), current.group(1))
    if not new:
        print(f"no release: no feat/fix/perf/deps/breaking commits since {tag or 'the start'}")
        out = os.environ.get("GITHUB_OUTPUT")
        if out and not dry and not stamp:
            Path(out).open("a").write("released=false\n")
        return 0
    print(f"release v{new} (from {current.group(1)}, since {tag})")
    if dry:
        print(notes)
        return 0
    INIT.write_text(INIT.read_text().replace(f'__version__ = "{current.group(1)}"', f'__version__ = "{new}"'))
    if stamp:
        return 0
    cl = ROOT / "CHANGELOG.md"
    cl.write_text(changelog(cl.read_text() if cl.exists() else "", notes))
    (ROOT / "release-notes.md").write_text(notes.split("\n", 2)[2])
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        Path(out).open("a").write(f"released=true\nversion={new}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
