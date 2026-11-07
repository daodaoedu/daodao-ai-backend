"""JWT verification must preserve authentication results without logging claims."""

import io
import logging
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from collections.abc import Iterator

import jwt
import pytest

from src import verify_jwt

ROOT = Path(__file__).resolve().parents[3]
SECRET = secrets.token_urlsafe(32)
PRIVATE_ID = "qa158-private-user-identifier"
PRIVATE_UUID = "qa158-private-external-identifier"
PRIVATE_EMAIL = "qa158-private-identity@example.invalid"
PRIVATE_NOTE = "qa158-private-nested-claim"
CLI_DEBUG_CAPTURE = """
import logging
import runpy

original_set_level = logging.Logger.setLevel

def enable_debug(logger, requested_level):
    original_set_level(logger, logging.DEBUG)

# Keep the real logger/handlers; enable every level instead of suppressing logs.
logging.Logger.setLevel = enable_debug
runpy.run_module("src.verify_jwt", run_name="__main__")
"""


@pytest.fixture
def captured_verifier_logs(monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    """Capture the real non-propagating logger, including DEBUG-level records."""
    monkeypatch.setattr(verify_jwt, "JWT_SECURITY", SECRET)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = verify_jwt.logger
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        handler.close()


def signed_fixture(kind: str) -> tuple[str, dict[str, object]]:
    """Create synthetic claims and real signatures for each authentication outcome."""
    now = int(time.time())
    claims: dict[str, object] = {
        "id": PRIVATE_ID,
        "_id": PRIVATE_UUID,
        "email": PRIVATE_EMAIL,
        "isTemp": False,
        "iat": now - 600 if kind == "expired" else now,
        "exp": now - 300 if kind == "expired" else now + 300,
        "private": {"note": PRIVATE_NOTE},
    }
    signing_key = secrets.token_urlsafe(32) if kind == "invalid" else SECRET
    return jwt.encode(claims, signing_key, algorithm="HS256"), claims


def assert_no_private_values(output: str, token: str) -> None:
    """Inspect actual output text, not a filtered or structured logger mock."""
    for value in (
        token,
        token.split(".")[1],
        SECRET,
        PRIVATE_ID,
        PRIVATE_UUID,
        PRIVATE_EMAIL,
        PRIVATE_NOTE,
    ):
        assert value not in output


@pytest.mark.parametrize("kind", ["valid", "expired", "invalid"])
def test_verification_keeps_result_without_leaking_claims(
    kind: str,
    captured_verifier_logs: io.StringIO,
    capfd: pytest.CaptureFixture[str],
) -> None:
    token, claims = signed_fixture(kind)

    result = verify_jwt.verify(token)

    assert result == (claims if kind == "valid" else None)
    captured = capfd.readouterr()
    assert_no_private_values(
        captured_verifier_logs.getvalue() + captured.out + captured.err, token
    )


@pytest.mark.parametrize("kind", ["valid", "expired", "invalid"])
@pytest.mark.parametrize(
    "all_levels", [False, True], ids=["default-info", "debug-enabled"]
)
def test_cli_does_not_echo_token_or_payload(
    kind: str, all_levels: bool, tmp_path: Path
) -> None:
    token, _ = signed_fixture(kind)
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "JWT_SECURITY": SECRET,
        "MY_TOKEN_ID": token,
    }

    command = (
        [sys.executable, "-c", CLI_DEBUG_CAPTURE]
        if all_levels
        else [sys.executable, "-m", "src.verify_jwt"]
    )
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert_no_private_values(result.stdout + result.stderr, token)
