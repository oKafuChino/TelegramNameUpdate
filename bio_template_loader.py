"""Shared Bio template loading and rendering helpers."""

import importlib.util
import os
from dataclasses import dataclass
from typing import Callable, Dict, List

import bio_templates


CUSTOM_TEMPLATE_FILENAME = "bio_custom_templates.py"
DEFAULT_TEMPLATE = "elapsed_en"


@dataclass(frozen=True)
class TemplateEntry:
    key: str
    name: str
    description: str
    render: Callable
    source: str


@dataclass(frozen=True)
class TemplateRegistry:
    entries: Dict[str, TemplateEntry]
    errors: List[str]


def get_user_template_path(data_dir):
    return os.path.join(data_dir, CUSTOM_TEMPLATE_FILENAME)


def _normalize_template(key, value, source):
    if not isinstance(key, str) or not key.strip():
        raise ValueError("template key must be a non-empty string")
    key = key.strip()
    if callable(value):
        return TemplateEntry(key, key, "", value, source)
    if not isinstance(value, dict):
        raise ValueError(f"template {key!r} must be a function or metadata dict")
    render = value.get("render")
    if not callable(render):
        raise ValueError(f"template {key!r} render must be callable")
    name = value.get("name")
    description = value.get("description")
    return TemplateEntry(
        key=key,
        name=name.strip() if isinstance(name, str) and name.strip() else key,
        description=description.strip() if isinstance(description, str) else "",
        render=render,
        source=source,
    )


def _merge_templates(entries, errors, templates, source, allow_override=False):
    if not isinstance(templates, dict):
        errors.append(f"{source} BIO_TEMPLATES must be a dict")
        return
    for key, value in templates.items():
        try:
            entry = _normalize_template(key, value, source)
        except Exception as exc:
            errors.append(f"{source} template {key!r} ignored: {exc}")
            continue
        if entry.key in entries and not allow_override:
            errors.append(f"{source} template {entry.key!r} duplicate ignored")
            continue
        entries[entry.key] = entry


def _load_custom_module(path, errors):
    if not os.path.exists(path):
        return None
    module_name = "_tg_updater_bio_custom_templates"
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError("cannot create import spec")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        errors.append(f"user template file failed to load: {exc}")
        return None


def load_templates(data_dir=None, builtins=None):
    errors = []
    entries = {}
    _merge_templates(entries, errors, builtins or bio_templates.BIO_TEMPLATES, "built-in")
    if data_dir:
        module = _load_custom_module(get_user_template_path(data_dir), errors)
        if module is not None:
            _merge_templates(entries, errors, getattr(module, "BIO_TEMPLATES", None), "user")
    return TemplateRegistry(entries=entries, errors=errors)


def template_exists(template_name, data_dir=None):
    return isinstance(template_name, str) and template_name in load_templates(data_dir).entries


def render_bio(template_name, ctx, data_dir=None, registry=None):
    registry = registry or load_templates(data_dir)
    entry = registry.entries.get(template_name) or registry.entries.get(DEFAULT_TEMPLATE)
    if entry is None:
        raise KeyError(f"Bio template {DEFAULT_TEMPLATE!r} is not available")
    try:
        value = entry.render(ctx)
        if not isinstance(value, str):
            raise TypeError(f"Bio template {entry.key!r} must return str")
        return value
    except Exception:
        fallback = registry.entries.get(DEFAULT_TEMPLATE)
        if fallback is None or fallback.key == entry.key:
            raise
        value = fallback.render(ctx)
        if not isinstance(value, str):
            raise TypeError(f"Bio template {fallback.key!r} must return str")
        return value
