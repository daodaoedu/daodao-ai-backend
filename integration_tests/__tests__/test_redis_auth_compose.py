"""Exercise Redis auth from rendered deployment config in disposable containers.

Only image, entrypoint, command, environment and healthcheck are used. Deployment
container names, networks, host ports and persistent volumes are never reused.
"""

import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "synthetic-redis-auth-99"


def _run(*args, **kwargs):
    return subprocess.run(
        args, text=True, capture_output=True, timeout=30, check=False, **kwargs
    )


def _render(environment, env_file):
    clean_env = dict(os.environ)
    clean_env.pop("REDIS_PASSWORD", None)
    return _run(
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(ROOT / f"docker-compose.{environment}.yml"),
        "--profile",
        environment,
        "config",
        "--no-env-resolution",
        "--format",
        "json",
        f"redis-{environment}",
        env=clean_env,
    )


def _isolated_compose(service, tmp_path):
    # Compose's rendered command/healthcheck retain escaped dollars for reuse as
    # Compose input. Let Compose interpret them rather than emulate that parser.
    isolated = {
        key: service[key]
        for key in ("image", "entrypoint", "command", "environment", "healthcheck")
        if service.get(key) is not None
    }
    config = tmp_path / "isolated-compose.json"
    config.write_text(
        json.dumps(
            {
                "services": {"redis": isolated},
                "networks": {"default": {"internal": True}},
            }
        )
    )
    return [
        "docker",
        "compose",
        "--env-file",
        "/dev/null",
        "--project-name",
        f"daodao-ai99-regression-{uuid.uuid4().hex}",
        "-f",
        str(config),
    ]


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_deployment_refuses_missing_redis_password(environment, tmp_path):
    env_file = tmp_path / "empty.env"
    env_file.write_text("")
    result = _render(environment, env_file)
    assert result.returncode != 0, "Deployment accepted an absent Redis password"
    assert "REDIS_PASSWORD" in result.stderr


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_deployed_redis_rejects_anonymous_and_wrong_auth_but_is_healthy(
    environment, tmp_path
):
    env_file = tmp_path / "synthetic.env"
    env_file.write_text(f"REDIS_PASSWORD={PASSWORD}\n")
    rendered = _render(environment, env_file)
    assert rendered.returncode == 0, rendered.stderr
    service = json.loads(rendered.stdout)["services"][f"redis-{environment}"]
    assert not service.get("ports"), "Redis must not publish a host port"
    compose = _isolated_compose(service, tmp_path)
    try:
        started = _run(*compose, "up", "--detach")
        assert started.returncode == 0, started.stderr
        located = _run(*compose, "ps", "--quiet", "redis")
        assert located.returncode == 0, located.stderr
        name = located.stdout.strip()
        assert name
        runtime_uid = _run(
            "docker", "exec", name, "sh", "-c", "awk '/^Uid:/{print $2}' /proc/1/status"
        )
        redis_uid = _run("docker", "exec", name, "id", "-u", "redis")
        assert runtime_uid.returncode == redis_uid.returncode == 0
        assert runtime_uid.stdout.strip() == redis_uid.stdout.strip(), (
            "Redis must retain the official entrypoint's unprivileged runtime user"
        )
        deadline = time.monotonic() + 10
        while True:
            ping = _run("docker", "exec", name, "redis-cli", "ping")
            if "PONG" in ping.stdout or "NOAUTH" in ping.stdout:
                break
            assert time.monotonic() < deadline, ping.stderr
            time.sleep(0.1)

        assert "NOAUTH" in ping.stdout, "Anonymous client could read deployed Redis"
        wrong = _run(
            "docker",
            "exec",
            "--env",
            "REDISCLI_AUTH=wrong-secret",
            name,
            "redis-cli",
            "ping",
        )
        assert wrong.stdout.strip() != "PONG"
        assert "WRONGPASS" in wrong.stdout + wrong.stderr
        authenticated = _run(
            "docker",
            "exec",
            "--env",
            f"REDISCLI_AUTH={PASSWORD}",
            name,
            "redis-cli",
            "ping",
        )
        assert authenticated.returncode == 0, authenticated.stderr
        assert authenticated.stdout.strip() == "PONG"
        written = _run(
            "docker",
            "exec",
            "--env",
            f"REDISCLI_AUTH={PASSWORD}",
            name,
            "redis-cli",
            "SET",
            "qa99-key",
            "安全的測試快取🐾",
        )
        assert written.returncode == 0, written.stderr
        assert written.stdout.strip() == "OK"
        read = _run(
            "docker",
            "exec",
            "--env",
            f"REDISCLI_AUTH={PASSWORD}",
            name,
            "redis-cli",
            "--raw",
            "GET",
            "qa99-key",
        )
        assert read.returncode == 0, read.stderr
        assert read.stdout.strip() == "安全的測試快取🐾"

        inspected = _run("docker", "inspect", name)
        assert inspected.returncode == 0, inspected.stderr
        health = json.loads(inspected.stdout)[0]["Config"]["Healthcheck"]["Test"]
        if health[0] == "CMD":
            checked = _run("docker", "exec", name, *health[1:])
        else:
            assert health[0] == "CMD-SHELL"
            checked = _run("docker", "exec", name, "sh", "-c", health[1])
        assert checked.returncode == 0, checked.stderr
        invalid_health = _run(
            "docker",
            "exec",
            "--env",
            "REDIS_PASSWORD=wrong-secret",
            name,
            "sh",
            "-c",
            health[1],
        )
        assert invalid_health.returncode != 0, "Wrong credentials reported healthy"
    finally:
        removed = _run(*compose, "down", "--volumes", "--remove-orphans")
        assert removed.returncode == 0, removed.stderr
