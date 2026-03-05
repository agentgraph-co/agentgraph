"""Tests for scripts/backup.sh — validates structure, commands, and logic."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

# Path to the backup script
SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "backup.sh"


@pytest.fixture(scope="module")
def script_content() -> str:
    """Read the backup script content once for all tests."""
    return SCRIPT_PATH.read_text()


@pytest.fixture(scope="module")
def script_lines(script_content: str) -> list[str]:
    """Split script into lines for line-by-line analysis."""
    return script_content.splitlines()


# -------------------------------------------------------------------------
# 1. Script exists and is valid bash
# -------------------------------------------------------------------------
class TestScriptValidity:
    """Verify the script file exists, is executable, and has valid bash syntax."""

    def test_script_exists(self) -> None:
        assert SCRIPT_PATH.exists(), f"Backup script not found at {SCRIPT_PATH}"

    def test_script_is_executable(self) -> None:
        assert os.access(SCRIPT_PATH, os.X_OK), "backup.sh must be executable"

    def test_bash_syntax_valid(self) -> None:
        """Run bash -n to check for syntax errors."""
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT_PATH)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Bash syntax errors in backup.sh:\n{result.stderr}"
        )

    def test_has_shebang(self, script_content: str) -> None:
        assert script_content.startswith("#!/"), "Script must start with a shebang"

    def test_uses_strict_mode(self, script_content: str) -> None:
        assert "set -euo pipefail" in script_content, (
            "Script must use strict mode (set -euo pipefail)"
        )


# -------------------------------------------------------------------------
# 2. pg_dump command structure
# -------------------------------------------------------------------------
class TestPgDumpCommand:
    """Verify the pg_dump command is correctly structured."""

    def test_uses_docker_exec(self, script_content: str) -> None:
        assert "docker exec" in script_content, (
            "Script must use 'docker exec' to run pg_dump inside the container"
        )

    def test_calls_pg_dump(self, script_content: str) -> None:
        assert "pg_dump" in script_content, "Script must call pg_dump"

    def test_pg_dump_specifies_user(self, script_content: str) -> None:
        assert re.search(r"pg_dump\s+.*-U\s", script_content), (
            "pg_dump must specify -U (user) flag"
        )

    def test_pg_dump_specifies_database(self, script_content: str) -> None:
        assert re.search(r"pg_dump\s+.*-d\s", script_content), (
            "pg_dump must specify -d (database) flag"
        )

    def test_pg_dump_no_owner_no_acl(self, script_content: str) -> None:
        assert "--no-owner" in script_content, (
            "pg_dump should use --no-owner for portability"
        )
        assert "--no-acl" in script_content, (
            "pg_dump should use --no-acl for portability"
        )

    def test_pipes_through_gzip(self, script_content: str) -> None:
        # The pg_dump output should be piped to gzip
        assert re.search(r"pg_dump.*\|\s*gzip", script_content, re.DOTALL), (
            "pg_dump output must be piped through gzip"
        )

    def test_output_file_has_gz_extension(self, script_content: str) -> None:
        assert re.search(r"\.sql\.gz", script_content), (
            "Backup filename must end in .sql.gz"
        )

    def test_container_name_configurable(self, script_content: str) -> None:
        assert "CONTAINER_NAME" in script_content, (
            "Container name should be configurable via CONTAINER_NAME variable"
        )

    def test_default_container_name(self, script_content: str) -> None:
        assert "agentgraph-postgres-1" in script_content, (
            "Default container name should be agentgraph-postgres-1"
        )

    def test_default_pg_user(self, script_content: str) -> None:
        # Should default PG_USER to 'agentgraph'
        assert re.search(
            r'PG_USER=.*agentgraph', script_content
        ), "Default PG_USER should be 'agentgraph'"

    def test_default_pg_db(self, script_content: str) -> None:
        assert re.search(
            r'PG_DB=.*agentgraph', script_content
        ), "Default PG_DB should be 'agentgraph'"


# -------------------------------------------------------------------------
# 3. Timestamp format
# -------------------------------------------------------------------------
class TestTimestampFormat:
    """Verify backup filenames use correct timestamp format."""

    def test_timestamp_uses_date_command(self, script_content: str) -> None:
        assert re.search(r'date \+%', script_content), (
            "Timestamp should be generated using the 'date' command"
        )

    def test_timestamp_format_includes_date_and_time(
        self, script_content: str
    ) -> None:
        # The format string should include year, month, day, hour, minute, second
        # Expecting something like %Y%m%d-%H%M%S or %Y-%m-%d-%H%M%S
        fmt_match = re.search(r"date \+(['\"]?)(%[^'\")\s]+)", script_content)
        assert fmt_match, "Could not find date format string"
        fmt = fmt_match.group(2)
        assert "%Y" in fmt, "Timestamp must include year (%Y)"
        assert "%m" in fmt or "%b" in fmt, (
            "Timestamp must include month (%m or %b)"
        )
        assert "%d" in fmt, "Timestamp must include day (%d)"
        assert "%H" in fmt, "Timestamp must include hour (%H)"
        assert "%M" in fmt, "Timestamp must include minute (%M)"
        assert "%S" in fmt, "Timestamp must include second (%S)"

    def test_backup_filename_pattern(self, script_content: str) -> None:
        # The filename variable should contain 'agentgraph-' prefix
        assert re.search(
            r'BACKUP_FILENAME=.*agentgraph-.*\.sql\.gz', script_content
        ), "Backup filename should follow pattern: agentgraph-TIMESTAMP.sql.gz"

    def test_generated_timestamp_is_parseable(self) -> None:
        """Verify the date format produces parseable output."""
        result = subprocess.run(
            ["date", "+%Y%m%d-%H%M%S"],
            capture_output=True,
            text=True,
        )
        ts = result.stdout.strip()
        assert re.match(r"^\d{8}-\d{6}$", ts), (
            f"Generated timestamp '{ts}' does not match YYYYMMDD-HHMMSS"
        )


# -------------------------------------------------------------------------
# 4. Backup rotation logic
# -------------------------------------------------------------------------
class TestBackupRotation:
    """Verify the backup rotation policy is correctly implemented."""

    def test_daily_rotation_configured(self, script_content: str) -> None:
        # Should keep 7 daily backups
        assert re.search(r'DAILY_KEEP=7', script_content), (
            "Daily retention should be set to 7"
        )

    def test_weekly_rotation_configured(self, script_content: str) -> None:
        # Should keep 4 weekly backups
        assert re.search(r'WEEKLY_KEEP=4', script_content), (
            "Weekly retention should be set to 4"
        )

    def test_daily_directory_exists(self, script_content: str) -> None:
        assert "daily" in script_content, (
            "Script should use a 'daily' subdirectory"
        )

    def test_weekly_directory_exists(self, script_content: str) -> None:
        assert "weekly" in script_content, (
            "Script should use a 'weekly' subdirectory"
        )

    def test_uses_ls_sort_by_time(self, script_content: str) -> None:
        # ls -1t sorts by modification time (newest first)
        assert "ls -1t" in script_content, (
            "Rotation should use 'ls -1t' to sort backups by time"
        )

    def test_uses_tail_for_rotation(self, script_content: str) -> None:
        # tail -n +N skips the first N-1 entries (keeps N-1 newest)
        assert re.search(r'tail -n \+', script_content), (
            "Rotation should use 'tail -n +N' to select old backups"
        )

    def test_rm_used_for_deletion(self, script_content: str) -> None:
        assert "rm -f" in script_content, (
            "Script must use 'rm -f' to remove old backups"
        )

    def test_daily_rotation_references_daily_keep(
        self, script_content: str
    ) -> None:
        # The daily rotation command should reference DAILY_KEEP
        assert re.search(r'DAILY_KEEP', script_content), (
            "Daily rotation must reference DAILY_KEEP variable"
        )

    def test_weekly_rotation_references_weekly_keep(
        self, script_content: str
    ) -> None:
        assert re.search(r'WEEKLY_KEEP', script_content), (
            "Weekly rotation must reference WEEKLY_KEEP variable"
        )

    def test_weekly_backup_on_sunday(self, script_content: str) -> None:
        # Day of week check: Sunday = 7 in ISO (date +%u)
        assert re.search(r'DAY_OF_WEEK.*date.*%u', script_content), (
            "Script should detect day of week using 'date +%u'"
        )
        assert re.search(
            r'DAY_OF_WEEK.*-eq\s+7', script_content
        ), "Weekly backup should trigger on Sunday (day 7)"

    def test_mkdir_creates_directories(self, script_content: str) -> None:
        assert "mkdir -p" in script_content, (
            "Script must create backup directories with mkdir -p"
        )


# -------------------------------------------------------------------------
# 5. S3 upload logic
# -------------------------------------------------------------------------
class TestS3Upload:
    """Verify optional S3 upload functionality."""

    def test_s3_bucket_variable_checked(self, script_content: str) -> None:
        assert "S3_BACKUP_BUCKET" in script_content, (
            "Script should check S3_BACKUP_BUCKET environment variable"
        )

    def test_aws_cli_availability_check(self, script_content: str) -> None:
        assert "command -v aws" in script_content, (
            "Script should verify AWS CLI is available before upload"
        )

    def test_aws_s3_cp_command(self, script_content: str) -> None:
        assert "aws s3 cp" in script_content, (
            "Script should use 'aws s3 cp' for uploads"
        )

    def test_s3_upload_is_optional(self, script_content: str) -> None:
        # The S3 upload should be guarded by a check for S3_BACKUP_BUCKET
        assert re.search(
            r'-n.*S3_BACKUP_BUCKET', script_content
        ), "S3 upload should only run when S3_BACKUP_BUCKET is set"

    def test_s3_failure_does_not_exit_1(self, script_content: str) -> None:
        # S3 failure should exit 2, not 1 (backup itself succeeded)
        assert "S3_EXIT=2" in script_content, (
            "S3 upload failure should set exit code 2 (not 1)"
        )

    def test_s3_uploads_to_daily_prefix(self, script_content: str) -> None:
        assert re.search(
            r's3://.*daily/', script_content
        ), "S3 upload should use a daily/ prefix path"

    def test_s3_uploads_weekly_on_sunday(self, script_content: str) -> None:
        # Weekly S3 upload should also be conditioned on Sunday
        assert re.search(
            r's3://.*weekly/', script_content
        ), "S3 should upload weekly backups to a weekly/ prefix"


# -------------------------------------------------------------------------
# 6. Logging
# -------------------------------------------------------------------------
class TestLogging:
    """Verify backup logging behavior."""

    def test_log_file_path_configured(self, script_content: str) -> None:
        assert "/var/log/agentgraph-backup.log" in script_content, (
            "Default log file should be /var/log/agentgraph-backup.log"
        )

    def test_log_file_configurable(self, script_content: str) -> None:
        assert re.search(r'LOG_FILE=.*:-', script_content), (
            "LOG_FILE should be configurable with a default"
        )

    def test_writes_to_log_file(self, script_content: str) -> None:
        assert "tee -a" in script_content, (
            "Script should append to log file (tee -a)"
        )

    def test_logs_start_marker(self, script_content: str) -> None:
        assert re.search(
            r'[Bb]ackup [Ss]tarted', script_content
        ), "Script should log a start marker"

    def test_logs_finish_marker(self, script_content: str) -> None:
        assert re.search(
            r'[Bb]ackup [Ff]inished', script_content
        ), "Script should log a finish marker"

    def test_logs_include_timestamp(self, script_content: str) -> None:
        # The log function should include a timestamp
        assert re.search(r"date.*%H:%M:%S", script_content), (
            "Log entries should include timestamps"
        )

    def test_logs_include_level(self, script_content: str) -> None:
        # Log function should accept and display a level (INFO, ERROR, etc.)
        assert "INFO" in script_content, "Logs should include INFO level entries"
        assert "ERROR" in script_content, "Logs should include ERROR level entries"


# -------------------------------------------------------------------------
# 7. Error handling & exit codes
# -------------------------------------------------------------------------
class TestErrorHandling:
    """Verify error handling and exit code behavior."""

    def test_trap_on_err(self, script_content: str) -> None:
        assert re.search(r"trap\s+'?.*ERR", script_content), (
            "Script must set a trap for ERR signals"
        )

    def test_exit_1_on_failure(self, script_content: str) -> None:
        assert "exit 1" in script_content, (
            "Script must exit 1 on backup failure"
        )

    def test_exit_2_on_s3_failure(self, script_content: str) -> None:
        assert "exit" in script_content, "Script must have exit statements"
        assert "S3_EXIT" in script_content, (
            "S3 failure should use a separate exit code variable"
        )

    def test_default_backup_dir(self, script_content: str) -> None:
        assert "/home/ec2-user/backups" in script_content, (
            "Default backup directory should be /home/ec2-user/backups"
        )


# -------------------------------------------------------------------------
# 8. Backup directory structure
# -------------------------------------------------------------------------
class TestDirectoryStructure:
    """Verify the backup directory structure."""

    def test_daily_subdirectory(self, script_content: str) -> None:
        assert re.search(
            r'DAILY_DIR=.*daily', script_content
        ), "DAILY_DIR should point to a 'daily' subdirectory"

    def test_weekly_subdirectory(self, script_content: str) -> None:
        assert re.search(
            r'WEEKLY_DIR=.*weekly', script_content
        ), "WEEKLY_DIR should point to a 'weekly' subdirectory"

    def test_daily_under_backup_dir(self, script_content: str) -> None:
        assert re.search(
            r'DAILY_DIR=.*BACKUP_DIR.*daily', script_content
        ), "DAILY_DIR should be a subdirectory of BACKUP_DIR"

    def test_weekly_under_backup_dir(self, script_content: str) -> None:
        assert re.search(
            r'WEEKLY_DIR=.*BACKUP_DIR.*weekly', script_content
        ), "WEEKLY_DIR should be a subdirectory of BACKUP_DIR"
