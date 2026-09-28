import unittest

from gitpulse import collect as c

H = "\x01"
F = "\x1f"


def raw(sha, name, email, at, ai, parents, subject, numstat=""):
    return "%s%s" % (H, F.join([sha, name, email, str(at), ai, parents, subject])) + "\0" + numstat


class ParseCommitTest(unittest.TestCase):
    def parse(self, **kw):
        text = raw("a" * 40, "Ann", "Ann@X.com", 1700000000, "2025-03-04 22:15:00 +0800",
                   kw.get("parents", "b" * 40), kw.get("subject", "feat: hi"), kw.get("numstat", ""))
        return c.parse_commit(text[1:])

    def test_header_fields(self):
        cm = self.parse()
        self.assertEqual((cm.name, cm.email, cm.date, cm.hour, cm.tz),
                         ("Ann", "ann@x.com", "2025-03-04", 22, "+0800"))
        self.assertEqual(cm.parents, 1)
        self.assertEqual(cm.subject, "feat: hi")

    def test_no_files(self):
        self.assertEqual(self.parse().files, [])

    def test_merge_parent_count(self):
        self.assertEqual(self.parse(parents="a b").parents, 2)

    def test_root_commit_has_no_parents(self):
        self.assertEqual(self.parse(parents="").parents, 0)

    def test_numstat_plain(self):
        cm = self.parse(numstat="\n3\t1\tsrc/a b.py\0" + "10\t0\t中文.txt\0")
        self.assertEqual([(f.path, f.added, f.deleted) for f in cm.files],
                         [("src/a b.py", 3, 1), ("中文.txt", 10, 0)])

    def test_numstat_binary(self):
        cm = self.parse(numstat="\n-\t-\timg.png\0")
        self.assertTrue(cm.files[0].binary)
        self.assertEqual((cm.files[0].added, cm.files[0].deleted), (0, 0))

    def test_numstat_rename(self):
        cm = self.parse(numstat="\n2\t1\t\0old name.py\0new/name.py\0" + "1\t1\tz\0")
        self.assertEqual(cm.files[0].old_path, "old name.py")
        self.assertEqual(cm.files[0].path, "new/name.py")
        self.assertEqual(cm.files[1].path, "z")

    def test_subject_with_odd_characters(self):
        cm = self.parse(subject="fix: 'quotes' \"and\" <tags> & 中文")
        self.assertEqual(cm.subject, "fix: 'quotes' \"and\" <tags> & 中文")


class StreamTest(unittest.TestCase):
    def data(self):
        parts = []
        for i in range(5):
            parts.append(raw("%040d" % i, "N", "n@x", 1700000000 + i, "2025-01-0%d 10:00:00 +0000" % (i + 1),
                             "p", "msg %d" % i, "\n1\t0\tf%d.txt\0" % i))
        return "".join(parts).encode()

    def test_any_chunk_size_gives_same_result(self):
        data = self.data()
        want = [cm.subject for cm in c.iter_commits([data])]
        self.assertEqual(want, ["msg %d" % i for i in range(5)])
        for size in (1, 2, 7, 50, 1000):
            chunks = [data[i:i + size] for i in range(0, len(data), size)]
            got = [(cm.subject, [f.path for f in cm.files]) for cm in c.iter_commits(chunks)]
            self.assertEqual([g[0] for g in got], want)
            self.assertEqual(got[3][1], ["f3.txt"])

    def test_invalid_utf8_does_not_crash(self):
        data = raw("a" * 40, "N", "n@x", 1, "2025-01-01 10:00:00 +0000", "", "bad").encode() + b"\n1\t1\tx\xff\0"
        cms = list(c.iter_commits([data]))
        self.assertEqual(len(cms), 1)


class BusFactorTest(unittest.TestCase):
    def test_single_author(self):
        self.assertEqual(c.bus_factor({"a": 100}), 1)

    def test_dominant_author(self):
        self.assertEqual(c.bus_factor({"a": 80, "b": 20}), 1)

    def test_just_below_threshold(self):
        self.assertEqual(c.bus_factor({"a": 79, "b": 21}), 2)

    def test_many_equal_authors(self):
        self.assertEqual(c.bus_factor({str(i): 10 for i in range(10)}), 8)

    def test_empty_and_zero(self):
        self.assertEqual(c.bus_factor({}), 0)
        self.assertEqual(c.bus_factor({"a": 0}), 0)


class AggregatorTest(unittest.TestCase):
    def commit(self, sha, files, ts=1, date="2025-01-06", subject="x", email="a@x"):
        return c.Commit(sha, "A", email, ts, date, 9, "+0000", 1, subject, files)

    def test_rename_chain_credits_new_path(self):
        agg = c.Aggregator()
        # newest first: b->c, then a->b, then edit of a
        agg.add(self.commit("3", [c.FileChange("c", 1, 0, False, "b")], ts=3))
        agg.add(self.commit("2", [c.FileChange("b", 1, 0, False, "a")], ts=2))
        agg.add(self.commit("1", [c.FileChange("a", 5, 0)], ts=1))
        self.assertEqual(list(agg.files), ["c"])
        self.assertEqual(agg.files["c"][:3], [3, 7, 0])

    def test_exclude_patterns(self):
        agg = c.Aggregator(["vendor/*", "*.lock"])
        agg.add(self.commit("1", [c.FileChange("vendor/x/y.py", 9, 0), c.FileChange("a.lock", 4, 0),
                                  c.FileChange("keep.py", 2, 1)]))
        self.assertEqual(list(agg.files), ["keep.py"])
        self.assertEqual((agg.added, agg.deleted), (2, 1))
        self.assertEqual(agg.commits, 1)

    def test_weekday_and_week_bucket(self):
        agg = c.Aggregator()
        agg.add(self.commit("1", [], date="2025-01-12"))  # Sunday
        self.assertEqual(agg.heat[6][9], 1)
        self.assertIn("2025-01-06", agg.weeks)

    def test_summarize_weekly_fills_gaps(self):
        agg = c.Aggregator()
        agg.add(self.commit("1", [], date="2025-01-06", ts=1))
        agg.add(self.commit("2", [], date="2025-01-27", ts=2))
        data = c.summarize(agg, {}, [])
        self.assertEqual([w["commits"] for w in data["weekly"]], [1, 0, 0, 1])

    def test_count_languages(self):
        out = b"HEAD:a.py\x0010\nHEAD:b.md\x005\nHEAD:vendor/c.py\x0099\nHEAD:x.unknown\x001\n"
        rows = c.count_languages(out, len("HEAD:"), ["vendor/*"])
        self.assertEqual([(r["name"], r["lines"]) for r in rows],
                         [("Python", 10), ("Markdown", 5), ("Other", 1)])
        self.assertAlmostEqual(sum(r["percent"] for r in rows), 100.0)

    def test_normalize_until(self):
        self.assertEqual(c.normalize_until("2025-06-30"), "2025-06-30 23:59:59")
        self.assertEqual(c.normalize_until("2 weeks ago"), "2 weeks ago")
        self.assertIsNone(c.normalize_until(None))


if __name__ == "__main__":
    unittest.main()
