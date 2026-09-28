import json
import unittest
from html.parser import HTMLParser

from gitpulse import collect as c
from gitpulse import report
from tests.helpers import Repo, sample_repo


class _P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        for k, v in attrs:
            if k in ("src", "href", "action", "data", "poster") and v:
                self.urls.append(v)
            if k == "style" and v and "url(" in v:
                self.urls.append(v)

    def handle_data(self, data):
        self.text.append(data)


class ReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = sample_repo()
        cls.data = c.analyze(cls.repo.path)
        cls.zh = report.render(cls.data, "zh", generated="2026-01-01")
        cls.en = report.render(cls.data, "en", generated="2026-01-01")

    @classmethod
    def tearDownClass(cls):
        cls.repo.cleanup()

    def parse(self, html):
        p = _P()
        p.feed(html)
        p.close()
        return p

    def test_parses_and_has_svgs(self):
        p = self.parse(self.zh)
        self.assertGreaterEqual(p.tags.count("svg"), 8)
        self.assertEqual(p.tags.count("table"), 2)

    def test_no_external_resources(self):
        for html in (self.zh, self.en):
            self.assertEqual(self.parse(html).urls, [])
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)
            self.assertNotIn("@import", html)

    def test_language_switch(self):
        self.assertIn('lang="zh-Hant"', self.zh)
        self.assertIn("每週活動", self.zh)
        self.assertIn('lang="en"', self.en)
        self.assertIn("Weekly activity", self.en)
        self.assertNotIn("每週活動", self.en)

    def test_supports_dark_and_mobile(self):
        self.assertIn("prefers-color-scheme:dark", self.zh)
        self.assertIn("width=device-width", self.zh)
        self.assertNotIn("gradient", self.zh)

    def test_insight_sentences_present(self):
        self.assertIn("2 contributors", self.en)
        self.assertIn("src/app.py", self.en)

    def test_escapes_repo_name(self):
        d = dict(self.data, repo="<b>x</b>&")
        html = report.render(d, "en")
        self.assertNotIn("<b>x</b>", html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;&amp;", html)

    def test_thousands_separator(self):
        d = json.loads(json.dumps(self.data))
        d["overview"]["commits"] = 12345
        self.assertIn("12,345", report.render(d, "en"))

    def test_empty_report(self):
        r = Repo()
        self.addCleanup(r.cleanup)
        html = report.render(c.analyze(r.path), "en")
        self.assertIn("No commits", html)
        self.parse(html)

    def test_shallow_notice(self):
        d = dict(self.data, shallow=True)
        self.assertIn("shallow", report.render(d, "en"))

    def test_bad_language(self):
        with self.assertRaises(ValueError):
            report.render(self.data, "fr")


class HelperTest(unittest.TestCase):
    def test_heat_summary(self):
        grid = [[0] * 24 for _ in range(7)]
        grid[2][22] = 7
        grid[5][3] = 2
        d, h, n, weekend, night = report.heat_summary(grid)
        self.assertEqual((d, h, n), (2, 22, 7))
        self.assertEqual(weekend, 22)
        self.assertEqual(night, 100)

    def test_week_labels(self):
        weeks = ["2025-%02d-01" % (1 + i // 4) for i in range(48)]
        labels = report.week_labels(weeks)
        self.assertLessEqual(len(labels), 7)
        self.assertIn(0, labels)
        self.assertEqual(labels[0], "2025-01")
        self.assertEqual(report.week_labels([]), {})
        self.assertEqual(report.week_labels(["2025-03-10"]), {0: "03-10"})

    def test_language_rows_fold_tail(self):
        langs = [{"name": "L%d" % i, "lines": 100 - i, "files": 1, "percent": 1.0} for i in range(15)]
        rows = report.language_rows(langs, 10)
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[-1]["name"], "Other")
        self.assertEqual(sum(r["lines"] for r in rows), sum(r["lines"] for r in langs))

    def test_pct(self):
        self.assertEqual(report.pct(1, 3), 33)
        self.assertEqual(report.pct(1, 0), 0)


if __name__ == "__main__":
    unittest.main()
