"""HTTP log privacy with real handlers; DB/services/cache are explicit boundaries."""

import io
import json
import logging
from types import SimpleNamespace
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import jwt
import pytest

import src.dependencies as dependencies
from src.models.Practice import Practice
from src.models.User import User
from src.routers import users
import src.verify_jwt as verify_jwt


class CacheBoundary:
    def __init__(self, value, fail_write):
        self.value = value
        self.fail_write = fail_write
        self.reads = []
        self.writes = []

    def get(self, key):
        self.reads.append(key)
        return self.value

    def set(self, key, value, ex):
        self.writes.append((key, value, ex))
        if self.fail_write:
            raise RuntimeError("synthetic cache write failure")
        return True


class DatabaseBoundary:
    def __init__(self, user):
        self.user = user

    def query(self, model):
        assert model is User
        return self

    def filter(self, *_):
        return self

    def first(self):
        return self.user

    def execute(self, *_):
        return SimpleNamespace(fetchall=lambda: [])


@pytest.fixture(params=["ordinary", "unicode"])
def route_context(request, monkeypatch):
    if request.param == "ordinary":
        keyword, tag, title = (
            "qa131-private@example.invalid",
            "qa131-private-tag",
            "qa131-private-practice-title",
        )
    else:
        keyword, tag, title = "私人關鍵🧭131", "私人標籤🏝️131", "私人實踐標題🌱131"
    user = User(
        id=131031,
        external_id=uuid.UUID("f09b68ca-a1e5-4fb6-bdea-eae72cdfd371"),
        nickname="synthetic-private-owner-131",
    )
    practice = Practice(
        id=131041,
        external_id="5cd3bbe7-f34f-4af1-b8b5-d7c5e0f62df9",
        title=title,
        status="active",
        privacy_status="public",
        user=user,
    )
    secret = "synthetic-jwt-signing-secret-for-issue-131-only"
    monkeypatch.setattr(
        verify_jwt, "get_settings", lambda: SimpleNamespace(jwt_security=secret)
    )
    headers = {
        "Authorization": "Bearer "
        + jwt.encode({"id": str(user.external_id)}, secret, algorithm="HS256")
    }
    calls = []
    suggestions = {"popular_keywords": [keyword], "interest_tags": [tag]}
    completions = {
        "completions": [{"text": keyword, "type": "title"}],
        "next_word_suggestions": [],
        "query": keyword,
    }

    def list_service(**kwargs):
        calls.append(("list", kwargs))
        return [practice]

    def suggestions_service(**kwargs):
        calls.append(("suggestions", kwargs))
        return suggestions

    def completions_service(**kwargs):
        calls.append(("completions", kwargs))
        return completions

    monkeypatch.setattr(users.PracticeService, "get_practices", list_service)
    monkeypatch.setattr(
        users.PracticeService, "get_search_suggestions", suggestions_service
    )
    monkeypatch.setattr(users.PracticeService, "get_completions", completions_service)
    logger = users.logger
    previous_level, previous_disabled = logger.level, logger.disabled
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.setLevel(logging.DEBUG)
    logger.disabled = False
    logger.addHandler(handler)
    try:
        yield SimpleNamespace(
            keyword=keyword,
            tag=tag,
            title=title,
            user=user,
            practice=practice,
            headers=headers,
            calls=calls,
            suggestions=suggestions,
            completions=completions,
            logs=stream,
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.disabled = previous_disabled
        handler.close()


@pytest.mark.parametrize("endpoint", ["list", "completions", "suggestions"])
@pytest.mark.parametrize("scenario", ["miss", "invalid-json", "write-failure", "hit"])
def test_http_cache_and_payload_keep_private_values_out_of_logs(
    route_context, endpoint, scenario
):
    context = route_context
    if endpoint == "list":
        path = "/api/v1/users/practices"
        params = {"keyword": context.keyword, "tags": context.tag, "limit": 2}
        cached_data = [{"id": "cached-practice-131", "title": context.title}]
        cached = {"data": cached_data, "pagination": {"count": 1}}
        expected_key = (
            f"practices:user:{context.user.id}:kw:{context.keyword}:tags:{context.tag}"
            ":dur:-:status:__none__:sort:newest_updated:limit:2:offset:0:after:0"
        )
        ttl = 120
    elif endpoint == "completions":
        path = "/api/v1/users/practices/completions"
        params = {"q": f"  {context.keyword}  ", "limit": 7}
        cached_data = context.completions
        cached = cached_data
        expected_key = f"practice_completions:q:{context.keyword}:limit:7"
        ttl = 300
    else:
        path = "/api/v1/users/practices/suggestions"
        params = {}
        cached_data = context.suggestions
        cached = cached_data
        expected_key = f"practice_suggestions:{context.user.id}"
        ttl = 600
    cache_value = (
        json.dumps(cached)
        if scenario == "hit"
        else "{synthetic-invalid-json" if scenario == "invalid-json" else None
    )
    cache = CacheBoundary(cache_value, scenario == "write-failure")
    db = DatabaseBoundary(context.user)
    app = FastAPI()
    app.include_router(users.router, prefix="/api")
    app.dependency_overrides[dependencies.get_db_session] = lambda: db
    app.dependency_overrides[dependencies.get_cache_client] = lambda: SimpleNamespace(
        client=cache
    )
    with TestClient(app) as client:
        response = client.get(path, params=params, headers=context.headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["cacheHit"] is (scenario == "hit")
    assert cache.reads == [expected_key]
    if scenario == "hit":
        assert payload["data"] == cached_data
        assert context.calls == []
        assert cache.writes == []
    else:
        assert len(context.calls) == 1
        operation, arguments = context.calls[0]
        assert operation == endpoint
        assert len(cache.writes) == 1
        key, written, expiry = cache.writes[0]
        assert key == expected_key
        assert expiry == ttl
        if endpoint == "list":
            row = payload["data"][0]
            assert row["title"] == context.title
            assert row["id"] == context.practice.external_id
            assert row["user"]["name"] == context.user.nickname
            assert row["reactions"] == []
            assert row["is_brewing"] is False
            assert payload["pagination"]["count"] == 1
            assert payload["pagination"]["cursors"]["end"] == str(context.practice.id)
            assert arguments["keyword"] == context.keyword
            assert arguments["tags"] == [context.tag]
            assert json.loads(written)["data"][0]["title"] == context.title
        else:
            expected_data = (
                context.completions
                if endpoint == "completions"
                else context.suggestions
            )
            assert payload["data"] == expected_data
            assert json.loads(written) == expected_data
            if endpoint == "completions":
                assert arguments["prefix"] == context.keyword
                assert arguments["limit"] == 7
            else:
                assert arguments["user_id"] == context.user.id
    output = context.logs.getvalue()
    if scenario in ["invalid-json", "write-failure"]:
        assert "WARNING " in output
    for private in [
        context.keyword,
        context.tag,
        context.title,
        str(context.user.id),
        str(context.practice.id),
        expected_key,
    ]:
        assert private not in output
