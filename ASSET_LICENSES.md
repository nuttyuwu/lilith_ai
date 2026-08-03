# Asset licensing inventory

## Release status: not cleared for redistribution

No written license or redistribution permission has been verified for the
bundled PNG artwork. The repository's MIT license does **not** cover these
files. Attribution and fan-work status are not substitutes for permission.

Until the entries below are completed with authoritative evidence, do not ship
the PNG files in a public source archive, package, static-site artifact, or
release. Resolve this by obtaining written permission, replacing the files with
original or permissively licensed work, or removing them and documenting a
user-supplied asset workflow.

This is a release-readiness record, not legal advice.

## Inventory (2026-08-03)

| Asset set | Files | Provenance / owner | License and redistribution status |
|---|---|---|---|
| `assets/glass/` | `blinking.png`, `cheeky.png`, `dissapointed.png`, `idle.png`, `sad.png`, `smile.png`, `talking.png`, `thinking.png` | Unverified; no authoritative source or owner record is present in this repository. | **Unknown; not cleared.** No permission document is on file. |
| `assets/room/` | `blinking.png`, `confused.png`, `happy.png`, `idle.png`, `playful.png`, `sad.png`, `sleep.png`, `smile.png`, `thinking_happy.png`, `thinking_sad.png` | Unverified; no authoritative source or owner record is present in this repository. | **Unknown; not cleared.** No permission document is on file. |
| `static/` | `blinking.png`, `cheeky.png`, `dissapointed.png`, `idle.png`, `sad.png`, `smile.png`, `talking.png`, `thinking.png` | Web-serving copies of the `glass` artwork. Runtime-generated `current.png` is ignored and excluded from release/static-build output. Underlying provenance remains unverified. | **Unknown; not cleared.** Duplication does not create new rights. |

The release candidate contains 26 PNG paths. Most `static/` images duplicate
`assets/glass/` so desktop and web code can serve their expected directory
layouts; the duplication is intentional operationally, but the rights issue
applies to every copy.

## Evidence required to clear an entry

For each set, record all of the following:

- authoritative source URL or delivery record;
- creator and current copyright owner;
- exact license name/version or written permission scope;
- required attribution and modification notices;
- whether source distribution, web deployment, and packaged redistribution are
  all allowed; and
- where the maintainer retains the permission evidence.

Do not place private correspondence in the public repository without the
sender's consent; record a reviewable summary and retain the original securely.

## Publication status

CI builds and checks the static preview but neither provider uploads `public/`.
GitLab Pages publication is disabled rather than controlled by an attestation
variable. Re-enabling any artifact or Pages upload requires both the evidence
above and a separate security design for a compatible public API; the bundled
web server is localhost-only.
