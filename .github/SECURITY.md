# Security Policy

## Supported Versions
| Version | Supported |
|---|---|
| latest (`main`) | yes |

## Reporting a Vulnerability
Please **do not** open a public issue for security vulnerabilities. Instead, report them privately:

- Email **edy.cu@live.com**, or
- Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) (Security → Report a vulnerability).

You'll get an acknowledgment within 48 hours and a resolution timeline after triage. Please give us a reasonable window to patch before public disclosure.

## Scope notes
- The app reads from CoinMarketCap and Qwen with server-side keys only; no key is sent to the browser.
- `follow_link` fetches announcement pages and refuses private addresses and hosts CMC does not list for the coin (SSRF guard). A bypass of that guard is in scope.
