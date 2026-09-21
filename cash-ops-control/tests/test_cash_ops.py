import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cash_ops


class CashOpsTests(unittest.TestCase):
    def test_canonical_dedup(self):
        a = cash_ops.candidate("https://Example.com/job/?utm_source=x&b=2&a=1#top", "A", "", "one")
        b = cash_ops.candidate("http://example.com/job?a=1&b=2", "B", "", "two")
        self.assertEqual(a["url"], "https://example.com/job?a=1&b=2")
        self.assertEqual(a["id"], b["id"])
        c = cash_ops.candidate("https://example.com/job?a=1&b=2", "C", "", "two")
        self.assertEqual(len(cash_ops.merge_items([a], [c])), 1)

    def test_no_false_income_or_qualification(self):
        vague = cash_ops.candidate("https://x.test/1", "Reward up to $1,000", "Apply", "test")
        fixed = cash_ops.candidate("https://x.test/2", "$500 bounty", "Open", "test")
        self.assertIsNone(vague["advertised_payout"])
        self.assertEqual(fixed["advertised_payout"], 500)
        self.assertEqual(fixed["status"], "lead")
        self.assertFalse(fixed["verified"])
        self.assertEqual(fixed["collected"], 0)

    def test_manual_fields_survive_rescan(self):
        old = cash_ops.candidate("https://x.test/a", "Old", "$25 bounty", "test")
        old.update(status="working", verified=True, accepted_payout=25, collected=4, notes="mine")
        fresh = cash_ops.candidate("https://x.test/a", "New", "$30 bounty", "test")
        result = cash_ops.merge_items([old], [fresh])[0]
        self.assertEqual((result["status"], result["accepted_payout"], result["collected"], result["notes"]), ("working", 25, 4, "mine"))
        self.assertEqual(result["advertised_payout"], 30)

    def test_malicious_feed_text_is_data_only(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "owned"
            xml = f"<rss><channel><item><title>$(touch {marker})</title><link>https://x.test/a</link><description>__import__('os').system('touch {marker}')</description></item></channel></rss>"
            rows = cash_ops.parse_rss(xml.encode(), "test")
            self.assertIn("$(touch", rows[0]["title"])
            self.assertFalse(marker.exists())

    def test_token_only_sent_to_exact_github_api_host(self):
        self.assertIn("Authorization", cash_ops.github_headers("https://api.github.com/search/issues", "secret"))
        self.assertEqual(cash_ops.github_headers("https://api.github.com.evil.test/feed", "secret"), {})

    def test_paid_work_is_next_before_unverified_high_score_lead(self):
        lead = cash_ops.candidate("https://x.test/lead", "Large", "$9000 bounty", "test")
        work = cash_ops.candidate("https://x.test/work", "Deliver", "$25 bounty", "test")
        work.update(status="working", verified=True, accepted_payout=25)
        self.assertIn("Deliver", cash_ops.next_action([lead, work]))

    def test_scan_records_source_error_and_writes_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); config = root / "sources.json"; state = root / "state.json"
            config.write_text(json.dumps({"github_searches": [{"name": "bad", "query": "x"}], "rss": []}))
            with patch("cash_ops.request", side_effect=RuntimeError("offline")):
                result = cash_ops.scan(config, state)
            self.assertEqual(result["errors"][0]["source"], "bad")
            self.assertTrue((root / "dashboard.md").exists())
            self.assertEqual(json.loads(state.read_text())["items"], [])


if __name__ == "__main__": unittest.main()
