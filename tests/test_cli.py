import contextlib
import io
import json
import os
import tempfile
import unittest

from gitpulse import cli
from tests.helpers import sample_repo


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = sample_repo()

    @classmethod
    def tearDownClass(cls):
        cls.repo.cleanup()

    def test_writes_html(self):
        with tempfile.TemporaryDirectory() as t:
            out = os.path.join(t, "r.html")
            code, _, err = run(self.repo.path, "-o", out)
            self.assertEqual(code, 0)
            self.assertIn("wrote", err)
            with open(out, encoding="utf-8") as f:
                self.assertTrue(f.read().startswith("<!doctype html>"))

    def test_json_to_stdout(self):
        code, out, _ = run(self.repo.path, "--json", "-q")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["overview"]["commits"], 6)

    def test_json_keeps_unicode(self):
        _, out, _ = run(self.repo.path, "--json", "-q")
        self.assertIn("中文 說明.md", out)

    def test_english_flag(self):
        with tempfile.TemporaryDirectory() as t:
            out = os.path.join(t, "r.html")
            run(self.repo.path, "-o", out, "--lang", "en", "-q")
            with open(out, encoding="utf-8") as f:
                self.assertIn("Weekly activity", f.read())

    def test_filters_forwarded(self):
        _, out, _ = run(self.repo.path, "--json", "-q", "--since", "2025-01-09",
                        "--until", "2025-01-25", "--exclude", "*.md")
        d = json.loads(out)
        self.assertEqual(d["overview"]["commits"], 4)
        self.assertEqual(d["excludes"], ["*.md"])

    def test_quiet_has_no_stderr(self):
        _, _, err = run(self.repo.path, "--json", "-q")
        self.assertEqual(err, "")

    def test_error_exit_code(self):
        with tempfile.TemporaryDirectory() as t:
            code, _, err = run(t, "-q")
            self.assertEqual(code, 2)
            self.assertIn("not a git repository", err)

    def test_bad_branch(self):
        code, _, err = run(self.repo.path, "--branch", "zzz", "-q")
        self.assertEqual(code, 2)
        self.assertIn("zzz", err)

    def test_version(self):
        with self.assertRaises(SystemExit) as cm:
            run("--version")
        self.assertEqual(cm.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
