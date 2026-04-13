from parsedwg.orm import Entity


def test_entity_has_parent_id_self_fk() -> None:
    parent_column = Entity.__table__.c.parent_id

    assert parent_column.nullable is True
    assert len(parent_column.foreign_keys) == 1

    fk = next(iter(parent_column.foreign_keys))
    assert fk.target_fullname == "entity.id"
