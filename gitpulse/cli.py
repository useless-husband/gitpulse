"""Command line interface."""

import argparse
import json
import sys

from . import __version__
from .collect import GitpulseError, analyze
from .report import render


def build_parser():
    p = argparse.ArgumentParser(
        prog="gitpulse",
        description="Turn a git repository's history into a single-file HTML report.")
    p.add_argument("repo", nargs="?", default=".", help="path to the repository (default: .)")
    p.add_argument("-o", "--output", help="output file (default: report.html; with --json: stdout)")
    p.add_argument("--since", help="only commits after this date, e.g. 2025-01-01")
    p.add_argument("--until", help="only commits before this date (inclusive), e.g. 2025-12-31")
    p.add_argument("--branch", help="branch or revision to analyze (default: HEAD)")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="ignore paths matching this glob, e.g. 'vendor/*' (repeatable)")
    p.add_argument("--lang", choices=("zh", "en"), default="zh", help="report language (default: zh)")
    p.add_argument("--json", action="store_true", help="print raw statistics as JSON instead of HTML")
    p.add_argument("-q", "--quiet", action="store_true", help="no progress messages")
    p.add_argument("--version", action="version", version="gitpulse " + __version__)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    def progress(msg):
        if not args.quiet:
            print(msg, file=sys.stderr, flush=True)

    try:
        data = analyze(args.repo, since=args.since, until=args.until, branch=args.branch,
                       excludes=args.exclude, progress=progress)
    except GitpulseError as e:
        print("gitpulse: error: %s" % e, file=sys.stderr)
        return 2

    if args.json:
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            _write(args.output, text)
            progress("wrote %s" % args.output)
        else:
            try:
                sys.stdout.write(text)
                sys.stdout.flush()
            except BrokenPipeError:  # e.g. `gitpulse --json | head`
                sys.stderr.close()
                return 0
        return 0

    out = args.output or "report.html"
    _write(out, render(data, args.lang))
    progress("wrote %s" % out)
    return 0


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
