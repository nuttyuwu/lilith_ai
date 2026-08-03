# Security policy

## Supported versions

Lilith AI V0.1A is a pre-release and is not currently cleared for a public
release. Security fixes are made on the current development branch on a
best-effort basis; no older version is presently supported.

## Reporting a vulnerability

Please do not publish credentials, private conversations, exploit steps, or
other sensitive details in a public issue.

1. If GitHub shows **Security → Report a vulnerability** for this repository,
   use that private form.
2. If private reporting is unavailable, open a detail-free issue asking the
   repository owner for a private contact channel.

Before a public release, the maintainer must replace this fallback with a
verified private security contact and publish expected response timelines.

Include the affected revision, platform, impact, reproduction preconditions,
and the smallest safe proof of concept. Remove names, conversation text, API
keys, local paths, and model credentials.

## Current security boundaries

- The bundled web server is loopback-only. It has no accounts and is not safe
  behind a public tunnel or reverse proxy.
- `config.ini`, `memory.json`, and logs may contain secrets or sensitive
  conversations. They are ignored by Git but stored locally without encryption.
- The Hugging Face backend refuses repository-supplied Python code. Optional
  snapshot revisions must be full commit SHAs.
- Model weights and artwork have separate provenance and licensing requirements;
  see [CREDITS.md](CREDITS.md) and [ASSET_LICENSES.md](ASSET_LICENSES.md).

This policy covers the code in this repository. Vulnerabilities in third-party
models, runtimes, or services should also be reported to their maintainers.
