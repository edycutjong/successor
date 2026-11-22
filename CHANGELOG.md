# Changelog

Generated from Conventional Commits by scripts/release.py.

## v1.1.1 (2026-11-22)

### Bug fixes

- QA round 2: orange only where something lit, quieter headline, stepped rail on slide 5 (0a41a58)

## v1.1.0 (2026-11-22)

### Features

- serve the architecture diagram at /architecture (eb602a0)
- landing /about and deck /pitch rebuilt in the struck-cathode world (d3049f0)

### Bug fixes

- headline lights with the tube; honest captions for a failed Reader; QA round 1 (bea3676)

## v1.0.1 (2026-11-22)

### Dependencies

- update uvicorn requirement from >=0.32 to >=0.54.0 (#11) (d1f7b08)
- update pydantic requirement from <3,>=2 to >=2.14.4,<3 (#12) (fd1826a)
- update pip-audit requirement from >=2.7 to >=2.10.1 (#10) (c8b4998)
- update ruff requirement from >=0.7 to >=0.17.6 (#9) (dfe4522)
- update playwright requirement from >=1.47 to >=1.65.2 (#8) (62de5f1)

(#8, #9 and #10 are inside the v1.0.1 tag but were missing from its generated notes: the release job then rebased onto main after deciding the version. It now releases only the commit the pipeline tested.)
