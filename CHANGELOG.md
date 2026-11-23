# Changelog

Generated from Conventional Commits by scripts/release.py.

## v1.1.5 (2026-11-23)

### Bug fixes

- header aligns with the 1360 px content column on wide screens (/about, /judge) (2245a73)

## v1.1.4 (2026-11-22)

### Bug fixes

- a live SWAP on the landing whose old token is above the swap says it is under the 5% margin R8 needs, instead of 'the old token is worth more' beside a lit SWAP (a2a r11) (481d9ec)
- when the old token is above the swap but under R8's 5% margin, the R9 SWAP reason says so (CPOOL read SWAP with the old token 4.8% above the swap and nothing on screen said why it was not SELL OLD) (a2a r11) (adb8475)

## v1.1.3 (2026-11-22)

### Bug fixes

- the deck's version stamp reads /api/health, so it names the live release instead of going stale at every automatic release (it said v1.1.1 after v1.1.2 shipped); static v1.1.2 stays as the fallback (a2a r10) (dd59d9b)
- a timeout or connection reset is a recorded failed sample, not a crash that loses the file; a second capture in the same minute gets a suffix instead of overwriting the first (a2a r10) (0c96e53)

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
