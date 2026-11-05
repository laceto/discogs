"""
Flat-JSON persistence for collected entities.

Storage shape (see docs/schemas.md): one JSON file per entity, at
``data/<entity_type>/<id>.json`` relative to the repo root.
"""

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _entity_path(entity_type: str, id: Any, base_dir: Path) -> Path:
    return base_dir / entity_type / f"{id}.json"


def save_json(
    entity_type: str, id: Any, record: dict[str, Any], base_dir: Path | None = None
) -> Path:
    """Write `record` to `<base_dir>/<entity_type>/<id>.json`, creating parent dirs as needed.

    `base_dir` defaults to `data/` under the repo root. Returns the path written to.
    """
    base = base_dir if base_dir is not None else _REPO_ROOT / "data"
    path = _entity_path(entity_type, id, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_json(entity_type: str, id: Any, base_dir: Path | None = None) -> dict[str, Any] | None:
    """Read back the record written by `save_json`, or None if it doesn't exist."""
    base = base_dir if base_dir is not None else _REPO_ROOT / "data"
    path = _entity_path(entity_type, id, base)
    if not path.exists():
        return None
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def list_ids(entity_type: str, base_dir: Path | None = None) -> list[str]:
    """Return the ids saved under `<base_dir>/<entity_type>/`, sorted; `[]` if none exist yet."""
    base = base_dir if base_dir is not None else _REPO_ROOT / "data"
    folder = base / entity_type
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("*.json"))
