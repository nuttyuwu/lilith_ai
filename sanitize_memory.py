import json, re, shutil
from pathlib import Path

BASE = Path(__file__).parent
MEMORY = BASE / 'memory.json'
BACKUP = BASE / 'memory.json.bak'

assistant_patterns = [
    r"i am a language model",
    r"i am an ai",
    r"i was programmed",
    r"i don't have any personal information",
    r"how can i (help|assist)",
    r"i'?m here to help",
    r"let me know if",
    r"i am here to",
]

if not MEMORY.exists():
    print('memory.json not found')
    exit(1)

shutil.copy2(MEMORY, BACKUP)
print(f'backup written to {BACKUP}')

data = json.loads(MEMORY.read_text(encoding='utf-8'))
conv = data.get('conversation', [])
new_conv = []
removed = 0
for entry in conv:
    if entry.get('role') == 'assistant':
        text = entry.get('content','').lower()
        if any(re.search(pat, text) for pat in assistant_patterns):
            removed += 1
            continue
    new_conv.append(entry)

print(f'removed {removed} assistant entries')

data['conversation'] = new_conv

MEMORY.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
print('memory.json sanitized')
