"""Batch-test Lilith/Mira with disposable history and editable review reports."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
from datetime import datetime
import html
import json
from pathlib import Path
import re
import tempfile
import time

ROOT = Path(__file__).resolve().parent
MODES = ('soft', 'yandere')


def resolved_model_identifier(client, config):
    implementation = getattr(client, 'imp', client)
    model_id = getattr(implementation, 'model_id', None)
    if isinstance(model_id, str):
        return model_id
    path = getattr(implementation, 'model_path', None)
    if isinstance(path, (str, Path)):
        return str(path)
    for attribute in ('model_name', 'model'):
        value = getattr(implementation, attribute, None)
        if isinstance(value, str):
            return value
    return config['ai_config'].get('ai_model', '')


def load_questions(path):
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError('Question file is too large (maximum 2 MB)')
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() == '.json':
        items = json.loads(text)
        if not isinstance(items, list):
            raise ValueError('JSON input must be an array of questions')
    else:
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        items = [json.loads(line) for line in lines] if path.suffix.lower() == '.jsonl' else lines
    cases = []
    for number, item in enumerate(items, 1):
        case = {'question': item} if isinstance(item, str) else deepcopy(item)
        if not isinstance(case, dict):
            raise ValueError(f'Question {number}: expected text or an object')
        question = case.get('question')
        if not isinstance(question, str) or not question.strip() or len(question) > 8000:
            raise ValueError(f'Question {number}: nonempty question text required (maximum 8000 characters)')
        if case.get('mode', 'soft') not in MODES:
            raise ValueError(f'Question {number}: choose soft or yandere')
        context = case.get('context', [])
        if not isinstance(context, list) or len(context) > 40:
            raise ValueError(f'Question {number}: context must contain at most 40 turns')
        for turn in context:
            if (not isinstance(turn, dict) or turn.get('role') not in ('user', 'assistant')
                    or not isinstance(turn.get('content'), str) or len(turn['content']) > 8000):
                raise ValueError(f'Question {number}: invalid context turn')
        expected = case.get('expected_emotions', [])
        if not isinstance(expected, list) or not all(isinstance(value, str) for value in expected):
            raise ValueError(f'Question {number}: expected_emotions must be a list of names')
        if not isinstance(case.get('ideal_reply', ''), str):
            raise ValueError(f'Question {number}: ideal_reply must be text')
        cases.append(dict(case, id=str(case.get('id', number)), question=question.strip(), context=context, expected_emotions=expected))
    if not cases:
        raise ValueError('No questions found')
    return cases


class RecordingClient:
    def __init__(self, client):
        self.client, self.messages, self.raw = client, [], ''

    def __getattr__(self, name):
        return getattr(self.client, name)

    def get_response(self, messages):
        self.messages = deepcopy(messages)
        self.raw = self.client.get_response(messages)
        return self.raw

    def get_structured_response(self, messages, schema):
        self.messages = deepcopy(messages)
        method = getattr(self.client, 'get_structured_response', None)
        self.raw = method(messages, schema) if method else self.client.get_response(messages)
        return self.raw


def run_cases(brain, cases, mode=None, repeat=1, on_result=None):
    results = []
    for case in cases:
        modes = MODES if mode == 'both' else (mode or case.get('mode', 'soft'),)
        for selected in modes:
            for repetition in range(1, repeat + 1):
                brain.create_conversation(f'batch-{len(results) + 1}')
                room = brain.memory['current_conversation']
                history = deepcopy(case.get('context', []))
                brain.memory['conversations'][room] = deepcopy(history)
                client = getattr(brain, 'client', None)
                if isinstance(client, RecordingClient):
                    client.messages, client.raw = [], ''
                row = dict(id=str(case['id']), mode=selected, repetition=repetition,
                           character=getattr(brain, 'character_name', 'Mira').lower(),
                           output_format='json' if getattr(brain, 'structured_replies', True) else 'tagged',
                           question=case['question'], expected_emotions=case.get('expected_emotions', []),
                           ideal_reply=case.get('ideal_reply', ''), reply='', emotion='', status='ok', error='', checks={})
                started = time.perf_counter()
                try:
                    row['reply'] = brain.lilith_reply(case['question'], temperament=selected)
                    row['emotion'] = brain.get_current_emotion()
                    normalize = lambda value: re.sub(r'\s+', ' ', value.strip().lower())
                    row['checks'] = {
                        'prompt_echo': normalize(row['reply']) == normalize(case['question']),
                        'punctuation_spam': bool(re.search(r'[!?]{4,}', row['reply'])),
                        'emotion_mismatch': bool(row['expected_emotions'] and row['emotion'] not in row['expected_emotions']),
                        'empty_reply': not bool(row['reply'].strip()),
                    }
                except Exception as exc:
                    row['status'], row['error'] = 'error', f'{type(exc).__name__}: {exc}'
                row['seconds'] = round(time.perf_counter() - started, 3)
                row['raw_reply'] = client.raw if isinstance(client, RecordingClient) else ''
                if isinstance(client, RecordingClient) and client.messages:
                    row['messages'] = deepcopy(client.messages)
                else:
                    # Fixed runtime replies do not call the backend. Reconstruct
                    # their request for review; generated turns use the recording.
                    row['messages'] = brain._build_payload(history, case['question'], temperament=selected)
                results.append(row)
                if on_result:
                    on_result(results)
    return results


def _csv_safe(value):
    value = str(value)
    dangerous = value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r'))
    return "'" + value if dangerous else value


def _csv_restore(value):
    return value[1:] if len(value) > 1 and value[0] == "'" and _csv_safe(value[1:]).startswith("'") else value


def write_reports(results, prefix, settings=None):
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    paths = {kind: Path(str(prefix) + '.' + kind) for kind in ('json', 'csv', 'html')}
    paths['json'].write_text(json.dumps({'settings':settings or {}, 'results':results}, ensure_ascii=False, indent=2), encoding='utf-8')
    fields = ['id','character','output_format','mode','repetition','question','reply','emotion','seconds','status','flags','error',
              'rating','ideal_reply','ideal_emotion','approved','messages_json']
    with paths['csv'].open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in results:
            review = {field:row.get(field, '') for field in fields}
            review.update(flags=', '.join(key for key, value in row['checks'].items() if value),
                          character=row.get('character', 'mira'), output_format=row.get('output_format', 'json'),
                          rating='', approved='', ideal_emotion=row.get('emotion', 'idle'),
                          messages_json=json.dumps(row['messages'], ensure_ascii=False))
            writer.writerow({key:_csv_safe(value) for key,value in review.items()})
    headings = ('Question', 'Mode', 'Reply', 'Emotion', 'Seconds', 'Flags / error')
    rows = []
    for row in results:
        flags = ', '.join(key for key,value in row['checks'].items() if value) or 'No automatic flags'
        values = [row['question'], row['mode'], row['reply'], row['emotion'], row['seconds'], row.get('error') or flags]
        rows.append('<tr>' + ''.join('<td>' + html.escape(str(value)) + '</td>' for value in values) + '</tr>')
    document = '<!doctype html><meta charset="utf-8"><title>Mira batch review</title><style>body{font:16px system-ui;margin:24px;background:#15111d;color:#eee}table{border-collapse:collapse;width:100%}th,td{border:1px solid #574663;padding:12px;text-align:left;vertical-align:top;white-space:pre-wrap}th{background:#30253d}</style><h1>Batch response review</h1><p>Automatic flags are diagnostics, not a personality-quality score. Rate and correct replies in the CSV after the run finishes. Personal chat history is unchanged.</p><table><tr>'
    document += ''.join('<th>' + heading + '</th>' for heading in headings) + '</tr>' + ''.join(rows) + '</table>'
    paths['html'].write_text(document, encoding='utf-8')
    return paths


def export_training(csv_path, destination):
    from modules.lilith_ai import VALID_STATES
    samples = []
    with Path(csv_path).open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            if row.get('approved', '').strip().lower() not in ('yes','true','1','y'):
                continue
            reply = _csv_restore(row.get('ideal_reply', '')).strip()
            emotion = row.get('ideal_emotion', '').strip()
            character = row.get('character')
            output_format = row.get('output_format')
            if character not in ('mira', 'lilith') or output_format not in ('json', 'tagged'):
                raise ValueError('Training export requires character/output_format metadata; regenerate this report')
            valid = set(VALID_STATES) | ({'angry', 'blushing', 'sad_confused'} if character == 'mira' else set())
            if not reply or emotion not in valid:
                raise ValueError('Approved rows need an ideal_reply and valid ideal_emotion')
            messages = json.loads(row['messages_json'])
            if (not isinstance(messages, list) or not messages
                    or not all(isinstance(message, dict) and message.get('role') in ('system','user','assistant')
                               and isinstance(message.get('content'), str) for message in messages)
                    or messages[-1]['role'] != 'user'):
                raise ValueError('Approved row has invalid request messages')
            target = json.dumps({'reply':reply, 'emotion':emotion}, ensure_ascii=False) if output_format == 'json' else f'{reply} [state:{emotion}]'
            messages.append({'role':'assistant', 'content':target})
            samples.append({'messages':messages})
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(''.join(json.dumps(sample, ensure_ascii=False) + '\n' for sample in samples), encoding='utf-8')
    return len(samples)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('questions', nargs='?', default=str(ROOT.parent.parent / 'Mira Questions.txt'))
    parser.add_argument('--mode', choices=(*MODES, 'both'), help='override modes in input; both compares every question')
    parser.add_argument('--character', choices=('mira','lilith'), default='mira')
    parser.add_argument('--temperature', type=float, help='default: actual configured temperature')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--output', help='report filename prefix, without extension')
    parser.add_argument('--use-gpu', action='store_true', help='use configured GPU layers instead of CPU isolation')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--open-report', action='store_true', help='open the completed HTML review in your browser')
    parser.add_argument('--export-training', metavar='REVIEW_CSV')
    parser.add_argument('--training-output', default=str(ROOT / 'audit' / 'mira-approved-training.jsonl'))
    args = parser.parse_args(argv)
    try:
        if args.export_training:
            count = export_training(args.export_training, args.training_output)
            print(f'Exported {count} approved corrections to {args.training_output}')
            return 0
        if not 1 <= args.repeat <= 20 or (args.limit is not None and args.limit < 1):
            raise ValueError('repeat must be 1–20; limit must be positive')
        if args.temperature is not None and not 0 <= args.temperature <= 2:
            raise ValueError('temperature must be between 0 and 2')
        cases = load_questions(args.questions)
        if args.limit:
            cases = cases[:args.limit]
        if args.validate_only:
            print(f'{len(cases)} valid questions; model not loaded')
            return 0
        from modules import compat
        from modules.lilith_ai import LilithAI
        from modules.personalities import profile_config
        config = compat.load_config()
        if args.temperature is not None:
            config['ai_config']['temperature'] = str(args.temperature)
        if not args.use_gpu:
            config['ai_config']['n_gpu_layers'] = '0'
            config['ai_config']['n_threads'] = '4'
        settings = {'character':args.character, 'temperature':config['ai_config'].getfloat('temperature'),
                    'backend':config['server'].get('server_ai'),
                    'max_tokens':config['ai_config'].getint('max_tokens'), 'repeat':args.repeat,
                    'cpu_override_requested':not args.use_gpu}
        prefix = Path(args.output) if args.output else ROOT / 'audit' / 'batch-runs' / datetime.now().strftime('run-%Y%m%d-%H%M%S-%f')
        print(f'Testing {len(cases)} questions; temperature={settings["temperature"]}; history is disposable', flush=True)
        def progress(results):
            row = results[-1]
            flags = ', '.join(key for key,value in row['checks'].items() if value)
            print(f'{len(results)}. {row["id"]} / {row["mode"]}: {row["status"]} {row["seconds"]}s' + (f' [{flags}]' if flags else ''), flush=True)
            write_reports(results, prefix, settings)
        with tempfile.TemporaryDirectory() as folder:
            config['ai_config']['memory'] = str(Path(folder) / 'batch.json')
            brain = LilithAI(config=profile_config(config, args.character))
            brain.set_user_name('Khongor')
            settings['model'] = resolved_model_identifier(brain.client, config)
            brain.client = RecordingClient(brain.client)
            results = run_cases(brain, cases, mode=args.mode, repeat=args.repeat, on_result=progress)
        print(f'Review: {prefix}.html\nCorrections: {prefix}.csv\nRaw data: {prefix}.json')
        if args.open_report:
            import webbrowser
            webbrowser.open(Path(str(prefix) + '.html').resolve().as_uri())
        return 1 if any(row['status'] == 'error' for row in results) else 0
    except KeyboardInterrupt:
        print('Stopped. Reports from completed questions are preserved.')
        return 130
    except (OSError, ValueError, KeyError) as exc:
        print(f'Batch test failed: {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
