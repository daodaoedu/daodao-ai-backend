"""Private search inputs must not be logged while filtering and ranking still work."""

from contextlib import contextmanager
import io
import logging
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, load_only

from src.models.Practice import Practice
from src.models.EntityTag import EntityTag, EntityTagType
from src.services.practice import practice, recommendation

PRACTICE_IDS = [99131, 99132, 99133]
TAG_ID = 987654


@contextmanager
def capture_logs(logger):
    previous_level, previous_disabled = logger.level, logger.disabled
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    logger.setLevel(logging.DEBUG)
    logger.disabled = False
    logger.addHandler(handler)
    try:
        yield output
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.disabled = previous_disabled
        handler.close()


@pytest.fixture(params=["qa131-private@example.invalid", "私人標籤與標題🧭qa131"])
def private_practices(request):
    marker = request.param
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            for ddl in [
                "CREATE TABLE practices (id INTEGER PRIMARY KEY, title TEXT, "
                "has_resources BOOLEAN, progress_percentage NUMERIC, "
                "template_id INTEGER, updated_at TIMESTAMP, created_at TIMESTAMP, "
                "duration_days INTEGER, status TEXT)",
                "CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT)",
                "CREATE TABLE entity_tags (id INTEGER PRIMARY KEY, tag_id INTEGER, "
                "entity_type TEXT, entity_id INTEGER)",
                "CREATE TABLE practice_checkins (id INTEGER PRIMARY KEY, "
                "practice_id INTEGER, user_id INTEGER, created_at TIMESTAMP)",
            ]:
                connection.exec_driver_sql(ddl)
            connection.exec_driver_sql(
                "INSERT INTO practices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (99131, f"Low {marker}", False, 0, None, None, None, 2, "active"),
                    (
                        99132,
                        f"Middle {marker}",
                        True,
                        0,
                        None,
                        None,
                        None,
                        5,
                        "completed",
                    ),
                    (
                        99133,
                        f"High {marker}",
                        True,
                        100,
                        1,
                        None,
                        None,
                        10,
                        "completed",
                    ),
                ],
            )
            connection.exec_driver_sql(
                "INSERT INTO tags VALUES (?, ?)", (TAG_ID, marker)
            )
            connection.execute(
                EntityTag.__table__.insert().values(
                    id=1,
                    tag_id=TAG_ID,
                    entity_type=EntityTagType.PRACTICE,
                    entity_id=99132,
                )
            )
        with Session(engine) as session:
            yield session, marker
    finally:
        engine.dispose()


@pytest.mark.parametrize("matching", [True, False])
def test_tag_filter_logs_exclude_private_tags_and_resolved_ids(
    private_practices, matching
):
    session, marker = private_practices
    tag = marker if matching else f"missing {marker}"
    with capture_logs(practice.logger) as logs:
        query = practice.PracticeService._apply_filters(
            session.query(Practice.id), [tag], None, None, None
        )
        result = [row.id for row in query.order_by(Practice.id).all()]
    # Unknown tags currently leave the query unchanged; this task preserves that policy.
    assert result == ([99132] if matching else PRACTICE_IDS)
    if not matching:
        assert "WARNING:" in logs.getvalue()
    assert marker not in logs.getvalue()
    assert str(TAG_ID) not in logs.getvalue()


def test_other_filter_results_remain_intact(private_practices):
    session, _ = private_practices
    query = practice.PracticeService._apply_filters(
        session.query(Practice.id), None, 2, 8, "completed"
    )
    assert [row.id for row in query.all()] == [99132]


def test_recommendations_preserve_ranking_without_item_metadata_logs(private_practices):
    session, marker = private_practices
    query = session.query(Practice).options(
        load_only(
            Practice.id,
            Practice.title,
            Practice.has_resources,
            Practice.progress_percentage,
            Practice.template_id,
            Practice.updated_at,
            Practice.created_at,
        )
    )
    with capture_logs(logging.getLogger(recommendation.__name__)) as logs:
        ranked = recommendation.recommand_practices(
            session, SimpleNamespace(id=81231), query.order_by(Practice.id)
        )
    # Equal freshness and no checkins isolate the documented resource/progress signals.
    assert [row.id for row in ranked] == [99133, 99132, 99131]
    assert [row.title for row in ranked] == [
        f"High {marker}",
        f"Middle {marker}",
        f"Low {marker}",
    ]
    output = logs.getvalue()
    assert marker not in output
    assert all(str(identifier) not in output for identifier in PRACTICE_IDS)
    assert "practice id:" not in output.casefold()
    assert "score:" not in output.casefold()
