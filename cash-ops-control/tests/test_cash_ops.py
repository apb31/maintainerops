import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import cash_ops


class CashOpsTests(unittest.TestCase):
    RSS_NOW = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)

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

    def test_rss_buyer_signal_wins_only_without_seller_exclusion(self):
        xml = b"""<rss><channel>
          <item><title>Hiring n8n expert - $500 payout</title><link>https://community.n8n.io/t/hiring/101</link><pubDate>Mon, 21 Sep 2026 12:00:00 +0000</pubDate></item>
          <item><title>For hire: n8n expert looking for projects</title><link>https://community.n8n.io/t/for-hire/102</link><pubDate>Mon, 21 Sep 2026 12:00:00 +0000</pubDate></item>
        </channel></rss>"""
        rules = {"title_buyer_signals": ["hiring", "looking for"], "title_seller_exclusions": ["for hire", "looking for projects"], "max_age_days": 30}
        rows = cash_ops.parse_rss(xml, "n8n", rules, self.RSS_NOW)
        self.assertEqual([row["title"] for row in rows], ["Hiring n8n expert - $500 payout"])
        self.assertEqual(rows[0]["advertised_payout"], 500)
        self.assertFalse(rows[0]["verified"])

    def test_rss_age_rule_rejects_old_and_missing_dates(self):
        xml = b"""<rss><channel>
          <item><title>Hiring old expert</title><link>https://example.test/t/old/1</link><pubDate>Sat, 01 Aug 2026 12:00:00 GMT</pubDate></item>
          <item><title>Hiring undated expert</title><link>https://example.test/t/undated/2</link></item>
          <item><title>Hiring fresh expert</title><link>https://example.test/t/fresh/3</link><pubDate>Mon, 21 Sep 2026 12:00:00 GMT</pubDate></item>
        </channel></rss>"""
        rows = cash_ops.parse_rss(xml, "jobs", {"title_buyer_signals": ["hiring"], "max_age_days": 30}, self.RSS_NOW)
        self.assertEqual([row["title"] for row in rows], ["Hiring fresh expert"])

    def test_atom_timezone_is_normalized_before_age_check(self):
        xml = b"""<feed xmlns='http://www.w3.org/2005/Atom'>
          <entry><title>Seeking stale automation help</title><link href='https://example.test/t/help/8'/>
            <updated>2026-09-22T11:00:00Z</updated><published>2026-08-01T12:00:00Z</published></entry>
          <entry><title>Seeking automation help</title><link href='https://example.test/t/help/9'/>
            <published>2026-09-21T08:00:00-04:00</published></entry>
        </feed>"""
        rows = cash_ops.parse_rss(xml, "jobs", {"title_buyer_signals": ["seeking"], "max_age_days": 1}, self.RSS_NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["published_at"], "2026-09-21T12:00:00+00:00")

    def test_rss_deduplicates_post_links_to_canonical_topic(self):
        xml = b"""<rss><channel>
          <item><title>Need help with n8n</title><link>https://community.n8n.io/t/help/123/2?utm_source=rss</link></item>
          <item><title>Need help with n8n updated</title><link>http://community.n8n.io/t/help/123/5</link></item>
        </channel></rss>"""
        rows = cash_ops.parse_rss(xml, "jobs")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://community.n8n.io/t/help/123")

    def test_rss_item_and_public_summary_limits_are_configurable(self):
        items = "".join(f"<item><title>Job {n}</title><link>https://example.test/jobs/{n}</link><description>{'x' * 40}</description></item>" for n in range(3))
        rows = cash_ops.parse_rss(f"<rss><channel>{items}</channel></rss>".encode(), "jobs", {"max_items": 2, "summary_max_chars": 12})
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["summary"], "x" * 12)

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
