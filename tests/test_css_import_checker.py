#!/usr/bin/env python3
"""Tests for css_import_checker — stdlib unittest only."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import css_import_checker as checker

REPO = Path(__file__).resolve().parent.parent


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def findings_of(text):
    return checker.check_text(text)


class TestImports(unittest.TestCase):
    def test_clean_file_passes(self):
        bad, errors = findings_of("body {\n  margin: 0;\n}\n")
        self.assertEqual(bad, [])
        self.assertEqual(errors, [])

    def test_simple_import_flagged(self):
        bad, _ = findings_of('@import "base.css";\n')
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertEqual(bad[0]["statement"], '@import "base.css";')

    def test_import_with_url_flagged(self):
        bad, _ = findings_of('@import url("base.css");\n')
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)

    def test_import_with_media_flagged(self):
        bad, _ = findings_of('@import url("print.css") print;\n')
        self.assertEqual(len(bad), 1)

    def test_import_without_semicolon_flagged(self):
        bad, _ = findings_of('@import "base.css"\n')
        self.assertEqual(len(bad), 1)

    def test_import_at_end_of_file_flagged(self):
        bad, _ = findings_of('a {\n  color: red;\n}\n@import "x.css";')
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 4)

    def test_multiple_imports_in_order(self):
        bad, _ = findings_of(
            '@import "a.css";\na {\n  color: red;\n}\n'
            '@import "b.css";\n@import url("c.css");\n')
        self.assertEqual(len(bad), 3)
        self.assertEqual([item["line"] for item in bad], [1, 5, 6])
        self.assertEqual(bad[1]["statement"], '@import "b.css";')

    def test_import_after_a_rule_flagged(self):
        bad, _ = findings_of(
            "a {\n  color: red;\n}\n@import \"late.css\";\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 4)

    def test_import_in_comment_ignored(self):
        bad, _ = findings_of(
            '/* @import "not-real.css"; */\na {\n  color: red;\n}\n')
        self.assertEqual(bad, [])

    def test_import_in_multiline_comment_ignored(self):
        bad, _ = findings_of(
            "/*\n@import \"hidden.css\";\n*/\na {\n  color: red;\n}\n")
        self.assertEqual(bad, [])

    def test_import_after_comment_on_same_line(self):
        bad, _ = findings_of(
            '/* note */ @import "real.css";\n')
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)

    def test_import_in_double_quoted_string_ignored(self):
        bad, _ = findings_of(
            '.icon::before {\n  content: "@import";\n}\n')
        self.assertEqual(bad, [])

    def test_import_in_single_quoted_string_ignored(self):
        bad, _ = findings_of(
            ".icon::before {\n  content: '@import';\n}\n")
        self.assertEqual(bad, [])

    def test_import_in_url_string_ignored(self):
        bad, _ = findings_of(
            '.a {\n  background: url("@import.png");\n}\n')
        self.assertEqual(bad, [])

    def test_imported_word_not_flagged(self):
        bad, _ = findings_of('@imported "fake.css";\n')
        self.assertEqual(bad, [])

    def test_import_dash_word_not_flagged(self):
        bad, _ = findings_of('@import-foo "fake.css";\n')
        self.assertEqual(bad, [])

    def test_class_named_import_not_flagged(self):
        bad, _ = findings_of(".import {\n  color: red;\n}\n")
        self.assertEqual(bad, [])

    def test_comment_markers_in_string_ignored(self):
        bad, _ = findings_of(
            '.note::after {\n  content: "/* not a comment */";\n}\n')
        self.assertEqual(bad, [])

    def test_escaped_quote_in_string(self):
        bad, _ = findings_of(
            '.a::before {\n  content: "say \\"@import\\" loud";\n}\n'
            '@import "real.css";\n')
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 4)

    def test_unclosed_comment_is_an_error(self):
        bad, errors = findings_of("a {\n  color: red;\n}\n/* never closed\n")
        self.assertEqual(len(errors), 1)
        self.assertIn("unclosed comment", errors[0])

    def test_import_after_unclosed_comment_is_hidden(self):
        bad, errors = findings_of(
            '/* never closed\n@import "hidden.css";\n')
        self.assertEqual(bad, [])
        self.assertEqual(len(errors), 1)

    def test_empty_document_passes(self):
        bad, errors = findings_of("")
        self.assertEqual(bad, [])
        self.assertEqual(errors, [])

    def test_comment_only_document_passes(self):
        bad, errors = findings_of("/* just a note */\n")
        self.assertEqual(bad, [])
        self.assertEqual(errors, [])

    def test_link_tag_line_not_flagged(self):
        bad, _ = findings_of(
            '<link rel="stylesheet" href="styles.css">\n')
        self.assertEqual(bad, [])

    def test_long_statement_truncated(self):
        long_url = "x" * 120
        bad, _ = findings_of('@import url("%s");\n' % long_url)
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0]["statement"].endswith("..."))
        self.assertEqual(len(bad[0]["statement"]), 100)


class TestCli(unittest.TestCase):
    def test_clean_file_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "ok.css", "a {\n  color: red;\n}\n")
            code, out, _ = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("OK", out)
            self.assertIn("no @import", out)

    def test_flagged_file_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.css", '@import "base.css";\n')
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn(
                'FAIL %s: line 1 uses @import — @import "base.css";'
                % path, out)
            self.assertIn("1 @import(s)", out)

    def test_folder_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.css", "a {\n  color: red;\n}\n")
            write(tmp, "b.css", '@import "x.css";\n')
            write(tmp, "notes.txt", '@import "x.css";\n')
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)
            self.assertNotIn("notes.txt", out)

    def test_nested_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "sub/deep.css", '@import "x.css";\n')
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("deep.css", out)

    def test_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "top.css", "a {\n  color: red;\n}\n")
            write(tmp, "sub/deep.css", '@import "x.css";\n')
            code, out, _ = run_cli(["--no-recursive", tmp])
            self.assertEqual(code, 0)
            self.assertIn("OK — 1 file(s) checked", out)

    def test_exclude_skips_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.css", '@import "x.css";\n')
            write(tmp, "skip.css", '@import "y.css";\n')
            code, out, _ = run_cli(["--exclude", "skip.css", tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s)", out)
            self.assertNotIn("skip.css", out)

    def test_git_folder_skipped_in_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, ".git/hooks/bad.css", '@import "x.css";\n')
            write(tmp, "a.css", "a {\n  color: red;\n}\n")
            code, out, _ = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("OK — 1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "style.txt", '@import "x.css";\n')
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("style.txt", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.css", '@import "x.css";\n')
            code, out, _ = run_cli([path, path])
            self.assertEqual(code, 1)
            self.assertIn("Checked 1 file(s)", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.css", '@import "x.css";\n')
            code, out, _ = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(
                data["files"][0]["findings"][0]["line"], 1)
            self.assertEqual(
                data["files"][0]["findings"][0]["statement"],
                '@import "x.css";')
            self.assertEqual(data["files"][0]["errors"], [])

    def test_stdin_clean(self):
        old_stdin = sys.stdin
        sys.stdin = io.StringIO("")
        try:
            code, out, _ = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)
        self.assertIn("no @import", out)

    def test_stdin_dirty(self):
        old_stdin = sys.stdin
        sys.stdin = io.StringIO('@import "x.css";\n')
        try:
            code, out, _ = run_cli(["--stdin"])
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 1)
        self.assertIn("FAIL <stdin>: line 1 uses @import", out)

    def test_stdin_with_paths_is_usage_error(self):
        code, _, err = run_cli(["--stdin", "a.css"])
        self.assertEqual(code, 2)

    def test_no_paths_is_usage_error(self):
        code, _, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_exit_2(self):
        code, _, err = run_cli(["/no/such/file.css"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no .css files found", err)

    def test_bad_flag_exit_2(self):
        code, _, _ = run_cli(["--nope", "a.css"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, _ = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("css_import_checker", out)

    def test_non_utf8_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.css", b"\xff\xfe{}")
            code, out, _ = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = '@import "x.css";\n'
            path = write(tmp, "bad.css", text)
            run_cli([path])
            self.assertEqual(Path(path).read_text(), text)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.css", '@import "x.css";\n')
            result = subprocess.run(
                [sys.executable,
                 str(REPO / "src" / "css_import_checker.py"), path],
                capture_output=True, text=True, cwd="/")
            self.assertEqual(result.returncode, 1)
            self.assertIn("line 1 uses @import", result.stdout)

    def test_cli_runs_under_fake_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.css", '@import "x.css";\n')
            env = dict(os.environ, HOME=tmp)
            result = subprocess.run(
                [sys.executable,
                 str(REPO / "src" / "css_import_checker.py"), path],
                capture_output=True, text=True, cwd=tmp, env=env)
            self.assertEqual(result.returncode, 1)

    def test_run_example_output_matches_sample(self):
        sample = (REPO / "examples" / "sample-output.md").read_text()
        result = subprocess.run(
            ["sh", str(REPO / "examples" / "run-example.sh")],
            capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), sample.strip())

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        flagged = (REPO / "examples" / "flagged.css").read_text()
        bad, _ = checker.check_text(flagged)
        for item in bad:
            line = ("FAIL examples/flagged.css: line %d uses @import — %s"
                    % (item["line"], item["statement"]))
            self.assertIn(line, readme)


class TestExamples(unittest.TestCase):
    def test_clean_example_passes(self):
        code, _, _ = run_cli([str(REPO / "examples" / "clean.css")])
        self.assertEqual(code, 0)

    def test_flagged_example_fails_with_two(self):
        bad, _ = checker.check_text(
            (REPO / "examples" / "flagged.css").read_text())
        self.assertEqual(len(bad), 2)
        self.assertEqual([item["line"] for item in bad], [3, 7])
        self.assertEqual(bad[0]["statement"], '@import url("base.css");')
        self.assertEqual(bad[1]["statement"], '@import "theme.css";')

    def test_edge_example_passes(self):
        code, _, _ = run_cli([str(REPO / "examples" / "edge.css")])
        self.assertEqual(code, 0)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True):
        """Every file in the repo, minus .git and caches."""
        for path in REPO.rglob("*"):
            if path.is_dir():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix == ".pyc":
                continue
            if skip_tests and "tests" in path.parts:
                continue
            yield path

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True):
            text = path.read_text(errors="ignore")
            for marker in ("/home/", "/Users/", "C:\\", "/tmp/"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        import ast
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src" / "css_import_checker.py",
                       REPO / "tests" / "test_css_import_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"css_import_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src" / "css_import_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertTrue(lines, ".gitignore is empty")
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text()
        self.assertIn("tests/test_css_import_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_the_neighbouring_repos(self):
        readme = (REPO / "README.md").read_text()
        for name in ("css-empty-rule-checker-cli",
                     "css-important-checker-cli",
                     "css-duplicate-property-checker-cli"):
            self.assertIn(name, readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
