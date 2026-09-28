import unittest

from gitpulse import collect as c
from tests.helpers import ALICE, Repo, lines, sample_repo


class SampleRepoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = sample_repo()
        cls.d = c.analyze(cls.repo.path)

    @classmethod
    def tearDownClass(cls):
        cls.repo.cleanup()

    def test_overview_numbers(self):
        o = self.d["overview"]
        self.assertEqual((o["commits"], o["merges"], o["authors"], o["active_days"]), (6, 1, 2, 5))
        self.assertEqual((o["added"], o["deleted"]), (27, 0))
        self.assertEqual(o["first"]["date"], "2025-01-06")
        self.assertEqual(o["last"]["date"], "2025-01-20")

    def test_authors(self):
        a = {x["name"]: x for x in self.d["authors"]}
        self.assertEqual(a["Alice"]["commits"], 4)
        self.assertEqual(a["Alice"]["added"], 20)
        self.assertEqual(a["Bob"]["commits"], 2)
        self.assertEqual(a["Bob"]["added"], 7)
        self.assertEqual(self.d["authors"][0]["name"], "Alice")

    def test_rename_is_followed(self):
        top = self.d["hot_files_by_touches"][0]
        self.assertEqual((top["path"], top["touches"], top["added"]), ("src/app.py", 3, 13))
        self.assertNotIn("src/main.py", [f["path"] for f in self.d["hot_files_by_touches"]])

    def test_special_file_names(self):
        paths = [f["path"] for f in self.d["hot_files_by_touches"]]
        self.assertIn("docs/中文 說明.md", paths)
        self.assertIn("my file.txt", paths)

    def test_binary_counted_as_touch_without_lines(self):
        f = next(f for f in self.d["hot_files_by_touches"] if f["path"] == "logo.bin")
        self.assertEqual((f["touches"], f["churn"], f["binary"]), (1, 0, True))

    def test_local_time_heatmap(self):
        h = self.d["heatmap"]
        self.assertEqual(h[0][9], 1)    # Mon 09:00
        self.assertEqual(h[1][22], 1)   # Tue 22:30
        self.assertEqual(h[5][10], 1)   # Sat 10:00 +0800 stays 10 (author's local hour)
        self.assertEqual(h[6][23], 1)   # Sun 23:00
        self.assertEqual(h[6][12], 1)
        self.assertEqual(h[0][8], 1)    # merge, Mon 08:00
        self.assertEqual(sum(map(sum, h)), 6)

    def test_weekly(self):
        self.assertEqual([(w["week"], w["commits"]) for w in self.d["weekly"]],
                         [("2025-01-06", 3), ("2025-01-13", 2), ("2025-01-20", 1)])

    def test_directories(self):
        dirs = {d["path"]: d["churn"] for d in self.d["dirs"]}
        self.assertEqual(dirs, {"src": 13, "(root)": 10, "docs": 4})

    def test_languages(self):
        langs = {r["name"]: r["lines"] for r in self.d["languages"]}
        self.assertEqual(langs, {"Python": 13, "Text": 8, "Markdown": 6})

    def test_bus_factor(self):
        rows = {r["path"]: r for r in self.d["bus_factor"]["dirs"]}
        self.assertEqual(rows["src"]["bus_factor"], 1)
        self.assertEqual(rows["src"]["top_author"], "Alice")
        self.assertEqual(rows["(root)"]["bus_factor"], 2)
        self.assertEqual(self.d["bus_factor"]["overall"], 2)

    def test_messages(self):
        m = self.d["messages"]
        self.assertEqual(m["count"], 5)  # merge commit excluded
        self.assertEqual(m["conventional"], 3)
        self.assertEqual(dict(m["types"]), {"feat": 2, "fix": 1})
        self.assertIn(["feat", 2], [list(x) for x in m["first_words"]])
        self.assertAlmostEqual(m["avg_length"], (14 + 9 + 16 + 9 + 13) / 5.0)

    def test_since_until(self):
        d = c.analyze(self.repo.path, since="2025-01-09", until="2025-01-25")
        self.assertEqual(d["overview"]["commits"], 4)
        self.assertEqual(d["overview"]["first"]["date"], "2025-01-11")

    def test_exclude(self):
        d = c.analyze(self.repo.path, excludes=["docs/*", "*.bin"])
        self.assertEqual(d["overview"]["added"], 23)
        self.assertNotIn("docs", [x["path"] for x in d["dirs"]])
        self.assertEqual({x["name"]: x["lines"] for x in d["languages"]}["Markdown"], 2)

    def test_branch(self):
        d = c.analyze(self.repo.path, branch="side")
        self.assertEqual(d["overview"]["commits"], 4)  # 3 shared + side work

    def test_unknown_branch(self):
        with self.assertRaises(c.GitpulseError):
            c.analyze(self.repo.path, branch="nope")


class EdgeCaseTest(unittest.TestCase):
    def test_empty_repo(self):
        r = Repo()
        self.addCleanup(r.cleanup)
        d = c.analyze(r.path)
        self.assertTrue(d["empty"])
        self.assertEqual(d["overview"]["commits"], 0)
        self.assertEqual(d["weekly"], [])

    def test_not_a_repo(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(c.GitpulseError):
                c.analyze(t)

    def test_missing_directory(self):
        with self.assertRaises(c.GitpulseError):
            c.analyze("/nonexistent/definitely/not/here")

    def test_mailmap_merges_identities(self):
        r = Repo()
        self.addCleanup(r.cleanup)
        r.commit("one", "2025-02-03 10:00:00", ("Al", "al@old.example"), files={"a.txt": lines(2)})
        r.commit("two", "2025-02-04 10:00:00", ALICE, files={"b.txt": lines(3)})
        r.write(".mailmap", "Alice <alice@example.com> Al <al@old.example>\n")
        r.commit("three", "2025-02-05 10:00:00", ALICE, files={"c.txt": lines(1)})
        d = c.analyze(r.path)
        self.assertEqual(len(d["authors"]), 1)
        self.assertEqual(d["authors"][0]["name"], "Alice")
        self.assertEqual(d["authors"][0]["commits"], 3)

    def test_shallow_clone_detected(self):
        import subprocess
        import tempfile
        r = Repo()
        self.addCleanup(r.cleanup)
        for i in range(3):
            r.commit("c%d" % i, "2025-03-0%d 10:00:00" % (i + 1), files={"f%d.txt" % i: lines(2)})
        with tempfile.TemporaryDirectory() as t:
            dst = t + "/clone"
            subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + r.path, dst], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            d = c.analyze(dst)
            self.assertTrue(d["shallow"])
            self.assertEqual(d["overview"]["commits"], 1)

    def test_deletions_counted(self):
        r = Repo()
        self.addCleanup(r.cleanup)
        r.commit("a", "2025-04-01 10:00:00", files={"a.txt": lines(10)})
        r.commit("b", "2025-04-02 10:00:00", files={"a.txt": lines(4)})
        d = c.analyze(r.path)
        self.assertEqual((d["overview"]["added"], d["overview"]["deleted"]), (10, 6))
        self.assertEqual(d["hot_files_by_churn"][0]["churn"], 16)

    def test_many_commits_stream(self):
        r = Repo()
        self.addCleanup(r.cleanup)
        for i in range(60):
            r.commit("c%d" % i, "2025-05-%02d 10:00:00" % (i % 28 + 1), files={"f.txt": lines(i + 1)})
        d = c.analyze(r.path)
        self.assertEqual(d["overview"]["commits"], 60)
        self.assertEqual(d["hot_files_by_touches"][0]["touches"], 60)


if __name__ == "__main__":
    unittest.main()
