"""Persist resource timing independently from free-form notes."""

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.exc import IntegrityError

from src.models.EntityResource import EntityResource


@pytest.fixture
def resource_db():
    engine = create_engine("sqlite:///:memory:")
    EntityResource.__table__.create(engine)
    with engine.begin() as connection:
        yield connection
    engine.dispose()


@pytest.mark.parametrize("day_number", [None, 1, 3, 91])
def test_resource_date_round_trip_keeps_note(resource_db, day_number):
    table = EntityResource.__table__
    resource_db.execute(
        insert(table).values(
            resource_id=1,
            entity_type="practice",
            entity_id=1,
            created_by=1,
            day_number=day_number,
            note="下次記得整理重點",
        )
    )
    stored = resource_db.execute(select(table.c.day_number, table.c.note)).one()
    assert stored == (day_number, "下次記得整理重點")


@pytest.mark.parametrize("day_number", [0, -1, 92])
def test_resource_date_rejects_outside_supported_days(resource_db, day_number):
    with pytest.raises(IntegrityError):
        resource_db.execute(
            insert(EntityResource.__table__).values(
                resource_id=1,
                entity_type="practice",
                entity_id=1,
                created_by=1,
                day_number=day_number,
            )
        )
