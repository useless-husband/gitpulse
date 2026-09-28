"""Build scripted git repositories for the tests."""

import os
import subprocess
import tempfile

ALICE = ("Alice", "alice@example.com")
BOB = ("Bob", "bob@example.com")


class Repo:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.realpath(self._tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "commit.gpgsign", "false")

    def cleanup(self):
        self._tmp.cleanup()

    def git(self, *args, env=None, check=True):
        e = dict(os.environ)
        e.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})
        e.update(env or {})
        r = subprocess.run(["git", "-C", self.path, *args], env=e,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if check and r.returncode:
            raise RuntimeError(r.stderr.decode())
        return r.stdout.decode()

    def write(self, name, content, binary=False):
        full = os.path.join(self.path, name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8"})) as f:
            f.write(content)

    def commit(self, msg, when, author=ALICE, tz="+0000", files=None, args=()):
        """Commit everything; ``when`` is 'YYYY-MM-DD HH:MM:SS'."""
        for name, content in (files or {}).items():
            self.write(name, content, isinstance(content, bytes))
        date = "%s %s" % (when, tz)
        env = {"GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1],
               "GIT_COMMITTER_NAME": author[0], "GIT_COMMITTER_EMAIL": author[1],
               "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg, *args, env=env)


def lines(n, prefix="line"):
    return "".join("%s %d\n" % (prefix, i) for i in range(n))


def sample_repo():
    """A deterministic repo exercising the awkward cases.

    Commits (all UTC unless noted):
      1 Alice Mon 2025-01-06 09:00  feat: add core     src/main.py(10) docs/中文 說明.md(4) "my file.txt"(3)
      2 Bob   Tue 2025-01-07 22:30  fix: typo           src/main.py +2 -0 (appends), logo.bin binary
      3 Alice Sat 2025-01-11 10:00 +0800 (author local) feat(ui): rename  rename src/main.py-> src/app.py (+1 line)
      4 Bob   Sun 2025-01-19 23:00  side branch commit
      5 Alice Mon 2025-01-20 08:00  merge of the branch
    """
    r = Repo()
    r.commit("feat: add core", "2025-01-06 09:00:00", ALICE, files={
        "src/main.py": lines(10), "docs/中文 說明.md": lines(4, "說明"), "my file.txt": lines(3)})
    r.commit("fix: typo", "2025-01-07 22:30:00", BOB, files={
        "src/main.py": lines(10) + lines(2, "extra"), "logo.bin": b"\x00\x01\x02\x03" * 10})
    r.git("mv", "src/main.py", "src/app.py")
    r.commit("feat(ui): rename", "2025-01-11 10:00:00", ALICE, tz="+0800", files={
        "src/app.py": lines(10) + lines(2, "extra") + "one more\n"})
    r.git("checkout", "-q", "-b", "side")
    r.commit("side work", "2025-01-19 23:00:00", BOB, files={"side.txt": lines(5)})
    r.git("checkout", "-q", "main")
    r.commit("Update readme", "2025-01-19 12:00:00", ALICE, files={"README.md": lines(2)})
    r.git("merge", "-q", "--no-ff", "side", "-m", "Merge branch 'side'", env={
        "GIT_AUTHOR_NAME": "Alice", "GIT_AUTHOR_EMAIL": "alice@example.com",
        "GIT_COMMITTER_NAME": "Alice", "GIT_COMMITTER_EMAIL": "alice@example.com",
        "GIT_AUTHOR_DATE": "2025-01-20 08:00:00 +0000",
        "GIT_COMMITTER_DATE": "2025-01-20 08:00:00 +0000"})
    return r
