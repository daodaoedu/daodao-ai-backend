"""
安全規範 regression (tasks 11.5 + 12.1/12.3/12.4/12.7):
DB 唯讀（prod + dev）、批次上限、憑證供裝優先序、容量護欄、檔案 TTL。
"""

import time

import pytest

from src.services.agent.capacity import CapacityError, check_capacity, ensure_capacity
from src.services.agent.credentials import is_connector_allowed, resolve_credential
from src.services.agent.tools.db import assert_readonly_sql
from src.services.agent.tools.email import BULK_EMAIL_LIMIT, bulk_send_emails
from src.services.agent.tools.files import cleanup_expired_files, write_scratch_file


class TestReadonlyDb:

    @pytest.mark.parametrize("env", ["prod", "dev"])
    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO users (nickname) VALUES ('x')",
            "UPDATE practices SET status = 'archived'",
            "DELETE FROM email_logs",
            "DROP TABLE users",
            "TRUNCATE practices",
        ],
    )
    def test_writes_rejected_on_all_envs(self, env, sql):
        with pytest.raises(ValueError):
            assert_readonly_sql(sql, env)

    @pytest.mark.parametrize("env", ["prod", "dev"])
    def test_select_and_cte_allowed(self, env):
        assert_readonly_sql("SELECT * FROM practices", env)
        assert_readonly_sql("WITH x AS (SELECT 1) SELECT * FROM x", env)
        assert_readonly_sql("  select id from users;  ", env)

    def test_multi_statement_smuggling_rejected(self):
        with pytest.raises(ValueError):
            assert_readonly_sql("SELECT 1; DELETE FROM users", "prod")


class TestBulkLimit:

    @pytest.mark.asyncio
    async def test_over_limit_requires_second_confirmation(self):
        emails = [{"to": f"u{i}@x.tw", "subject": "s", "html": "h"} for i in range(501)]
        with pytest.raises(ValueError, match="second confirmation"):
            await bulk_send_emails(emails, api_base="http://x", admin_token="t")

    @pytest.mark.asyncio
    async def test_over_limit_passes_with_confirmation_in_dry_run(self):
        emails = [{"to": f"u{i}@x.tw", "subject": "s", "html": "h"} for i in range(501)]
        result = await bulk_send_emails(
            emails, api_base="http://x", admin_token="t",
            dry_run=True, confirmed_over_limit=True,
        )
        assert result["dry_run"] is True
        assert result["total"] == 501

    @pytest.mark.asyncio
    async def test_at_limit_no_confirmation_needed(self):
        emails = [{"to": f"u{i}@x.tw", "subject": "s", "html": "h"} for i in range(BULK_EMAIL_LIMIT)]
        result = await bulk_send_emails(emails, api_base="http://x", admin_token="t", dry_run=True)
        assert result["total"] == BULK_EMAIL_LIMIT


class TestCredentialProvisioning:

    def test_precedence_config_over_db_over_env(self):
        # config > db > env（D13）
        value = resolve_credential(
            "NOTION_TOKEN",
            config_credentials={"NOTION_TOKEN": "from-config"},
            db_lookup=lambda _: "from-db",
            env={"NOTION_TOKEN": "from-env"},
        )
        assert value == "from-config"

    def test_db_wins_over_env_when_config_missing(self):
        value = resolve_credential(
            "NOTION_TOKEN",
            config_credentials={},
            db_lookup=lambda _: "from-db",
            env={"NOTION_TOKEN": "from-env"},
        )
        assert value == "from-db"

    def test_env_is_last_resort(self):
        value = resolve_credential(
            "NOTION_TOKEN", config_credentials={}, db_lookup=lambda _: None,
            env={"NOTION_TOKEN": "from-env"},
        )
        assert value == "from-env"

    def test_missing_everywhere_returns_none(self):
        assert resolve_credential("NOPE", env={}) is None

    def test_connector_denied_without_role(self):
        # connector 依角色綁定，未列出的一律拒絕
        roles = {"notion": frozenset({"admin"})}
        assert is_connector_allowed("notion", frozenset({"member"}), roles) is False
        assert is_connector_allowed("notion", frozenset({"admin"}), roles) is True
        assert is_connector_allowed("unknown", frozenset({"admin"}), roles) is False


class TestCapacityGuard:

    def test_normal_thresholds_pass(self):
        status = check_capacity(min_free_memory_mb=1, min_free_disk_mb=1)
        assert status.ok is True

    def test_impossible_threshold_fails(self):
        status = check_capacity(min_free_memory_mb=10**9, min_free_disk_mb=1)
        assert status.ok is False
        assert "memory" in status.reason

    def test_ensure_capacity_raises(self):
        with pytest.raises(CapacityError):
            ensure_capacity(min_free_memory_mb=10**9)


class TestScratchFileTtl:

    def test_expired_files_removed_fresh_kept(self, tmp_path):
        old = write_scratch_file("old-report.md", "old", scratch_dir=tmp_path)
        fresh = write_scratch_file("fresh-report.md", "fresh", scratch_dir=tmp_path)

        # 把 old 檔案 mtime 撥回 31 天前
        past = time.time() - 31 * 86400
        import os

        os.utime(old, (past, past))

        removed = cleanup_expired_files(scratch_dir=tmp_path, ttl_days=30)

        assert removed == ["old-report.md"]
        assert not old.exists()
        assert fresh.exists()

    def test_path_escape_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            write_scratch_file("../evil.sh", "x", scratch_dir=tmp_path)
