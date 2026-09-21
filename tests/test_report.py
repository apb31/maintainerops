import unittest

from maintainerops.report import build_report


class ReportTests(unittest.TestCase):
    def test_empty_activity(self):
        repo = {
            "full_name": "owner/repo",
            "stargazers_count": 10,
            "forks_count": 2,
            "default_branch": "main",
            "archived": False,
        }
        report = build_report(repo, [], [], None, 30)
        self.assertEqual(report["repository"], "owner/repo")
        self.assertEqual(report["stars"], 10)
        self.assertEqual(report["forks"], 2)
        self.assertEqual(report["open_issues"], 0)
        self.assertEqual(report["open_pull_requests"], 0)
        self.assertIsNone(report["latest_release"])


if __name__ == "__main__":
    unittest.main()
