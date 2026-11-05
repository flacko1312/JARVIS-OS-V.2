"""E46 — Shopping list management with local JSON persistence.

Provides a full CRUD shopping list experience: add items, remove them,
mark as purchased, clear the list, and support multiple named lists.
No external API required.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Storage helpers

_LISTS_DIR_ENV = "JARVIS_LISTS_DIR"


def _lists_dir() -> Path:
    env = os.environ.get(_LISTS_DIR_ENV, "")
    base = Path(env) if env else Path.home() / ".jarvis" / "lists"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _list_path(name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lower()) or "compra"
    return _lists_dir() / f"{safe}.json"


def _load(name: str) -> list[dict]:
    path = _list_path(name)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(name: str, items: list[dict]) -> None:
    path = _list_path(name)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _normalize_list_name(name: str) -> str:
    return (name or "compra").strip().lower()


# ---------------------------------------------------------------------------
# Actions


def _action_add(item: str, quantity: str = "", list_name: str = "compra") -> str:
    if not item.strip():
        return "Especifica qué quieres añadir a la lista."
    name = _normalize_list_name(list_name)
    items = _load(name)
    # Avoid duplicates (case-insensitive)
    for existing in items:
        if existing.get("item", "").lower() == item.strip().lower():
            if quantity:
                existing["quantity"] = quantity.strip()
                _save(name, items)
                return f"Actualizada cantidad de '{item}' en la lista '{name}'."
            return f"'{item}' ya está en la lista '{name}'."
    entry: dict = {"item": item.strip(), "done": False}
    if quantity.strip():
        entry["quantity"] = quantity.strip()
    items.append(entry)
    _save(name, items)
    qty_str = f" ({quantity.strip()})" if quantity.strip() else ""
    return f"Añadido '{item.strip()}'{qty_str} a la lista '{name}'."


def _action_remove(item: str, list_name: str = "compra") -> str:
    if not item.strip():
        return "Especifica qué quieres eliminar de la lista."
    name = _normalize_list_name(list_name)
    items = _load(name)
    before = len(items)
    items = [i for i in items if i.get("item", "").lower() != item.strip().lower()]
    if len(items) == before:
        return f"'{item}' no estaba en la lista '{name}'."
    _save(name, items)
    return f"Eliminado '{item.strip()}' de la lista '{name}'."


def _action_check(item: str, list_name: str = "compra", done: bool = True) -> str:
    if not item.strip():
        return "Especifica el artículo que quieres marcar."
    name = _normalize_list_name(list_name)
    items = _load(name)
    for entry in items:
        if entry.get("item", "").lower() == item.strip().lower():
            entry["done"] = done
            _save(name, items)
            state = "comprado ✓" if done else "pendiente"
            return f"'{item.strip()}' marcado como {state}."
    return f"'{item}' no está en la lista '{name}'."


def _action_list(list_name: str = "compra", show_all: bool = True) -> str:
    name = _normalize_list_name(list_name)
    items = _load(name)
    if not items:
        return f"La lista '{name}' está vacía."
    pending = [i for i in items if not i.get("done")]
    done = [i for i in items if i.get("done")]
    lines = [f"Lista '{name}' ({len(items)} artículos):"]
    if pending:
        lines.append("Pendientes:")
        for entry in pending:
            qty = f" ({entry['quantity']})" if entry.get("quantity") else ""
            lines.append(f"  ○ {entry['item']}{qty}")
    if done and show_all:
        lines.append("Comprados:")
        for entry in done:
            qty = f" ({entry['quantity']})" if entry.get("quantity") else ""
            lines.append(f"  ✓ {entry['item']}{qty}")
    return "\n".join(lines)


def _action_clear(list_name: str = "compra", only_done: bool = False) -> str:
    name = _normalize_list_name(list_name)
    items = _load(name)
    if not items:
        return f"La lista '{name}' ya estaba vacía."
    if only_done:
        kept = [i for i in items if not i.get("done")]
        removed = len(items) - len(kept)
        _save(name, kept)
        return f"Eliminados {removed} artículos comprados de '{name}'."
    _save(name, [])
    return f"Lista '{name}' vaciada ({len(items)} artículos eliminados)."


def _action_all_lists() -> str:
    base = _lists_dir()
    files = sorted(base.glob("*.json"))
    if not files:
        return "No hay listas creadas todavía."
    lines = ["Listas disponibles:"]
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            count = len(data) if isinstance(data, list) else 0
            pending = sum(1 for i in data if isinstance(i, dict) and not i.get("done")) if isinstance(data, list) else 0
            lines.append(f"  • {f.stem}: {count} artículos ({pending} pendientes)")
        except Exception:
            lines.append(f"  • {f.stem}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point


def shopping_list(parameters=None, response=None, player=None, session_memory=None) -> str:
    """NEST 68 E46 — Shopping list management with local JSON persistence."""
    if not parameters:
        return _action_list()

    action = str(parameters.get("action", "list")).strip().lower()
    item = str(parameters.get("item") or parameters.get("product") or "").strip()
    quantity = str(parameters.get("quantity") or parameters.get("cantidad") or "").strip()
    list_name = str(parameters.get("list") or parameters.get("lista") or "compra").strip()

    if action in ("add", "añadir", "agregar", "apuntar", "put"):
        return _action_add(item, quantity=quantity, list_name=list_name)
    elif action in ("remove", "eliminar", "quitar", "borrar", "delete"):
        return _action_remove(item, list_name=list_name)
    elif action in ("check", "marcar", "comprado", "done", "tick"):
        return _action_check(item, list_name=list_name, done=True)
    elif action in ("uncheck", "desmarcar", "pendiente", "untick"):
        return _action_check(item, list_name=list_name, done=False)
    elif action in ("list", "mostrar", "ver", "show", "read"):
        return _action_list(list_name=list_name)
    elif action in ("clear", "vaciar", "limpiar"):
        only_done = bool(parameters.get("only_done") or parameters.get("solo_comprados"))
        return _action_clear(list_name=list_name, only_done=only_done)
    elif action in ("lists", "all_lists", "todas"):
        return _action_all_lists()
    else:
        return f"Acción '{action}' no reconocida. Usa: add, remove, check, uncheck, list, clear, lists."
