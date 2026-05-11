from parsedwg.cli import main


def test_main_project_add_runs_pipeline(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_create_project(name: str, description: str | None = None, created_by: str | None = None):
        captured_kwargs["name"] = name
        captured_kwargs["description"] = description
        captured_kwargs["created_by"] = created_by
        return {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": name,
            "description": description or "",
            "created_by": created_by or "",
        }

    monkeypatch.setattr("parsedwg.db.create_project", fake_create_project)

    exit_code = main(["project-add", "Башня А", "--description", "Описание", "--created-by", "andrus"])

    assert exit_code == 0
    assert captured_kwargs == {
        "name": "Башня А",
        "description": "Описание",
        "created_by": "andrus",
    }
    assert "Проект создан" in capsys.readouterr().out


def test_main_project_delete_requires_confirmation(monkeypatch, capsys) -> None:
    async def fake_delete_project(project_id: str) -> bool:
        _ = project_id
        return True

    monkeypatch.setattr("parsedwg.db.delete_project", fake_delete_project)
    monkeypatch.setattr("builtins.input", lambda _prompt: "NO")

    exit_code = main(["project-delete", "11111111-1111-1111-1111-111111111111"])

    assert exit_code == 1
    assert "Удаление отменено." in capsys.readouterr().out


def test_main_project_delete_with_yes(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_delete_project(project_id: str) -> bool:
        captured_kwargs["project_id"] = project_id
        return True

    monkeypatch.setattr("parsedwg.db.delete_project", fake_delete_project)

    exit_code = main(["project-delete", "11111111-1111-1111-1111-111111111111", "--yes"])

    assert exit_code == 0
    assert captured_kwargs == {"project_id": "11111111-1111-1111-1111-111111111111"}
    assert "Проект удалён" in capsys.readouterr().out


def test_main_category_add_runs_pipeline(monkeypatch, capsys) -> None:
    captured_kwargs: dict[str, object] = {}

    async def fake_create_category(
        name: str,
        description: str | None = None,
        parent_id: str | None = None,
    ):
        captured_kwargs["name"] = name
        captured_kwargs["description"] = description
        captured_kwargs["parent_id"] = parent_id
        return {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": name,
            "description": description or "",
            "parent_id": parent_id or "",
        }

    monkeypatch.setattr("parsedwg.db.create_category", fake_create_category)

    exit_code = main([
        "category-add",
        "Архитектура",
        "--description",
        "Разделы по архитектуре",
        "--parent-id",
        "11111111-1111-1111-1111-111111111111",
    ])

    assert exit_code == 0
    assert captured_kwargs == {
        "name": "Архитектура",
        "description": "Разделы по архитектуре",
        "parent_id": "11111111-1111-1111-1111-111111111111",
    }
    assert "Категория создана" in capsys.readouterr().out


def test_main_category_delete_requires_confirmation(monkeypatch, capsys) -> None:
    async def fake_delete_category(category_id: str) -> bool:
        _ = category_id
        return True

    monkeypatch.setattr("parsedwg.db.delete_category", fake_delete_category)
    monkeypatch.setattr("builtins.input", lambda _prompt: "NO")

    exit_code = main(["category-delete", "22222222-2222-2222-2222-222222222222"])

    assert exit_code == 1
    assert "Удаление отменено." in capsys.readouterr().out


def test_main_category_list_handles_empty_result(monkeypatch, capsys) -> None:
    async def fake_list_categories(parent_id: str | None = None):
        assert parent_id is None
        return []

    monkeypatch.setattr("parsedwg.db.list_categories", fake_list_categories)

    exit_code = main(["category-list"])

    assert exit_code == 0
    assert "Нет категорий." in capsys.readouterr().out