# css-import-checker-cli

Check CSS files contain no @import, fail CI when one is found.

[![CI](https://github.com/haiderstudio/css-import-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/css-import-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`css_import_checker` reads CSS files, scans them for
`@import`, and reports each one with the file and the
line number. It exits 1 when any `@import` is found, so
it can fail a CI run. A file with no `@import` exits 0.

- One `@import` in a stylesheet makes the browser
  fetch stylesheets one after another instead of
  together — the page paints late for a reason that
  reads like a slow server, not a stylesheet line. A
  `<link>` tag does not have this problem: linked
  stylesheets load in parallel. A gate that names the
  exact line turns it into a `<link>` tag.
- The scan is plain text: every `@import` outside
  comments and strings is a finding, and each one is
  reported with the line it sits on.
- An `@import` inside a comment or a quoted string is
  not a finding — a string like `content: "@import"`
  is just text. A longer word that only starts with
  `@import`, such as `@imported`, is not one either.
  A line number is always measured in the original
  file.
- A file given directly on the command line is always
  checked, whatever its name. A folder is walked for
  files ending in `.css` only, recursively by default
  (`--no-recursive` stops at the top level). `.git`
  folders are never walked, and directory links are
  never followed.
- `--json` prints the result as JSON, and `--stdin`
  checks one CSS document read from standard input.
- A file that cannot be read — a file that is not
  valid UTF-8 — is reported as an error and fails the
  check the same way a finding does, and a file with
  an unclosed comment is reported as an error too.

## Who it is for

Anyone who ships a stylesheet — which is every site
owner. One `@import` hides in a file copied from a
tutorial or an old theme, and the page paints late
for a reason no one traces back to a stylesheet line.
This is the gate that names it at the pull request,
before it ships.

## What it does NOT do

- It does not check whether a class is used in the
  HTML. That is repo #74, css-class-checker-cli,
  which checks UNUSED classes — unused classes are a
  different check on the same files.
- It does not check empty rules. That is repo #99,
  css-empty-rule-checker-cli — an empty rule is a
  different check on the same files.
- It does not check `!important`. That is repo #89,
  css-important-checker-cli — `!important` is a
  different check on the same files. The names are
  close, the checks are not: this tool looks for
  `@import`, that one for `!important`.
- It does not check duplicate properties inside one
  rule. That is repo #78,
  css-duplicate-property-checker-cli — duplicate
  properties are a different check on the same files.
- It does not rewrite the `@import` into a `<link>`
  tag or remove it. It reports, you change the line.
- It never touches the network, and it only reads the
  files and folders you point it at.

## How this differs

- A fresh search of GitHub on Nov 17, 2026 found 1
  result for `"css-import-checker-cli"` — our own repo
  #89, css-important-checker-cli, matched because the
  search matches "important" against "import". It is
  not a rival. The same search for `css import
  checker` found 3 results: the same own repo, a
  CSS-art series piece that happens to use `@import`,
  and a PHP hospital system that happens to contain
  CSS. No rival is a tested command-line gate that
  checks CSS files for `@import`.
- So the narrow slice stands: `@import` only, skipping
  comments and strings, per-line reporting, a CI exit
  code, and a report-only tool that never edits a file.

## Install

```sh
git clone https://github.com/haiderstudio/css-import-checker-cli.git
cd css-import-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one stylesheet:

```sh
python3 src/css_import_checker.py styles.css
```

A stylesheet with no `@import` passes:

```sh
$ python3 src/css_import_checker.py examples/clean.css
OK — 1 file(s) checked, no @import.
```

A stylesheet with `@import` fails, with the line for
each one:

```sh
$ python3 src/css_import_checker.py examples/flagged.css
FAIL examples/flagged.css: line 3 uses @import — @import url("base.css");
FAIL examples/flagged.css: line 7 uses @import — @import "theme.css";
Checked 1 file(s), 2 @import(s) in 1 file(s).
```

Check a whole folder (`.css` files only):

```sh
$ python3 src/css_import_checker.py examples/
FAIL examples/flagged.css: line 3 uses @import — @import url("base.css");
FAIL examples/flagged.css: line 7 uses @import — @import "theme.css";
Checked 3 file(s), 2 @import(s) in 1 file(s).
```

Check one document from standard input:

```sh
$ python3 src/css_import_checker.py --stdin < examples/flagged.css
FAIL <stdin>: line 3 uses @import — @import url("base.css");
FAIL <stdin>: line 7 uses @import — @import "theme.css";
Checked 1 file(s), 2 @import(s) in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/css_import_checker.py --json examples/flagged.css
{
  "files": [
    {
      "path": "examples/flagged.css",
      "findings": [
        {
          "line": 3,
          "statement": "@import url(\"base.css\");"
        },
        {
          "line": 7,
          "statement": "@import \"theme.css\";"
        }
      ],
      "errors": []
    }
  ],
  "checked": 1,
  "findings": 2
}
```

Exit codes: 0 when no `@import` is found, 1 when any
`@import` or file error is found, 2 for a usage error
(a missing path, a bad flag, or no `.css` files found).

## Examples

An `@import` on the first line of a file is caught
with the line and the statement:

```sh
$ printf '@import "base.css";\na {\n  color: red;\n}\n' > two.css
$ python3 src/css_import_checker.py two.css
FAIL two.css: line 1 uses @import — @import "base.css";
Checked 1 file(s), 1 @import(s) in 1 file(s).
```

An `@import` inside a quoted string is just text, not
an import — a rule that only mentions the word passes:

```sh
$ printf 'a {\n  content: "@import";\n}\n' > quoted.css
$ python3 src/css_import_checker.py quoted.css
OK — 1 file(s) checked, no @import.
```

The same holds for an `@import` inside a comment and
for a word that only starts with `@import` —
`examples/edge.css` holds all three, and it passes:

```sh
$ python3 src/css_import_checker.py examples/edge.css
OK — 1 file(s) checked, no @import.
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_css_import_checker.py
```

The tests cover imports (a plain `@import`, one with
`url()`, one with a media type, one without a
semicolon, one at the end of the file, several in
order, one after a rule, an `@import` on the same line
after a comment), comments and strings (an `@import`
in a comment, in a multi-line comment, in a double
quoted string, in a single quoted string, in a
`url()` string, comment markers inside a string, an
escaped quote inside a string, an unclosed comment
reported as an error, an `@import` hidden by an
unclosed comment), lookalikes (a word starting with
`@import`, a word with a hyphen after it, a class
named `.import`, a `<link>` tag line, an empty
document, a comment-only document, a very long
statement truncated), the CLI (exit 0/1/2, folder
walking for several CSS files, nested folders,
`--no-recursive`, `--exclude`, `.git` skipped, a
direct file checked whatever its name, duplicate paths
checked once, `--json` output, `--stdin`, bad flags,
missing paths, empty folders, `--version`, a
non-UTF-8 file reported, input files left unchanged,
the tool run from `/` and under a fake HOME), the
bundled examples (sample output compared against a
fresh run, and the README-quoted outputs checked
against it), and hygiene checks (no placeholder text,
no absolute paths, stdlib imports only, no network
use in the source, `.env` first in `.gitignore`, CI
file runs the test file, README names the
neighbouring repos).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The
idea of checking a stylesheet is not new, and the
comment-and-string blanking technique is standard —
but no existing tool does this one job, checking local
CSS files for `@import` as a tested command-line gate,
as the search above shows — and every line of code
here is original, built on nothing but Python's
standard library.
