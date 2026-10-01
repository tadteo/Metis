"""Inherited model defaults; snapshots contain references, never credentials."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .config import ResearchConfig
from .store import ConflictError, Store

ROUTING_KEYS = ("provider", "cheap_provider", "frontier_provider", "role_providers", "role_panels")
MODEL_KEYS = (*ROUTING_KEYS, "model_inventory", "allowed_models", "laya")


def global_store() -> Store:
    root = Path(os.environ.get("METIS_SETTINGS_HOME", Path.home() / ".local/state/metis-settings"))
    return Store(root, db_dir=root)


def select_models(config: ResearchConfig) -> dict[str, Any]:
    data = config.model_dump(mode="json")
    return {key: data[key] for key in MODEL_KEYS}


def validate_models(data: Any) -> dict[str, Any]:
    from .settings import validate_settings

    if not isinstance(data, dict) or set(data) - set(MODEL_KEYS):
        raise ValueError("Only model routing and Laya settings are allowed")
    config = validate_settings(data)
    normalized = select_models(config)
    return {key: normalized[key] for key in data}


def project_scope(project: str) -> str:
    if not project or not Path(project).expanduser().is_absolute():
        raise ValueError("Choose an absolute project source directory")
    return "project:" + str(Path(project).expanduser().resolve())


def _row(db: sqlite3.Connection, scope: str) -> tuple[dict[str, Any], int] | None:
    row = db.execute(
        "SELECT config,revision FROM model_settings WHERE scope=?", (scope,)
    ).fetchone()
    return (json.loads(row[0]), row[1]) if row else None


def _write(db: sqlite3.Connection, scope: str, config: dict[str, Any]) -> None:
    current = _row(db, scope)
    db.execute(
        "INSERT OR REPLACE INTO model_settings(scope,config,revision) VALUES(?,?,?)",
        (scope, json.dumps(config), (current[1] if current else 0) + 1),
    )


def _snapshot(
    db: sqlite3.Connection, global_db: sqlite3.Connection, scope: str, project: str
) -> dict[str, Any]:
    if scope not in {"global", "workspace", "project"}:
        raise ValueError("Choose global, workspace or project settings")
    key = project_scope(project) if scope == "project" else scope
    from .model_inventory import initial_inventory

    builtin_config = ResearchConfig()
    builtins = select_models(builtin_config)
    builtins["model_inventory"] = initial_inventory(builtin_config).model_dump(mode="json")
    local_global = _row(global_db, "global")
    remote = _row(db, "parent")
    global_values = (remote or local_global or (builtins, 0))[0]
    global_values = {**builtins, **global_values}
    inherited_row = remote or local_global
    if inherited_row is not None and "model_inventory" not in inherited_row[0]:
        global_values["model_inventory"] = None
    legacy = db.execute("SELECT config,revision FROM settings WHERE id=1").fetchone()
    workspace = _row(db, "workspace")
    workspace_values = (
        workspace[0]
        if workspace
        else select_models(ResearchConfig.model_validate_json(legacy[0]))
        if legacy
        else {}
    )
    if legacy and workspace is None:
        legacy_data = json.loads(legacy[0])
        for new_key in ("model_inventory", "allowed_models"):
            if new_key not in legacy_data and (remote or local_global):
                workspace_values.pop(new_key, None)
    project_row = _row(db, key) if scope == "project" else None
    parent = builtins if scope == "global" else global_values
    if scope == "project":
        parent = {**parent, **workspace_values}
    overrides = (
        global_values
        if scope == "global"
        else workspace_values
        if scope == "workspace"
        else (project_row or ({}, 0))[0]
    )
    config = ResearchConfig.model_validate_json(legacy[0]) if legacy else ResearchConfig()
    effective = {**parent, **overrides}
    data = config.model_dump(mode="json")
    data.update(effective)
    if scope == "project":
        data["project"]["source_dir"] = key.removeprefix("project:")
    token = hashlib.sha256(
        json.dumps(
            [
                remote or local_global,
                workspace,
                tuple(legacy) if legacy else None,
                key,
                project_row,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "scope": scope,
        "project": project,
        "revision": token,
        "settings_revision": int(token[:13], 16)
        if (remote or local_global or workspace or legacy or project_row)
        else 0,
        "config": data,
        "overrides": overrides,
        "inherited": parent,
        "managed": remote is not None,
        "legacy": workspace is None and legacy is not None,
    }


def snapshot(store: Store, scope: str = "workspace", project: str = "") -> dict[str, Any]:
    with global_store().connect() as global_db, store.connect() as db:
        return _snapshot(db, global_db, scope, project)


def save_scope(
    store: Store, scope: str, project: str, overrides: Any, revision: str
) -> dict[str, Any]:
    values = validate_models(overrides)
    with global_store().connect() as global_db:
        global_db.execute("BEGIN IMMEDIATE")
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            before = _snapshot(db, global_db, scope, project)
            if before["revision"] != revision:
                raise ConflictError("Settings changed. Reload this scope before saving again.")
            if scope == "global" and before["managed"]:
                raise ValueError("Global defaults are managed from the local console")
            if (
                any(key in values and values[key] != before["config"][key] for key in ROUTING_KEYS)
                and values.get("model_inventory", before["config"]["model_inventory"])
                == before["config"]["model_inventory"]
            ):
                values["model_inventory"] = None
            _write(
                global_db if scope == "global" else db,
                project_scope(project) if scope == "project" else scope,
                values,
            )
            return _snapshot(db, global_db, scope, project)


def resolve_models(store: Store, config: ResearchConfig) -> ResearchConfig:
    scope = "project" if config.project.source_dir else "workspace"
    result = snapshot(store, scope, config.project.source_dir or "")
    data = config.model_dump(mode="json")
    data.update({key: result["config"][key] for key in MODEL_KEYS})
    return ResearchConfig.model_validate(data)


def global_snapshot() -> dict[str, Any]:
    with global_store().connect() as db:
        row = _row(db, "global")
    config = ResearchConfig()
    values = select_models(config)
    if row is None:
        from .model_inventory import initial_inventory

        values["model_inventory"] = initial_inventory(config).model_dump(mode="json")
    return {**values, **(row[0] if row else {})}


def receive_parent(store: Store, config: Any) -> None:
    values = validate_models(config)
    if set(values) != set(MODEL_KEYS):
        raise ValueError("Global snapshot must contain all model settings")
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = _row(db, "parent")
        if current is None or current[0] != values:
            _write(db, "parent", values)
