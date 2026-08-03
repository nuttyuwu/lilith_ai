# Safety

Lilith is fictional AI roleplay for adults (18+). It is not a person, a
sentient being, a therapist, medical advice, or an emergency service. The
character may discuss emotionally intense themes from its source material.
Consent specifically includes fictional parasocial and tulpa themes; these are
never claims that the AI is conscious, inside the user's mind, or dependent on
the user's attention.
Using the app should never replace sleep, medication, professional care, or
contact with people you trust.

## Crisis support

Lilith cannot assess risk, contact help, or keep anyone safe. If you might act
on thoughts of self-harm, have already harmed yourself, or are in immediate
danger, call your local emergency number or go to the nearest emergency
department.

- United States and territories: call or text [988](https://988lifeline.org/).
- Canada: call or text [9-8-8](https://988.ca/).
- Elsewhere: find a verified local service through
  [Find A Helpline](https://findahelpline.com/).

The app uses a small deterministic detector for direct, first-person self-harm
statements. A match bypasses the configured model, translation, and persona
retry and returns the fixed resource message in `modules/safety.py`. Crisis
turns are not stored, so the resource message does not wait for the model,
conversation lock, or writable memory. This is a backstop, not diagnosis or
monitoring: phrasing outside the tested patterns can be missed, and nobody is
alerted.

## Product boundaries

- Setup requires the exact phrase `I AGREE` after the adult, fictional-AI,
  mental-health, backend-sharing, and plaintext-storage disclosure.
- Web chat remains disabled until the browser disclosure is accepted; every
  chat request must carry the current consent-version header.
- Persona-style diagnostics never regenerate replies, so AI identity
  statements, safety refusals, and capability limits cannot be replaced.
- Questions about whether Lilith is real or AI receive a neutral presentation,
  not disappointment or guilt.
- The web service supports loopback access only. Tunnels, LAN exposure, and
  reverse proxies are not supported security boundaries.

See [PRIVACY.md](PRIVACY.md) before entering personal information. To report a
security issue, follow [SECURITY.md](SECURITY.md).
