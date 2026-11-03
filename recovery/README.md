# Restore Mira after formatting

Branch: https://github.com/nuttyuwu/lilith_ai/tree/mira

## Before formatting

Save C:\Lilith\MIRA RECOVERY PASSWORD.txt somewhere OFF THIS PC (a password manager, phone, or external drive). The password is deliberately NOT committed. Losing it means losing access to encrypted chat history, configuration and tunnel credentials. The repository alone cannot decrypt the backup.

## What is saved

The mira branch contains source, both characters, UI, portraits/animations, tests and examples. Numbered private-state.zip parts contain an AES-256 encrypted backup of ignored project state, SQLite snapshots, audit reports/candidate prompts, tunnel setup and credentials, the top-level launchers/questions, and the startup shortcut. See manifest.json for hashes and exclusions. Credentials and chat history are not published in plain text.

Python virtual environments, the model weights, runtime locks and generated public site are excluded. The model is reproducible from its pinned URL/checksum in docs/model-provenance.md and modules/compat.py. Files unrelated to Lilith elsewhere in C:\Lilith are not part of this project backup.

## Restore

1. Install Git and Python 3.12. Clone into the original path to preserve launcher paths:

   git clone --branch mira https://github.com/nuttyuwu/lilith_ai.git C:\Lilith\lilith-complete-upgraded\lilith_ai

2. In the clone, combine ALL numbered backup parts. In PowerShell:

   py -3.12 -c "from pathlib import Path; import shutil; parts=sorted(Path('recovery').glob('private-state.zip.[0-9][0-9][0-9]')); out=open('private-state.zip','wb'); [shutil.copyfileobj(p.open('rb'),out) for p in parts]; out.close()"

3. Compare SHA256 of private-state.zip with recovery/manifest.json:

   Get-FileHash private-state.zip -Algorithm SHA256

4. Use 7-Zip to extract private-state.zip with the saved password. It uses AES ZIP encryption; Windows Explorer may not support this encryption. Extract OUTSIDE the repository first.
5. Copy extracted project contents into the clone; copy extracted launchers files into C:\Lilith. Copy user-cloudflared contents into your new user profile's .cloudflared folder. Adjust the credentials-file path in .tunnel/config.yml to the NEW user's absolute path. Keep the same configured tunnel hostname.
6. Create venv and install requirements.txt plus requirements-llama.txt (see README for Windows prebuilt wheels). Download the pinned GGUF into models and verify its SHA256. Do not try to use the old venv after reinstalling Windows.
7. Run doctor.py, then C:\Lilith\Launch Lilith.bat. After testing startup successfully, recreate the Windows startup shortcut for the new user/profile rather than blindly using an old shortcut path.

Keep extracted secrets and the recovery password private. The encrypted recovery snapshot is from 2026-11-03; later chats require a new backup.
