# Changelog

Generated from Conventional Commits by scripts/release.py.

## v1.1.2 (2026-11-22)

### Bug fixes

- a non-JSON answer is a failed sample (the file is still written), correctness is gated before latency, --confirm re-measures once when only the latency gate fails and keeps both batches; CI uses it (a2a r09) (7345adf)
- hosts come from urlsplit().hostname, so a port or user info no longer becomes part of the host (a2a r09); 0 of the 2026-11-22 notice links change host (aedec1b)
- /api/health refreshes CMC key/info single-flight (concurrent requests on an empty or expired cache shared no lock and each called CMC), one lock per event loop (a2a r09) (166d93a)
- p95 is the nearest-rank percentile (unchanged for the published n=12 and n=6 figures, which are maxima), each sample records server t_ms and its slowest CMC call, files are timestamped so a re-run never overwrites a capture; CI gate takes 20 calls so one slow call alone does not fail Stage 5 (a2a r09) (f04bce5)
- CHANGELOG.md keeps one header (every release repeated the 'Generated from' line), --stamp writes only the version for the deploy stage; v1.0.1 notes list #8-#10, which its tag holds (a2a r09) (5564f23)
- a link counts as CMC only on coinmarketcap.com or a subdomain, not any host ending in it (a2a r09, CodeQL py/incomplete-url-substring-sanitization); 0 of the 91 hosts in the 2026-11-22 notices change class, census figures unchanged (69fe65b)

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
