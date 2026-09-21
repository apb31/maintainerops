import csv
import io
import unittest

from maintainerops.formatters import CSV_FIELDS, report_to_csv


class CsvFormatterTests(unittest.TestCase):
    def test_csv_contains_stable_header_and_values(self):
        report = {
            "repository": "owner/repo",
            "stars": 10,
            "forks": 2,
            "open_issues": 3,
            "open_pull_requests": 4,
            "stale_issues": 1,
            "stale_pull_requests": 2,
            "latest_release": "v0.1.0",
            "latest_release_age_days": 5,
            "default_branch": "main",
            "archived": False,
        }

        rendered = report_to_csv(report)
        rows = list(csv.DictReader(io.StringIO(rendered)))

        self.assertEqual(len(rows), 1)
        self.assertEqual(list(rows[0].keys()), CSV_FIELDS)
        self.assertEqual(rows[0]["repository"], "owner/repo")
        self.assertEqual(rows[0]["stars"], "10")
        self.assertEqual(rows[0]["latest_release"], "v0.1.0")


if __name__ == "__main__":
    unittest.main()
