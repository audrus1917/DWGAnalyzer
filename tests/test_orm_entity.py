from sqlalchemy.dialects.postgresql import TSVECTOR

from parsedwg.orm import Entity


def test_entity_has_parent_id_self_fk() -> None:
    parent_column = Entity.__table__.c.parent_id

    assert parent_column.nullable is True
    assert len(parent_column.foreign_keys) == 1

    fk = next(iter(parent_column.foreign_keys))
    assert fk.target_fullname == "entity.id"


def test_entity_has_file_md5_column() -> None:
    file_md5_column = Entity.__table__.c.file_md5

    assert file_md5_column.nullable is True
    assert file_md5_column.type.length == 32


def test_entity_has_is_table_column() -> None:
    is_table_column = Entity.__table__.c.is_table

    assert is_table_column.nullable is True


def test_entity_has_entity_text_tsvector_column() -> None:
    entity_text_column = Entity.__table__.c.entity_text

    assert entity_text_column.nullable is True
    assert isinstance(entity_text_column.type, TSVECTOR)
