from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import ARRAY

from parsedwg.orm import Category, Entity, EntityEmbedding, Project, category_to_entity


def test_entity_has_parent_id_self_fk() -> None:
    parent_column = Entity.__table__.c.parent_id

    assert parent_column.nullable is True
    assert len(parent_column.foreign_keys) == 1

    fk = next(iter(parent_column.foreign_keys))
    assert fk.target_fullname == "entity.id"


def test_entity_has_file_id_self_fk() -> None:
    file_column = Entity.__table__.c.file_id

    assert file_column.nullable is True
    assert len(file_column.foreign_keys) == 1

    fk = next(iter(file_column.foreign_keys))
    assert fk.target_fullname == "entity.id"


def test_entity_has_entity_md5_column() -> None:
    entity_md5_column = Entity.__table__.c.entity_md5

    assert entity_md5_column.nullable is True
    assert entity_md5_column.type.length == 32


def test_entity_has_is_table_column() -> None:
    is_table_column = Entity.__table__.c.is_table

    assert is_table_column.nullable is True


def test_entity_embedding_has_entity_text_tsvector_column() -> None:
    entity_text_column = EntityEmbedding.__table__.c.entity_text

    assert entity_text_column.nullable is True
    assert isinstance(entity_text_column.type, TSVECTOR)


def test_entity_embedding_has_entity_fk() -> None:
    entity_id_column = EntityEmbedding.__table__.c.entity_id

    assert entity_id_column.nullable is False
    fk = next(iter(entity_id_column.foreign_keys))
    assert fk.target_fullname == "entity.id"


def test_entity_uses_self_fks_for_hierarchy_and_file_scope() -> None:
    parent_id_column = Entity.__table__.c.parent_id
    file_id_column = Entity.__table__.c.file_id

    assert parent_id_column.nullable is True
    assert next(iter(parent_id_column.foreign_keys)).target_fullname == "entity.id"
    assert file_id_column.nullable is True
    assert next(iter(file_id_column.foreign_keys)).target_fullname == "entity.id"


def test_entity_has_embedding_relationship_only() -> None:
    assert "embedding_data" in Entity.__mapper__.relationships
    assert "primitives" not in Entity.__mapper__.relationships


def test_entity_has_required_columns() -> None:
    columns = Entity.__table__.c

    assert "id" in columns
    assert "entity_type" in columns
    assert "name" in columns
    assert "data" in columns
    assert "created_at" in columns


def test_entity_has_project_id_fk() -> None:
    project_column = Entity.__table__.c.project_id

    assert project_column.nullable is True
    assert len(project_column.foreign_keys) == 1

    fk = next(iter(project_column.foreign_keys))
    assert fk.target_fullname == "project.id"


def test_category_has_parent_id_self_fk() -> None:
    parent_column = Category.__table__.c.parent_id

    assert parent_column.nullable is True
    assert len(parent_column.foreign_keys) == 1

    fk = next(iter(parent_column.foreign_keys))
    assert fk.target_fullname == "category.id"


def test_category_has_required_columns() -> None:
    columns = Category.__table__.c

    assert "name" in columns
    assert "description" in columns
    assert "parent_id" in columns
    assert "aliases" in columns
    assert isinstance(columns.aliases.type, ARRAY)


def test_category_to_entity_has_required_fks() -> None:
    category_fk = next(iter(category_to_entity.c.category_id.foreign_keys))
    entity_fk = next(iter(category_to_entity.c.entity_id.foreign_keys))

    assert category_fk.target_fullname == "category.id"
    assert entity_fk.target_fullname == "entity.id"


def test_entity_has_categories_relationship() -> None:
    assert "categories" in Entity.__mapper__.relationships


def test_category_has_entities_relationship() -> None:
    assert "entities" in Category.__mapper__.relationships


def test_project_has_required_columns() -> None:
    columns = Project.__table__.c

    assert "name" in columns
    assert "description" in columns
    assert "created_by" in columns
    assert "created_at" in columns
