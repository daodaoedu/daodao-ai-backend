"""Search must retain its results without putting private inputs in application logs."""

import io
import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models.Practice import Practice
from src.services.practice import practice


@pytest.fixture(params=["qa123-private@example.invalid", "私人搜尋🧭qa123"])
def search_dataset(request):
    keyword = request.param
    engine = create_engine("sqlite:///:memory:")
    tables = [
        "CREATE TABLE practices (id INTEGER PRIMARY KEY, title TEXT, "
        "practice_action TEXT, privacy_status TEXT, status TEXT)",
        "CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT)",
        "CREATE TABLE entity_tags (id INTEGER PRIMARY KEY, tag_id INTEGER, "
        "entity_type TEXT, entity_id INTEGER)",
        "CREATE TABLE resources (id INTEGER PRIMARY KEY, name TEXT)",
        "CREATE TABLE entity_resources (id INTEGER PRIMARY KEY, resource_id INTEGER, "
        "entity_type TEXT, entity_id INTEGER)",
        "CREATE TABLE practice_checkins (id INTEGER PRIMARY KEY, practice_id INTEGER, "
        "note TEXT)",
    ]
    try:
        with engine.begin() as connection:
            for statement in tables:
                connection.exec_driver_sql(statement)
            for practice_id in range(1, 8):
                connection.exec_driver_sql(
                    "INSERT INTO practices VALUES (?, ?, ?, ?, ?)",
                    (
                        practice_id,
                        f"title {keyword}" if practice_id == 1 else "unrelated title",
                        f"action {keyword}" if practice_id == 2 else "unrelated action",
                        "delayed" if practice_id == 6 else "public",
                        "active",
                    ),
                )
            connection.exec_driver_sql("INSERT INTO tags VALUES (1, ?)", (keyword,))
            connection.exec_driver_sql(
                "INSERT INTO entity_tags VALUES (1, 1, 'practice', 3)"
            )
            connection.exec_driver_sql(
                "INSERT INTO resources VALUES (1, ?)", (keyword,)
            )
            connection.exec_driver_sql(
                "INSERT INTO entity_resources VALUES (1, 1, 'practice', 4)"
            )
            connection.exec_driver_sql(
                "INSERT INTO practice_checkins VALUES (?, ?, ?)",
                [(1, 5, keyword), (2, 6, keyword)],
            )
        with Session(engine) as session:
            yield session, keyword
    finally:
        engine.dispose()


@pytest.fixture
def captured_search_logs():
    logger = practice.logger
    previous_level, previous_disabled = logger.level, logger.disabled
    output = io.StringIO()
    handler = logging.StreamHandler(output)
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


def test_search_keyword_and_literal_sql_are_absent_at_all_log_levels(
    search_dataset, captured_search_logs
):
    session, keyword = search_dataset
    query = practice.PracticeService._build_base_query(
        session.query(Practice.id), keyword
    )
    assert [row.id for row in query.order_by(Practice.id).all()] == [1, 2, 3, 4, 5]
    output = captured_search_logs.getvalue()
    assert keyword not in output
    lowered_output = output.lower()
    assert not ("select" in lowered_output and "practices.title" in lowered_output)


def test_search_matches_each_field_without_disclosing_brewing_checkins(search_dataset):
    session, keyword = search_dataset
    query = practice.PracticeService._build_base_query(
        session.query(Practice.id), keyword
    )
    assert [row.id for row in query.order_by(Practice.id).all()] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("keyword", [None, ""])
def test_empty_keyword_preserves_the_unfiltered_query(search_dataset, keyword):
    session, _ = search_dataset
    query = practice.PracticeService._build_base_query(
        session.query(Practice.id), keyword
    )
    assert [row.id for row in query.order_by(Practice.id).all()] == list(range(1, 8))
