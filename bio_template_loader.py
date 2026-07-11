"""Shared Bio template loading and rendering helpers."""

import importlib.util
import os
from dataclasses import dataclass
from typing import Callable, Dict, List

import bio_templates


DIGIT_STYLES = {
    "normal": "1",
    "sans_bold": "𝟭",
    "serif_bold": "𝟏",
    "double_struck": "𝟙",
}

DIGIT_STYLE_MAPS = {
    "normal": str.maketrans("", ""),
    "sans_bold": str.maketrans("0123456789", "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"),
    "serif_bold": str.maketrans("0123456789", "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"),
    "double_struck": str.maketrans("0123456789", "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"),
}

LETTER_SOURCE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
LETTER_STYLES = {
    "normal": "Aa",
    "sans_bold": "𝗔𝗮",
    "script": "𝒜𝒶",
    "bold_script": "𝓐𝓪",
    "monospace": "𝙰𝚊",
    "double_struck": "𝔸𝕒",
}

LETTER_STYLE_MAPS = {
    "normal": str.maketrans("", ""),
    "sans_bold": str.maketrans(LETTER_SOURCE, "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇"),
    "script": str.maketrans(LETTER_SOURCE, "𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏"),
    "bold_script": str.maketrans(LETTER_SOURCE, "𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃"),
    "monospace": str.maketrans(LETTER_SOURCE, "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣"),
    "double_struck": str.maketrans(LETTER_SOURCE, "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫"),
}

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
