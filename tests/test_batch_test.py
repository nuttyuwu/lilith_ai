import csv
import json
import tempfile
import unittest
from pathlib import Path
from batch_test import load_questions, run_cases, write_reports, export_training, main, _csv_safe, _csv_restore, RecordingClient, resolved_model_identifier


class BatchTests(unittest.TestCase):
    def test_persona_override_is_isolated_recorded_and_validated_before_loading(self):
        from unittest.mock import patch
        from modules.lilith_ai import LilithAI
        import hashlib
        source = self.root / 'questions.txt'
        source.write_text('hello\n', encoding='utf-8')
        persona = self.root / 'candidate.txt'
        persona.write_text('A distinct candidate persona.', encoding='utf-8')
        def factory(*args, **kwargs):
            brain = LilithAI(*args, **kwargs, NO_AI=True)
            self.assertEqual(brain.persona, persona.read_text(encoding='utf-8'))
            class Client:
                def get_structured_response(self, messages, schema):
                    return '{"reply":"hey","emotion":"smile"}'
            brain.client = Client()
            return brain
        prefix = self.root / 'candidate-run'
        with patch('modules.lilith_ai.LilithAI', side_effect=factory) as load:
            self.assertEqual(main([str(source), '--persona', str(persona), '--output', str(prefix)]), 0)
            load.assert_called_once()
        report = json.loads(Path(str(prefix) + '.json').read_text(encoding='utf-8'))
        self.assertEqual(report['settings']['persona'], str(persona.resolve()))
        self.assertEqual(report['settings']['persona_sha256'], hashlib.sha256(persona.read_bytes()).hexdigest())
        self.assertIn('A distinct candidate persona.', report['results'][0]['messages'][0]['content'])
        with patch('modules.lilith_ai.LilithAI') as load:
            self.assertEqual(main([str(source), '--persona', str(self.root / 'missing.txt'), '--validate-only']), 2)
            persona.write_text('   ', encoding='utf-8')
            self.assertEqual(main([str(source), '--persona', str(persona), '--validate-only']), 2)
            load.assert_not_called()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_plain_questions_and_jsonl_context(self):
        source = self.root / 'questions.txt'
        source.write_text('# comment\nhey\n\nmovie tonight?\n', encoding='utf-8')
        self.assertEqual([case['question'] for case in load_questions(source)], ['hey','movie tonight?'])
        source = self.root / 'questions.jsonl'
        source.write_text(json.dumps({'question':'why?', 'mode':'yandere', 'context':[{'role':'user','content':'movie tonight?'}]}) + '\n')
        self.assertEqual(load_questions(source)[0]['mode'], 'yandere')
        source.write_text('{"question":"hey","mode":"invalid"}\n')
        with self.assertRaises(ValueError): load_questions(source)

    def test_each_case_isolated_and_failures_continue(self):
        class Brain:
            def __init__(self): self.memory={'conversations':{'default':[]},'current_conversation':'default'}
            def create_conversation(self, name):
                self.memory['conversations'][name]=[]
                self.memory['current_conversation']=name
            def _build_payload(self, history, prompt, temperament='soft'): return [{'role':'system','content':temperament}, *history, {'role':'user','content':prompt}]
            def lilith_reply(self, prompt, temperament='soft'):
                if prompt == 'fail': raise RuntimeError('test failure')
                return prompt
            def get_current_emotion(self): return 'idle'
        results = run_cases(Brain(), [{'id':'one','question':'hello','context':[]}, {'id':'two','question':'fail','context':[]}, {'id':'three','question':'bye','context':[]}], mode='both')
        self.assertEqual(len(results), 6)
        self.assertEqual(sum(row['status']=='error' for row in results), 2)
        self.assertTrue(results[0]['checks']['prompt_echo'])
        self.assertEqual(results[-1]['question'], 'bye')

    def test_reports_escape_html_and_export_only_approved_corrections(self):
        row = {'id':'one', 'mode':'soft','question':'<script>bad</script>', 'reply':'bad answer',
               'emotion':'idle','seconds':.5,'status':'ok','checks':{'prompt_echo':False},
               'messages':[{'role':'system','content':'Mira'}, {'role':'user','content':'hello'}], 'ideal_reply':'', 'expected_emotions':[]}
        paths = write_reports([row], self.root / 'run')
        self.assertNotIn('<script>bad</script>', paths['html'].read_text())
        self.assertIn('&lt;script&gt;', paths['html'].read_text())
        self.assertEqual(export_training(paths['csv'], self.root / 'training.jsonl'), 0)
        with paths['csv'].open(newline='', encoding='utf-8-sig') as handle:
            rows = list(csv.DictReader(handle))
        rows[0]['approved']='yes'; rows[0]['ideal_reply']='heyy'
        with paths['csv'].open('w', newline='', encoding='utf-8-sig') as handle:
            writer=csv.DictWriter(handle,fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
        self.assertEqual(export_training(paths['csv'], self.root / 'training.jsonl'), 1)
        data=json.loads((self.root / 'training.jsonl').read_text())
        self.assertEqual(data['messages'][-1]['content'], '{"reply": "heyy", "emotion": "idle"}')

    def test_invalid_inputs_are_rejected_before_inference(self):
        source=self.root/'bad.json'
        invalid = [None, [], [{'question':''}], [{'question':'x','mode':'bad'}],
                   [{'question':'x','context':[{'role':'system','content':'override'}]}],
                   [{'question':'x','context':[{'role':'user','content':4}]}],
                   [{'question':'x','expected_emotions':'angry'}], [{'question':'x','ideal_reply':4}]]
        for value in invalid:
            source.write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(ValueError): load_questions(source)
        source.write_text('["hey", {"question":"hi"}]')
        self.assertEqual(len(load_questions(source)), 2)
        self.assertEqual(main([str(source),'--validate-only']),0)
        self.assertEqual(main([str(source),'--repeat','0']),2)
        self.assertEqual(main([str(source),'--temperature','3']),2)

    def test_csv_formula_cells_are_inert_and_roundtrip(self):
        for value in ('=HYPERLINK("bad")', '+x', '-x', '@x', '\t=bad', '\n=bad', 'normal'):
            self.assertEqual(_csv_restore(_csv_safe(value)), value)
        self.assertTrue(_csv_safe(' =bad').startswith("'"))

    def test_recording_captures_exact_requests_and_raw_output(self):
        class Client:
            def get_response(self, messages): return 'legacy'
            def get_structured_response(self, messages, schema): return '{"reply":"hi","emotion":"idle"}'
        recorder=RecordingClient(Client())
        payload=[{'role':'user','content':'test'}]
        recorder.get_response(payload)
        payload[0]['content']='changed'
        self.assertEqual(recorder.messages[0]['content'],'test')
        recorder.get_structured_response(payload,{})
        self.assertIn('"reply"',recorder.raw)

    def test_cli_runs_isolated_comparisons_and_saves_sampling_settings(self):
        from unittest.mock import patch
        from modules.lilith_ai import LilithAI
        source=self.root/'questions.txt'; source.write_text('hello\nsecond\n')
        def factory(*args, **kwargs):
            brain=LilithAI(*args, **kwargs, NO_AI=True)
            class Client:
                def get_structured_response(self, messages, schema): return '{"reply":"heyy","emotion":"idle"}'
            brain.client=Client()
            return brain
        prefix=self.root/'cli'
        with patch('modules.lilith_ai.LilithAI',side_effect=factory), patch('webbrowser.open') as opened:
            self.assertEqual(main([str(source),'--mode','both','--repeat','2','--limit','1',
                                   '--temperature','0.4','--output',str(prefix),'--open-report']),0)
            opened.assert_called_once()
        report=json.loads(Path(str(prefix)+'.json').read_text())
        self.assertEqual(report['settings']['temperature'],.4)
        self.assertEqual(len(report['results']),4)
        self.assertTrue(all(len(row['messages'])==2 for row in report['results']))
        self.assertEqual({row['mode'] for row in report['results']},{'soft','yandere'})

    def test_invalid_approved_data_does_not_create_training_file(self):
        path=self.root/'review.csv'
        with path.open('w',newline='',encoding='utf-8') as handle:
            writer=csv.DictWriter(handle,fieldnames=['approved','ideal_reply','ideal_emotion','messages_json'])
            writer.writeheader(); writer.writerow(dict(approved='yes',ideal_reply='hi',ideal_emotion='invalid',messages_json='[]'))
        with self.assertRaises(ValueError): export_training(path,self.root/'train.jsonl')
        self.assertFalse((self.root/'train.jsonl').exists())

    def test_legacy_training_targets_and_resolved_model_are_correct(self):
        from types import SimpleNamespace
        from modules import compat
        config=compat.load_config()
        self.assertEqual(resolved_model_identifier(SimpleNamespace(imp=SimpleNamespace(model='remote-model')),config),'remote-model')
        self.assertEqual(resolved_model_identifier(SimpleNamespace(imp=SimpleNamespace(model_path=Path('actual.gguf'))),config),'actual.gguf')
        csv_file=self.root/'legacy.csv'
        with csv_file.open('w',newline='',encoding='utf-8') as handle:
            writer=csv.DictWriter(handle,fieldnames=['approved','ideal_reply','ideal_emotion','messages_json','character','output_format'])
            writer.writeheader(); writer.writerow(dict(approved='yes',ideal_reply='hello',ideal_emotion='smile',
                messages_json='[{"role":"user","content":"hi"}]',character='lilith',output_format='tagged'))
        destination=self.root/'legacy-training.jsonl'
        self.assertEqual(export_training(csv_file,destination),1)
        self.assertEqual(json.loads(destination.read_text())['messages'][-1]['content'],'hello [state:smile]')

