import csv
import json
import tempfile
import unittest
from pathlib import Path
from batch_test import load_questions, run_cases, write_reports, export_training


class BatchTests(unittest.TestCase):
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

