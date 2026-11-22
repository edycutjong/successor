"""The architecture diagram is served at /architecture (public/) and kept in docs/ for the repo: the two must not drift."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_architecture_is_a_byte_copy_of_docs():
    assert (ROOT / "public" / "architecture.html").read_bytes() == (
        ROOT / "docs" / "architecture.html"
    ).read_bytes()
