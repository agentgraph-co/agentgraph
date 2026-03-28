"""Tests for scanner false-positive reduction features.

Tests inline suppression (ag-scan:ignore), allowlist, and context-aware scanning.
"""
from __future__ import annotations

from src.scanner.scan import _scan_content


class TestInlineSuppression:
    """Option 1: Lines with ag-scan:ignore are skipped."""

    def test_suppression_skips_finding(self):
        code = 'api_key = "sk-ant-AAAA1234567890BBBB1234567890CCCC1234567890DD"  # ag-scan:ignore\n'
        findings, _ = _scan_content(code, "config.py")
        assert len(findings) == 0

    def test_no_suppression_still_flags(self):
        code = 'api_key = "sk-ant-AAAA1234567890BBBB1234567890CCCC1234567890DD"\n'
        findings, _ = _scan_content(code, "config.py")
        assert len(findings) > 0

    def test_suppression_in_comment_variants(self):
        code = 'subprocess.run(["ls"])  // ag-scan:ignore\n'
        findings, _ = _scan_content(code, "tool.py")
        assert len(findings) == 0


class TestAllowlist:
    """Option 2: Allowlist suppresses specific findings for specific files."""

    def test_allowlist_suppresses_finding(self):
        code = 'subprocess.run(cmd)\n'
        allowlist = {("tool.py", "subprocess.run / Popen (Python)")}
        findings, _ = _scan_content(code, "tool.py", allowlist=allowlist)
        assert len(findings) == 0

    def test_allowlist_glob_match(self):
        code = 'subprocess.run(cmd)\n'
        allowlist = {("src/utils/*", "subprocess.run / Popen (Python)")}
        findings, _ = _scan_content(code, "src/utils/git.py", allowlist=allowlist)
        assert len(findings) == 0

    def test_allowlist_wrong_file_still_flags(self):
        code = 'subprocess.run(cmd)\n'
        allowlist = {("other.py", "subprocess.run / Popen (Python)")}
        findings, _ = _scan_content(code, "tool.py", allowlist=allowlist)
        assert len(findings) > 0

    def test_allowlist_wrong_name_still_flags(self):
        code = 'subprocess.run(cmd)\n'
        allowlist = {("tool.py", "eval() call")}
        findings, _ = _scan_content(code, "tool.py", allowlist=allowlist)
        assert len(findings) > 0


class TestContextAwareExec:
    """Option 3: Context-aware scanning for safe exec patterns."""

    def test_subprocess_hardcoded_args_safe(self):
        code = 'subprocess.run(["git", "status"])\n'
        findings, _ = _scan_content(code, "deploy.py")
        assert len(findings) == 0

    def test_subprocess_hardcoded_string_safe(self):
        code = "subprocess.run(['pip', 'install', 'requests'])\n"
        findings, _ = _scan_content(code, "setup.py")
        assert len(findings) == 0

    def test_subprocess_variable_arg_flagged(self):
        code = 'subprocess.run(user_input)\n'
        findings, _ = _scan_content(code, "handler.py")
        assert any(f.category == "unsafe_exec" for f in findings)

    def test_subprocess_shell_false_safe(self):
        code = 'subprocess.run(cmd, shell=False)\n'
        findings, _ = _scan_content(code, "runner.py")
        assert len(findings) == 0

    def test_ast_literal_eval_safe(self):
        code = 'result = ast.literal_eval(data)\n'
        findings, _ = _scan_content(code, "parser.py")
        assert not any(f.name == "eval() call" for f in findings)

    def test_plain_eval_still_flagged(self):
        code = 'result = eval(user_data)\n'
        findings, _ = _scan_content(code, "handler.py")
        assert any(f.name == "eval() call" for f in findings)


class TestContextAwareFs:
    """Option 3: Context-aware scanning for safe filesystem patterns."""

    def test_open_hardcoded_path_safe(self):
        code = 'data = open("config.json", "r").read()\n'
        findings, _ = _scan_content(code, "loader.py")
        assert len(findings) == 0

    def test_with_open_safe(self):
        code = 'with open(path, "r") as f:\n'
        findings, _ = _scan_content(code, "reader.py")
        assert not any(f.category == "fs_access" for f in findings)

    def test_path_write_text_safe(self):
        code = 'Path("output.txt").write_text(result)\n'
        findings, _ = _scan_content(code, "writer.py")
        assert not any(f.category == "fs_access" for f in findings)

    def test_open_variable_write_still_flagged(self):
        """open() with a variable path and write mode is still flagged."""
        code = 'f = open(user_path, "w")\n'
        findings, _ = _scan_content(code, "handler.py")
        # This should still be flagged because user_path is a variable
        # The "w" write mode pattern triggers, and it's not a hardcoded path
        # Note: the safe open check matches hardcoded strings, but user_path
        # is a variable so it won't match the safe pattern
        unsafe_fs = [f for f in findings if f.category == "fs_access"]
        assert len(unsafe_fs) > 0
