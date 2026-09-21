import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cash_ops as ops


class QueueTests(unittest.TestCase):
    at = datetime(2026, 9, 21, 20, tzinfo=timezone.utc)

    def item(self, suffix, **fields):
        row = ops.candidate('https://github.com/example/work/issues/' + str(suffix), 'Task', '$50 bounty', 'test')
        row.update(fields)
        return row

    def test_priority_closed_active_and_fairness(self):
        items = [self.item(1, status='working', verified=True, accepted_payout=50, open=False)]
        items += [self.item(n, status='submitted', open=False) for n in range(2, 9)]
        items += [self.item(10), self.item(11, status='blocked'), self.item(12, open=False)]
        queue, _ = ops.build_queue({'items': items}, self.at)
        self.assertLessEqual(len(queue['jobs']), 5)
        self.assertEqual(queue['jobs'][0]['kind'], 'accepted-work')
        self.assertIn('verify', [j['kind'] for j in queue['jobs']])
        self.assertFalse({items[-1]['id'], items[-2]['id']} & {j['item_id'] for j in queue['jobs']})

    def test_manual_execution_survives_refresh_and_comments_change_fingerprint(self):
        old = self.item(1, application_submitted=True, execution={'checkpoint': {'summary': 'saved'}, 'parked': True})
        fresh = self.item(1, source_comments=2)
        merged = ops.merge_items([old], [fresh])[0]
        self.assertEqual(merged['execution'], old['execution'])
        self.assertTrue(merged['application_submitted'])
        self.assertNotEqual(ops.source_fingerprint(old), ops.source_fingerprint(merged))

    def test_lease_prevents_duplicate_then_expires(self):
        with tempfile.TemporaryDirectory() as folder:
            state, queue = Path(folder) / 'state.json', Path(folder) / 'queue.json'
            item = self.item(1)
            ops.atomic_json(state, {'items': [item]})
            job = ops.build_queue({'items': [item]}, self.at)[0]['jobs'][0]['id']
            ops.claim_job(job, 'worker-a', 10, state, queue, self.at)
            with self.assertRaises(RuntimeError):
                ops.claim_job(job, 'worker-b', 10, state, queue, self.at)
            with self.assertRaises(RuntimeError):
                ops.record_job(job, 'done', owner='worker-b', state_path=state, queue_path=queue, at=self.at)
            after = ops.build_queue(json.loads(state.read_text()), self.at + timedelta(minutes=11))[0]
            self.assertEqual(after['jobs'][0]['id'], job)

    def test_completed_verification_transitions_to_application(self):
        row = self.item(1, status='qualified', verified=True)
        row['execution'] = {'completed_fingerprint': ops.source_fingerprint(row), 'completed_kind': 'verify', 'completed_status': 'lead'}
        queue, _ = ops.build_queue({'items': [row]}, self.at)
        self.assertEqual(queue['jobs'][0]['kind'], 'application')

    def test_submitted_cooldown_then_recheck_and_parked_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            state, queue = Path(folder) / 'state.json', Path(folder) / 'queue.json'
            row = self.item(1, status='submitted')
            ops.atomic_json(state, {'items': [row]})
            job = ops.build_queue({'items': [row]}, self.at)[0]['jobs'][0]['id']
            ops.claim_job(job, 'worker', state_path=state, queue_path=queue, at=self.at)
            ops.record_job(job, 'done', owner='worker', state_path=state, queue_path=queue, at=self.at)
            saved = json.loads(state.read_text())
            self.assertEqual(ops.build_queue(copy.deepcopy(saved), self.at + timedelta(hours=1))[0]['jobs'], [])
            self.assertEqual(len(ops.build_queue(saved, self.at + timedelta(hours=73))[0]['jobs']), 1)
            later = self.at + timedelta(hours=73)
            ops.claim_job(job, 'worker', state_path=state, queue_path=queue, at=later)
            ops.record_job(job, 'rejected', owner='worker', state_path=state, queue_path=queue, at=later)
            self.assertEqual(ops.build_queue(json.loads(state.read_text()), later + timedelta(days=30))[0]['jobs'], [])

    def test_changed_source_releases_claim_without_false_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            state, queue = Path(folder) / 'state.json', Path(folder) / 'queue.json'
            row = self.item(1)
            ops.atomic_json(state, {'items': [row]})
            job = ops.build_queue({'items': [row]}, self.at)[0]['jobs'][0]['id']
            ops.claim_job(job, 'worker', state_path=state, queue_path=queue, at=self.at)
            saved = json.loads(state.read_text())
            saved['items'][0]['source_comments'] = 3
            ops.atomic_json(state, saved)
            with self.assertRaises(RuntimeError):
                ops.record_job(job, 'done', owner='worker', state_path=state, queue_path=queue, at=self.at)
            execution = json.loads(state.read_text())['items'][0]['execution']
            self.assertNotIn('completed_fingerprint', execution)
            self.assertNotIn('lease', execution)


if __name__ == '__main__':
    unittest.main()
