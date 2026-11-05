"""Tests for actions.shopping_list — local shopping list management."""
from __future__ import annotations

import json
import pytest

from actions.shopping_list import (
    _action_add,
    _action_all_lists,
    _action_check,
    _action_clear,
    _action_list,
    _action_remove,
    shopping_list,
)


@pytest.fixture(autouse=True)
def isolated_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_LISTS_DIR", str(tmp_path))
    yield


# ---------------------------------------------------------------------------
# TestActionAdd


class TestActionAdd:
    def test_add_item(self):
        result = _action_add("leche")
        assert "leche" in result.lower()

    def test_add_with_quantity(self):
        result = _action_add("huevos", quantity="12")
        assert "huevos" in result.lower()
        assert "12" in result

    def test_duplicate_no_change(self):
        _action_add("pan")
        result = _action_add("pan")
        assert "ya está" in result.lower()

    def test_duplicate_updates_quantity(self):
        _action_add("leche")
        result = _action_add("leche", quantity="2L")
        assert "actualizada" in result.lower() or "cantidad" in result.lower()

    def test_empty_item_error(self):
        result = _action_add("")
        assert "especifica" in result.lower()

    def test_custom_list_name(self):
        result = _action_add("destornillador", list_name="herramientas")
        assert "herramientas" in result.lower()

    def test_persisted(self, tmp_path):
        _action_add("mantequilla")
        from actions.shopping_list import _load
        items = _load("compra")
        assert any(i["item"] == "mantequilla" for i in items)


# ---------------------------------------------------------------------------
# TestActionRemove


class TestActionRemove:
    def test_remove_existing(self):
        _action_add("tomate")
        result = _action_remove("tomate")
        assert "eliminado" in result.lower()

    def test_remove_nonexistent(self):
        result = _action_remove("unicornio")
        assert "no estaba" in result.lower()

    def test_empty_item_error(self):
        result = _action_remove("")
        assert "especifica" in result.lower()

    def test_remove_case_insensitive(self):
        _action_add("Manzana")
        result = _action_remove("manzana")
        assert "eliminado" in result.lower()


# ---------------------------------------------------------------------------
# TestActionCheck


class TestActionCheck:
    def test_check_existing(self):
        _action_add("queso")
        result = _action_check("queso")
        assert "comprado" in result.lower() or "✓" in result

    def test_uncheck(self):
        _action_add("yogur")
        _action_check("yogur", done=True)
        result = _action_check("yogur", done=False)
        assert "pendiente" in result.lower()

    def test_check_nonexistent(self):
        result = _action_check("platano")
        assert "no está" in result.lower()

    def test_empty_item_error(self):
        result = _action_check("")
        assert "especifica" in result.lower()


# ---------------------------------------------------------------------------
# TestActionList


class TestActionList:
    def test_empty_list(self):
        result = _action_list()
        assert "vacía" in result.lower()

    def test_shows_items(self):
        _action_add("arroz")
        _action_add("aceite")
        result = _action_list()
        assert "arroz" in result
        assert "aceite" in result

    def test_separates_done_pending(self):
        _action_add("sal")
        _action_add("pimienta")
        _action_check("sal", done=True)
        result = _action_list()
        assert "pendientes" in result.lower() or "○" in result
        assert "comprados" in result.lower() or "✓" in result

    def test_custom_list(self):
        _action_add("martillo", list_name="bricolaje")
        result = _action_list(list_name="bricolaje")
        assert "martillo" in result


# ---------------------------------------------------------------------------
# TestActionClear


class TestActionClear:
    def test_clear_all(self):
        _action_add("patatas")
        _action_add("cebollas")
        result = _action_clear()
        assert "vaciada" in result.lower() or "eliminados" in result.lower()
        assert _action_list() and "vacía" in _action_list().lower()

    def test_clear_only_done(self):
        _action_add("ajo")
        _action_add("pimiento")
        _action_check("ajo", done=True)
        result = _action_clear(only_done=True)
        remaining = _action_list()
        assert "pimiento" in remaining
        assert "ajo" not in remaining

    def test_clear_empty(self):
        result = _action_clear()
        assert "vacía" in result.lower()


# ---------------------------------------------------------------------------
# TestActionAllLists


class TestActionAllLists:
    def test_no_lists(self):
        result = _action_all_lists()
        assert "no hay" in result.lower()

    def test_shows_lists(self):
        _action_add("leche", list_name="compra")
        _action_add("martillo", list_name="bricolaje")
        result = _action_all_lists()
        assert "compra" in result
        assert "bricolaje" in result


# ---------------------------------------------------------------------------
# TestEntryPoint


class TestShoppingListEntryPoint:
    def test_none_params_returns_list(self):
        result = shopping_list(None)
        assert isinstance(result, str)

    def test_add_action(self):
        result = shopping_list({"action": "add", "item": "pan"})
        assert "pan" in result.lower()

    def test_remove_action(self):
        shopping_list({"action": "add", "item": "leche"})
        result = shopping_list({"action": "remove", "item": "leche"})
        assert "eliminado" in result.lower()

    def test_list_action(self):
        shopping_list({"action": "add", "item": "queso"})
        result = shopping_list({"action": "list"})
        assert "queso" in result

    def test_check_action(self):
        shopping_list({"action": "add", "item": "yogur"})
        result = shopping_list({"action": "check", "item": "yogur"})
        assert isinstance(result, str)
        assert "yogur" in result.lower()

    def test_clear_action(self):
        shopping_list({"action": "add", "item": "arroz"})
        result = shopping_list({"action": "clear"})
        assert isinstance(result, str)

    def test_lists_action(self):
        shopping_list({"action": "add", "item": "pan"})
        result = shopping_list({"action": "lists"})
        assert isinstance(result, str)

    def test_unknown_action(self):
        result = shopping_list({"action": "fly"})
        assert "no reconocida" in result.lower()

    def test_product_alias(self):
        result = shopping_list({"action": "add", "product": "manzanas"})
        assert "manzanas" in result.lower()

    def test_añadir_alias(self):
        result = shopping_list({"action": "añadir", "item": "fresas"})
        assert "fresas" in result.lower()

    def test_custom_list_param(self):
        result = shopping_list({"action": "add", "item": "clavos", "lista": "ferretería"})
        assert "ferretería" in result.lower()
