"""Run git and stream its history into aggregate statistics.

``git log --numstat -z`` output is parsed incrementally: the raw bytes are
read in chunks, split on a rare marker byte (0x01) into one chunk per commit,
and every commit is folded into an :class:`Aggregator` and then dropped. No
per-commit list is ever kept, so memory stays flat on large repositories.
"""

import datetime as _dt
import fnmatch
import os
import re
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass, field

from .langs import OTHER, language_of

COMMIT_MARK = "\x01"
FIELD_SEP = "\x1f"
LOG_FORMAT = "%x01%H%x1f%aN%x1f%aE%x1f%at%x1f%ai%x1f%P%x1f%s"
ROOT_DIR = "(root)"
BUS_THRESHOLD = 0.8
CHUNK_SIZE = 1 << 20

_CC_RE = re.compile(r"^([A-Za-z]+)(\([^)]*\))?!?:\s")
_WORD_RE = re.compile(r"[^\W_]+")


class GitpulseError(Exception):
    """A user-facing error (bad path, unknown branch, git missing...)."""


@dataclass
class FileChange:
    path: str
    added: int  # 0 for binary files
    deleted: int
    binary: bool = False
    old_path: str = None


@dataclass
class Commit:
    sha: str
    name: str
    email: str
    ts: int
    date: str  # author-local date, YYYY-MM-DD
    hour: int  # author-local hour
    tz: str
    parents: int
    subject: str
    files: list = field(default_factory=list)


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def parse_commit(text):
    """Parse the text of one commit chunk (without the leading marker)."""
    header, _, rest = text.partition("\0")
    parts = header.split(FIELD_SEP, 6)
    if len(parts) < 7:
        parts += [""] * (7 - len(parts))
    sha, name, email, at, ai, parents, subject = parts
    try:
        ts = int(at)
    except ValueError:
        ts = 0
    date = ai[:10]
    try:
        hour = int(ai[11:13])
    except ValueError:
        hour = 0
    tz = ai[20:25]
    commit = Commit(sha, name, email.lower(), ts, date, hour, tz,
                    len(parents.split()), subject)
    tokens = rest.split("\0")
    if tokens:
        tokens[0] = tokens[0].lstrip("\n")
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if not tok:
            i += 1
            continue
        fields = tok.split("\t", 2)
        if len(fields) < 3:
            i += 1
            continue
        a, d, path = fields
        binary = a == "-" or d == "-"
        added = 0 if binary else _to_int(a)
        deleted = 0 if binary else _to_int(d)
        old = None
        if path == "":  # rename/copy: "a\td\t\0old\0new\0"
            if i + 2 >= n:
                break
            old, path = tokens[i + 1], tokens[i + 2]
            i += 3
        else:
            i += 1
        commit.files.append(FileChange(path, added, deleted, binary, old))
    return commit


def _to_int(s):
    try:
        return int(s)
    except ValueError:
        return 0


def iter_commit_texts(chunks):
    """Split an iterable of bytes chunks into per-commit strings."""
    buf = b""
    marker = COMMIT_MARK.encode()
    for chunk in chunks:
        buf += chunk
        if marker not in buf:
            continue
        pieces = buf.split(marker)
        buf = pieces.pop()
        for piece in pieces:
            if piece:
                yield piece.decode("utf-8", "replace")
    if buf:
        yield buf.decode("utf-8", "replace")


def iter_commits(chunks):
    for text in iter_commit_texts(chunks):
        yield parse_commit(text)


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------

def bus_factor(churn_by_author, threshold=BUS_THRESHOLD):
    """Smallest number of authors whose churn reaches ``threshold`` of the total."""
    values = sorted((v for v in churn_by_author.values() if v > 0), reverse=True)
    total = sum(values)
    if total <= 0:
        return 0
    running = 0
    for count, value in enumerate(values, 1):
        running += value
        if running >= threshold * total:
            return count
    return len(values)


def top_dir(path):
    return path.split("/", 1)[0] if "/" in path else ROOT_DIR


def matches_any(path, patterns):
    return any(fnmatch.fnmatchcase(path, p) for p in patterns)


class Aggregator:
    """Accumulates commits (newest first, as ``git log`` emits them)."""

    def __init__(self, excludes=()):
        self.excludes = list(excludes)
        self.commits = 0
        self.merges = 0
        self.added = 0
        self.deleted = 0
        self.days = set()
        self.weeks = {}
        self.heat = [[0] * 24 for _ in range(7)]
        self.authors = {}
        self.files = {}
        self.dirs = {}
        self.dirs2 = {}
        self.dir_authors = {}
        self.author_churn = Counter()
        self.first = None  # (ts, date, name, sha)
        self.last = None
        self.msg_count = 0
        self.msg_len = 0
        self.cc_types = Counter()
        self.first_words = Counter()
        self._alias = {}
        self._date_cache = {}

    def _resolve(self, path):
        seen = 0
        while path in self._alias and seen < 50:
            path = self._alias[path]
            seen += 1
        return path

    def _date_info(self, date):
        info = self._date_cache.get(date)
        if info is None:
            try:
                d = _dt.date.fromisoformat(date)
            except ValueError:
                d = _dt.date(1970, 1, 1)
            monday = d - _dt.timedelta(days=d.weekday())
            info = (d.weekday(), monday.isoformat())
            self._date_cache[date] = info
        return info

    def add(self, c):
        self.commits += 1
        is_merge = c.parents > 1
        if is_merge:
            self.merges += 1
        weekday, week = self._date_info(c.date)
        self.days.add(c.date)
        self.heat[weekday][c.hour % 24] += 1

        a = self.authors.get(c.email)
        if a is None:
            a = self.authors[c.email] = {
                "name": c.name, "email": c.email, "commits": 0, "added": 0,
                "deleted": 0, "first_ts": c.ts, "first": c.date,
                "last_ts": c.ts, "last": c.date,
            }
        a["commits"] += 1
        if c.ts < a["first_ts"]:
            a["first_ts"], a["first"] = c.ts, c.date
        if c.ts > a["last_ts"]:
            a["last_ts"], a["last"], a["name"] = c.ts, c.date, c.name

        if self.first is None or c.ts < self.first[0]:
            self.first = (c.ts, c.date, c.name, c.sha)
        if self.last is None or c.ts > self.last[0]:
            self.last = (c.ts, c.date, c.name, c.sha)

        w = self.weeks.get(week)
        if w is None:
            w = self.weeks[week] = [0, 0, 0]
        w[0] += 1

        if not is_merge and c.subject:
            self.msg_count += 1
            self.msg_len += len(c.subject)
            m = _CC_RE.match(c.subject)
            if m:
                self.cc_types[m.group(1).lower()] += 1
            wm = _WORD_RE.search(c.subject.split(None, 1)[0])
            if wm:
                self.first_words[wm.group(0).lower()] += 1

        for f in c.files:
            # Renames: history is newest-first, so older commits that touched
            # the old path are credited to the new one.
            if f.old_path is not None:
                new = self._resolve(f.path)
                if f.old_path != new:
                    self._alias[f.old_path] = new
                path = new
            else:
                path = self._resolve(f.path)
            if self.excludes and (matches_any(path, self.excludes)
                                  or matches_any(f.path, self.excludes)):
                continue
            churn = f.added + f.deleted
            self.added += f.added
            self.deleted += f.deleted
            a["added"] += f.added
            a["deleted"] += f.deleted
            w[1] += f.added
            w[2] += f.deleted
            rec = self.files.get(path)
            if rec is None:
                rec = self.files[path] = [0, 0, 0, f.binary]
            rec[0] += 1
            rec[1] += f.added
            rec[2] += f.deleted
            top = top_dir(path)
            d = self.dirs.get(top)
            if d is None:
                d = self.dirs[top] = [0, 0]
            d[0] += f.added
            d[1] += f.deleted
            parts = path.split("/")
            if len(parts) > 2:
                key = "/".join(parts[:2])
                d2 = self.dirs2.get(key)
                if d2 is None:
                    d2 = self.dirs2[key] = [0, 0]
                d2[0] += f.added
                d2[1] += f.deleted
            if churn:
                self.author_churn[c.email] += churn
                da = self.dir_authors.setdefault(top, Counter())
                da[c.email] += churn


def _weekly_series(weeks):
    if not weeks:
        return []
    keys = sorted(weeks)
    cur = _dt.date.fromisoformat(keys[0])
    end = _dt.date.fromisoformat(keys[-1])
    out = []
    while cur <= end:
        k = cur.isoformat()
        c, a, d = weeks.get(k, (0, 0, 0))
        out.append({"week": k, "commits": c, "added": a, "deleted": d})
        cur += _dt.timedelta(days=7)
    return out


def summarize(agg, meta, languages, top_n=15):
    """Turn an Aggregator into the plain-dict statistics structure."""
    names = {e: a["name"] for e, a in agg.authors.items()}
    authors = sorted(agg.authors.values(),
                     key=lambda a: (-a["commits"], -(a["added"] + a["deleted"]), a["name"]))
    authors_out = [{k: v for k, v in a.items() if k not in ("first_ts", "last_ts")}
                   for a in authors]

    files = agg.files
    by_touch = sorted(files.items(), key=lambda kv: (-kv[1][0], -(kv[1][1] + kv[1][2]), kv[0]))
    by_churn = sorted(files.items(), key=lambda kv: (-(kv[1][1] + kv[1][2]), -kv[1][0], kv[0]))

    def file_row(item):
        p, r = item
        return {"path": p, "touches": r[0], "added": r[1], "deleted": r[2],
                "churn": r[1] + r[2], "binary": r[3]}

    def dir_rows(dirs):
        rows = [{"path": k, "added": v[0], "deleted": v[1], "churn": v[0] + v[1]}
                for k, v in dirs.items()]
        rows.sort(key=lambda r: (-r["churn"], r["path"]))
        return rows

    bus_dirs = []
    for d, counter in agg.dir_authors.items():
        total = sum(counter.values())
        top_email, top_val = counter.most_common(1)[0]
        bus_dirs.append({
            "path": d, "churn": total, "authors": len(counter),
            "bus_factor": bus_factor(counter),
            "top_author": names.get(top_email, top_email),
            "top_share": top_val / total if total else 0.0,
        })
    bus_dirs.sort(key=lambda r: (-r["churn"], r["path"]))

    ov = {
        "commits": agg.commits, "merges": agg.merges,
        "authors": len(agg.authors), "active_days": len(agg.days),
        "added": agg.added, "deleted": agg.deleted, "files": len(agg.files),
        "first": _point(agg.first), "last": _point(agg.last),
    }
    msgs = {
        "count": agg.msg_count,
        "avg_length": (agg.msg_len / agg.msg_count) if agg.msg_count else 0.0,
        "conventional": sum(agg.cc_types.values()),
        "types": agg.cc_types.most_common(10),
        "first_words": agg.first_words.most_common(10),
    }
    data = dict(meta)
    data.update({
        "overview": ov,
        "weekly": _weekly_series(agg.weeks),
        "heatmap": agg.heat,
        "authors": authors_out,
        "hot_files_by_touches": [file_row(i) for i in by_touch[:top_n]],
        "hot_files_by_churn": [file_row(i) for i in by_churn[:top_n]],
        "dirs": dir_rows(agg.dirs)[:top_n],
        "dirs_depth2": dir_rows(agg.dirs2)[:top_n],
        "languages": languages,
        "bus_factor": {
            "overall": bus_factor(agg.author_churn),
            "threshold": BUS_THRESHOLD,
            "dirs": bus_dirs[:top_n],
        },
        "messages": msgs,
    })
    return data


def _point(p):
    if p is None:
        return None
    return {"date": p[1], "author": p[2], "sha": p[3][:10]}


# --------------------------------------------------------------------------
# Talking to git
# --------------------------------------------------------------------------

def _git(repo, *args, check=True):
    try:
        r = subprocess.run(["git", "-C", repo, "-c", "core.quotepath=off", *args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise GitpulseError("git not found on PATH")
    if check and r.returncode != 0:
        raise GitpulseError(r.stderr.decode("utf-8", "replace").strip() or "git failed")
    return r


def normalize_until(value):
    """``--until 2025-06-30`` should include that whole day."""
    if value and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value + " 23:59:59"
    return value


def repo_root(path):
    if not os.path.isdir(path):
        raise GitpulseError("not a directory: %s" % path)
    r = _git(path, "rev-parse", "--show-toplevel", check=False)
    if r.returncode != 0:
        raise GitpulseError("not a git repository: %s" % path)
    return r.stdout.decode("utf-8", "replace").strip()


def _stream_log(repo, rev, since, until):
    cmd = ["git", "-C", repo, "-c", "core.quotepath=off", "log", "--numstat", "-z",
           "-M", "--use-mailmap", "--no-color", "--no-ext-diff", "--format=" + LOG_FORMAT]
    if since:
        cmd.append("--since=" + since)
    if until:
        cmd.append("--until=" + normalize_until(until))
    cmd += [rev, "--"]
    err = tempfile.TemporaryFile()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err)
    try:
        while True:
            chunk = proc.stdout.read(CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
    finally:
        proc.stdout.close()
        rc = proc.wait()
        if rc != 0:
            err.seek(0)
            msg = err.read().decode("utf-8", "replace").strip()
            err.close()
            raise GitpulseError(msg or "git log failed")
        err.close()


def language_breakdown(repo, tree_sha, excludes=()):
    """Line counts per language at ``tree_sha`` (binary files are skipped)."""
    cmd = ["git", "-C", repo, "-c", "core.quotepath=off", "grep", "-I", "-c", "-z", "",
           tree_sha, "--"]
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
    except FileNotFoundError:
        raise GitpulseError("git not found on PATH")
    return count_languages(out, len(tree_sha) + 1, excludes)


def count_languages(out, prefix_len, excludes=()):
    lines = Counter()
    nfiles = Counter()
    pos = 0
    n = len(out)
    while pos < n:
        z = out.find(b"\0", pos)
        if z < 0:
            break
        nl = out.find(b"\n", z + 1)
        if nl < 0:
            nl = n
        path = out[pos + prefix_len:z].decode("utf-8", "replace")
        try:
            count = int(out[z + 1:nl])
        except ValueError:
            count = 0
        pos = nl + 1
        if excludes and matches_any(path, excludes):
            continue
        lang = language_of(path)
        lines[lang] += count
        nfiles[lang] += 1
    total = sum(lines.values())
    rows = [{"name": k, "lines": v, "files": nfiles[k],
             "percent": (100.0 * v / total) if total else 0.0}
            for k, v in lines.items() if v > 0]
    rows.sort(key=lambda r: (r["name"] == OTHER, -r["lines"], r["name"]))
    return rows


def analyze(path=".", since=None, until=None, branch=None, excludes=(), progress=None):
    """Analyze the repository at ``path`` and return the statistics dict."""
    say = progress or (lambda msg: None)
    root = repo_root(path)
    excludes = list(excludes)
    shallow = _git(root, "rev-parse", "--is-shallow-repository", check=False) \
        .stdout.decode().strip() == "true"
    rev = branch or "HEAD"
    head = _git(root, "rev-parse", "--verify", "-q", rev + "^{commit}", check=False)
    meta = {
        "repo": os.path.basename(root.rstrip("/")) or root,
        "ref": branch or "HEAD",
        "since": since, "until": until, "excludes": excludes,
        "shallow": shallow, "empty": False,
    }
    if head.returncode != 0:
        if branch:
            raise GitpulseError("unknown branch or revision: %s" % branch)
        meta["empty"] = True
        return summarize(Aggregator(excludes), meta, [])

    say("reading history of %s (%s)..." % (meta["repo"], meta["ref"]))
    agg = Aggregator(excludes)
    for commit in iter_commits(_stream_log(root, rev, since, until)):
        agg.add(commit)
        if agg.commits % 2000 == 0:
            say("  %d commits parsed" % agg.commits)
    say("  %d commits parsed" % agg.commits)

    languages = []
    if agg.commits:
        tip = head.stdout.decode().strip()
        if until:
            r = _git(root, "rev-list", "-1", "--until=" + normalize_until(until), rev,
                     check=False)
            if r.returncode == 0 and r.stdout.strip():
                tip = r.stdout.decode().strip()
        say("counting lines per language...")
        languages = language_breakdown(root, tip, excludes)
    if agg.commits == 0:
        meta["empty"] = True
    return summarize(agg, meta, languages)
