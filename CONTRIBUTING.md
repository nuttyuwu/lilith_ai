# Contributing

Lilith AI is currently a pre-release. Contributions are welcome, but a change
must not weaken the localhost, consent, privacy, persistence, or model-trust
boundaries described in [SECURITY.md](SECURITY.md).

## Development check

Use CPython 3.10–3.12 and install the core requirements in a virtual environment.
The compatibility suite requires no model, GPU, display, or network:

```bash
python -m pip install -r requirements.txt
python tests/test_compat.py
python watch_compile.py --once
python build_static_site.py
```

Keep pull requests focused, explain the behavior being changed, and add a
regression check for platform-sensitive code. Do not include `config.ini`,
`memory.json`, logs, models, virtual environments, or real conversations.

## Creative assets and model material

Do not add artwork, game text, model weights, training data, or other creative
material unless the contribution records its source, copyright owner, exact
license, required attribution, and evidence that redistribution is permitted.
“Found online,” fan-work status, or attribution alone is not permission.

The existing PNG files are not cleared for redistribution; see
[ASSET_LICENSES.md](ASSET_LICENSES.md). Code contributions must not describe
those rights as resolved.

## Security and conduct

Report vulnerabilities privately according to [SECURITY.md](SECURITY.md).
Participation is subject to [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

By contributing, you confirm that you have the right to submit your work under
the repository's applicable license. No contributor license agreement is
currently in place.
