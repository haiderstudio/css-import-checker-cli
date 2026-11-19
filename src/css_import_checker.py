#!/usr/bin/env python3
"""Check CSS files contain no @import.

Run: python3 src/css_import_checker.py styles.css
     python3 src/css_import_checker.py project/
     python3 src/css_import_checker.py --stdin < styles.css

One @import in a stylesheet makes the browser fetch
stylesheets one after another instead of together —
the page paints late for a reason that reads like a
slow server, not a stylesheet line. A <link> tag does
not have this problem: linked stylesheets load in
parallel. This tool names each @import, with the file
and the line number, and exits 1 when any is found, so
it can fail a CI run. A file with no @import exits 0.

The scan is plain text: every "@import" outside
comments and strings is a finding. An "@import" inside
a comment or a quoted string is not one — a string
like content: "@import" is just text. A longer word
that only starts with "@import", such as "@imported",
is not one either. The line number is always measured
in the original file.

It reads CSS only. It never edits a file, never touches
the network, and reads only the files and folders you
point it at.
"""

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

__version__ = "1.0.0"

CSS_SUFFIX = ".css"


def blank_comments_and_strings(text):
    """Blank comments and string contents, keeping positions.

    Returns (clean, unclosed_comment). clean is a copy of
    the text the same length, where every comment
    (/* ... */) and every quoted string has its contents
    replaced by spaces. Newlines are kept, so a line
    number measured in the blanked text is the line
    number in the original. Blanked text is safe to scan
    for @import: an "@import" inside a comment or a
    string can no longer fool the check. unclosed_comment
    is True when a "/*" never closes — the rest of the
    file is comment, so the blanked text blanks it to
    the end.
    """
    out = []
    unclosed = False
    i = 0
    size = len(text)
    while i < size:
        char = text[i]
        if char in ("\"", "'"):
            out.append(" ")
            i += 1
            while i < size and text[i] != char:
                if text[i] == "\\" and i + 1 < size:
                    out.append(" ")
                    out.append("\n" if text[i + 1] == "\n" else " ")
                    i += 2
                    continue
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i < size:
                out.append(" ")
                i += 1
        elif char == "/" and i + 1 < size and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                unclosed = True
                for rest in text[i:]:
                    out.append("\n" if rest == "\n" else " ")
                i = size
            else:
                for rest in text[i:end + 2]:
                    out.append("\n" if rest == "\n" else " ")
                i = end + 2
        else:
            out.append(char)
            i += 1
    return "".join(out), unclosed


def _line_number(text, index):
    return text.count("\n", 0, index) + 1


def _statement(text, index):
    """The full line holding the @import, trimmed."""
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    if end == -1:
        end = len(text)
    line = text[start:end].strip()
    if len(line) > 100:
        line = line[:97] + "..."
    return line


def check_text(text):
    """Check one CSS document given as text.

    Returns (findings, errors). A finding is a dict with
    "line" and "statement".
    """
    clean, unclosed = blank_comments_and_strings(text)
    findings = []
    errors = []
    if unclosed:
        errors.append("unclosed comment")
    needle = "@import"
    start = 0
    while True:
        index = clean.find(needle, start)
        if index == -1:
            break
        after = index + len(needle)
        if after < len(clean) and (
                clean[after].isalnum() or clean[after] in ("_", "-")):
            start = after
            continue
        findings.append({
            "line": _line_number(clean, index),
            "statement": _statement(text, index),
        })
        start = after
    return findings, errors


def check_file(path):
    """Check one file. Returns (findings, errors)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], ["not valid UTF-8"]
    except OSError as exc:
        return [], ["could not read the file: %s" % exc]
    return check_text(text)


def _is_excluded(name, patterns):
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def collect_paths(paths, recursive, exclude):
    """Turn command-line paths into a sorted list of files.

    A file given directly is always checked, whatever its
    name. A folder is walked for files ending in .css
    only. .git folders are never walked, and directory
    links are never followed.
    """
    found = []
    seen = set()
    for given in paths:
        target = Path(given)
        if target.is_file():
            key = str(target.resolve())
            if key not in seen:
                seen.add(key)
                found.append(str(target))
        elif target.is_dir():
            if recursive:
                walker = os.walk(target, followlinks=False)
            else:
                walker = [(str(target), [], sorted(
                    p.name for p in target.iterdir() if p.is_file()))]
            for root, dirs, files in walker:
                dirs[:] = sorted(
                    d for d in dirs if d != ".git")
                for name in sorted(files):
                    if not name.endswith(CSS_SUFFIX):
                        continue
                    if _is_excluded(name, exclude):
                        continue
                    full = os.path.join(root, name)
                    key = str(Path(full).resolve())
                    if key not in seen:
                        seen.add(key)
                        found.append(full)
        else:
            found.append(given)
    return sorted(found)


def _fail_line(path, finding):
    return ('FAIL %s: line %d uses @import — %s'
            % (path, finding["line"], finding["statement"]))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="css_import_checker",
        description="Check CSS files contain no @import.")
    parser.add_argument("paths", nargs="*", metavar="PATH",
                        help="CSS file or folder to check")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one CSS document from standard input")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        metavar="PATTERN",
                        help="skip files whose name matches the pattern "
                        "(may be given more than once)")
    parser.add_argument("--version", action="version",
                        version="css_import_checker " + __version__)
    args = parser.parse_args(argv)

    results = []
    if args.stdin:
        if args.paths:
            print("error: --stdin takes no paths",
                  file=sys.stderr)
            return 2
        text = sys.stdin.read()
        findings, errors = check_text(text)
        results.append(("<stdin>", findings, errors))
    else:
        if not args.paths:
            print("error: give at least one file or folder to check",
                  file=sys.stderr)
            return 2
        missing = [p for p in args.paths
                   if not Path(p).exists()]
        if missing:
            for path in missing:
                print("error: no such file or folder: %s" % path,
                      file=sys.stderr)
            return 2
        files = collect_paths(args.paths, not args.no_recursive,
                              args.exclude)
        if not files:
            print("error: no .css files found", file=sys.stderr)
            return 2
        for path in files:
            findings, errors = check_file(path)
            results.append((path, findings, errors))

    checked = len(results)
    total_findings = sum(len(f) for _, f, _ in results)
    bad_files = sum(1 for _, f, e in results if f or e)

    if args.json:
        print(json.dumps({
            "files": [
                {"path": path, "findings": findings,
                 "errors": errors}
                for path, findings, errors in results
            ],
            "checked": checked,
            "findings": total_findings,
        }, indent=2))
    else:
        for path, findings, errors in results:
            for finding in findings:
                print(_fail_line(path, finding))
            for error in errors:
                print("ERROR %s: %s" % (path, error))
        if total_findings == 0 and bad_files == 0:
            print("OK — %d file(s) checked, no @import."
                  % checked)
        else:
            print("Checked %d file(s), %d @import(s) in %d file(s)."
                  % (checked, total_findings, bad_files))

    if total_findings or bad_files:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
