"""Run the actual feed pool SQL against disposable PostgreSQL role fixtures.

Explicit CI entrypoint; TEST_DATABASE_URL is required and must point to loopback
or a temporary Unix socket. This suite is outside make test's tests/ directory.
It does not bootstrap the application, execute migrations, or use cloud data.
"""

import os
from collections.abc import Iterator
from typing import Callable
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url

from src.services.feed.feed_service import FeedService
from src.services.feed.space_filter import SpaceFilter

OWNER = 1
PEER = 10
OTHER_COHORT_MEMBER = 11
LEFT_MEMBER = 12
REMOVED_MEMBER = 13
OUTSIDER = 14
COHORT = 100
PRIVATE_PRACTICE = 1000
PUBLIC_PRACTICE = 1005
COMPLETED_DELAYED = 1006
PUBLIC_IDS = {PUBLIC_PRACTICE, COMPLETED_DELAYED}


@pytest.fixture(scope="module")
def database() -> Iterator[Connection]:
    """Keep all DDL/data in one random schema and roll back the whole fixture."""
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not raw_url:
        pytest.fail("TEST_DATABASE_URL is required for the PostgreSQL ACL suite")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("The ACL suite requires real PostgreSQL")
    socket = str(url.query.get("host", ""))
    is_local = url.host in {"localhost", "127.0.0.1", "::1"}
    is_temp_socket = url.host is None and socket.startswith(("/tmp/", "/private/tmp/"))
    if not (is_local or is_temp_socket):
        pytest.fail("TEST_DATABASE_URL must use loopback or a temporary Unix socket")

    engine = create_engine(url)
    schema = "acl_test_" + uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            # schema is generated hex only, never taken from connection/user input.
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
            connection.execute(
                text(
                    """
                    CREATE TABLE programs (id integer PRIMARY KEY, kind text NOT NULL);
                    CREATE TABLE cohorts (
                        id integer PRIMARY KEY, program_id integer NOT NULL,
                        end_date date NOT NULL
                    );
                    CREATE TABLE cohort_enrollments (
                        cohort_id integer NOT NULL, user_id integer NOT NULL,
                        status text NOT NULL, PRIMARY KEY (cohort_id, user_id)
                    );
                    CREATE TABLE practices (
                        id integer PRIMARY KEY, user_id integer NOT NULL,
                        cohort_id integer, privacy_status text NOT NULL,
                        status text NOT NULL, deleted_at timestamptz,
                        title text DEFAULT 'ACL fixture', practice_action text DEFAULT 'Practice',
                        created_at timestamptz DEFAULT NOW(), updated_at timestamptz DEFAULT NOW(),
                        is_featured boolean DEFAULT false,
                        featured_start_at timestamptz, featured_end_at timestamptz
                    );
                    CREATE TABLE practice_checkins (
                        id integer PRIMARY KEY, practice_id integer NOT NULL,
                        user_id integer NOT NULL, created_at timestamptz DEFAULT NOW(),
                        note text DEFAULT 'Fixture check-in'
                    );
                    CREATE TABLE reactions (
                        id integer PRIMARY KEY, target_type text NOT NULL,
                        target_id integer NOT NULL
                    );
                    CREATE TABLE comments (
                        id integer PRIMARY KEY, target_type text NOT NULL,
                        target_id integer NOT NULL, visibility text NOT NULL
                    );
                    INSERT INTO programs VALUES (1, 'lighthouse'), (2, 'challenge');
                    INSERT INTO cohorts VALUES
                        (100, 1, CURRENT_DATE + 7),
                        (101, 1, CURRENT_DATE + 7),
                        (102, 2, CURRENT_DATE + 7),
                        (103, 1, CURRENT_DATE - 90),
                        (104, 1, CURRENT_DATE - 91);
                    INSERT INTO cohort_enrollments VALUES
                        (100, 1, 'joined'), (100, 10, 'joined'),
                        (101, 11, 'joined'), (100, 12, 'left'), (100, 13, 'removed'),
                        (101, 1, 'joined'), (102, 1, 'joined'),
                        (103, 1, 'joined'), (104, 1, 'joined');
                    INSERT INTO practices (id, user_id, cohort_id, privacy_status, status) VALUES
                        (1000, 1, 100, 'private', 'active'),
                        (1001, 1, 101, 'private', 'active'),
                        (1002, 1, 102, 'private', 'active'),
                        (1003, 1, NULL, 'private', 'active'),
                        (1004, 1, 100, 'private', 'draft'),
                        (1005, 1, 100, 'public', 'active'),
                        (1006, 1, 100, 'delayed', 'completed'),
                        (1007, 1, 100, 'delayed', 'active'),
                        (1008, 1, 103, 'private', 'active'),
                        (1009, 1, 104, 'private', 'active'),
                        (1010, 1, 100, 'private', 'active');
                    UPDATE practices SET deleted_at = NOW() WHERE id = 1010;
                    INSERT INTO practice_checkins (id, practice_id, user_id)
                        SELECT id + 10000, id, user_id FROM practices;
                    INSERT INTO comments VALUES
                        (1, 'practice', 1000, 'public'),
                        (2, 'practice', 1000, 'private'),
                        (3, 'checkin', 11000, 'public'),
                        (4, 'checkin', 11000, 'private');
                    """
                )
            )
            yield connection
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.fixture(params=["practice", "checkin"])
def pool(request: pytest.FixtureRequest) -> tuple[Callable, int]:
    """Use both production query builders, retaining a common practice ID assertion."""
    if request.param == "practice":
        return FeedService._fetch_practice_pool, 0
    return FeedService._fetch_checkin_pool_with_counts, 10000


def rows_for(
    database: Connection,
    pool: tuple[Callable, int],
    requester: int | None,
    space_filter: SpaceFilter | None = SpaceFilter(cohort_ids=(COHORT,)),
) -> dict[int, object]:
    """Execute production SQL; never substitute a policy query in this test."""
    query, offset = pool
    rows = query(
        database, None, None, 100, space_filter=space_filter, requester_id=requester
    )
    return {row.item_id - offset: row for row in rows}


@pytest.mark.parametrize("requester", [OWNER, PEER])
def test_owner_and_joined_peer_read_selected_private_content(database, pool, requester):
    rows = rows_for(database, pool, requester)
    assert set(rows) == {PRIVATE_PRACTICE, *PUBLIC_IDS}
    assert rows[PRIVATE_PRACTICE].comments_count == 1  # private comment never counted


@pytest.mark.parametrize(
    "requester", [OTHER_COHORT_MEMBER, LEFT_MEMBER, REMOVED_MEMBER, OUTSIDER, None]
)
def test_private_content_absent_for_unauthorized_roles(database, pool, requester):
    # Raw pools preserve public visibility; top-level service separately limits
    # selected cohort IDs to joined memberships. Neither may expose this private row.
    assert set(rows_for(database, pool, requester)) == PUBLIC_IDS


def test_selected_cohort_does_not_reveal_other_joined_cohort(database, pool):
    assert 1001 not in rows_for(database, pool, OWNER)
    assert set(rows_for(database, pool, OWNER, SpaceFilter(cohort_ids=(101,)))) == {
        1001
    }


def test_mixed_selection_keeps_personal_and_challenge_private_content_hidden(
    database, pool
):
    rows = rows_for(
        database,
        pool,
        OWNER,
        SpaceFilter(personal=True, challenge=True, cohort_ids=(100, 102)),
    )
    assert set(rows) == {PRIVATE_PRACTICE, *PUBLIC_IDS}
    assert not {1002, 1003, 1004, 1007, 1010} & rows.keys()


def test_unfiltered_feed_does_not_gain_private_content(database, pool):
    assert set(rows_for(database, pool, OWNER, None)) == PUBLIC_IDS


def test_retention_boundary_keeps_day_90_and_excludes_day_91(database, pool):
    rows = rows_for(database, pool, OWNER, SpaceFilter(cohort_ids=(103, 104)))
    assert set(rows) == {1008}


@pytest.mark.parametrize("timezone", ["Pacific/Kiritimati", "Etc/GMT+12"])
def test_retention_uses_utc_calendar_when_database_timezone_differs(
    database, pool, timezone
):
    # set_config(..., true) is transaction-local, equivalent to SET LOCAL TIME ZONE.
    # At least one of UTC+14/UTC-12 has a different calendar date from UTC.
    database.execute(
        text("SELECT set_config('TimeZone', :timezone, true)"), {"timezone": timezone}
    )
    try:
        rows = rows_for(database, pool, OWNER, SpaceFilter(cohort_ids=(103, 104)))
        assert set(rows) == {1008}
    finally:
        database.execute(text("SET LOCAL TIME ZONE 'UTC'"))


def test_membership_revocation_takes_effect_on_next_query(database, pool):
    assert PRIVATE_PRACTICE in rows_for(database, pool, PEER)
    database.execute(
        text("UPDATE cohort_enrollments SET status = 'left' WHERE user_id = :user"),
        {"user": PEER},
    )
    try:
        assert set(rows_for(database, pool, PEER)) == PUBLIC_IDS
    finally:
        database.execute(
            text(
                "UPDATE cohort_enrollments SET status = 'joined' WHERE user_id = :user"
            ),
            {"user": PEER},
        )
