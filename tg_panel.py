#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import urllib.request
import re
import subprocess
import time
import unicodedata
import tempfile
import secrets
import calendar
import ast
import shutil
import shlex
import copy
from datetime import date
import bio_templates
import bio_template_loader
from bio_template_loader import DIGIT_STYLES, LETTER_STYLES, LETTER_STYLE_MAPS

# ==========================================
# 【版本定义】
# 每次修改代码推送到 GitHub 前，请手动提升此版本号
# ==========================================
CURRENT_VERSION = "v1.11.2"
AUTHOR = "oKafuChino"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_INSTALLED = BASE_DIR == "/opt/tg_updater"
DEFAULT_DATA_DIR = "/var/lib/tg_updater" if IS_INSTALLED else BASE_DIR
DATA_DIR = DEFAULT_DATA_DIR if IS_INSTALLED else os.environ.get("TG_UPDATER_DATA_DIR", DEFAULT_DATA_DIR)
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
SESSION_FILE = os.path.join(DATA_DIR, 'api_auth.session')
SESSION_JOURNAL_FILE = os.path.join(DATA_DIR, 'api_auth.session-journal')
API_CONFIG_FILE = os.path.join(DATA_DIR, 'api_auth.json')
BIO_STATE_FILE = os.path.join(DATA_DIR, 'bio_last_update.txt')
EMOJI_STATE_FILE = os.path.join(DATA_DIR, 'emoji_last_active.txt')
LEGACY_CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
LEGACY_SESSION_FILE = os.path.join(BASE_DIR, 'api_auth.session')
LEGACY_SESSION_JOURNAL_FILE = os.path.join(BASE_DIR, 'api_auth.session-journal')
LEGACY_API_CONFIG_FILE = os.path.join(BASE_DIR, 'api_auth.json')
REPO_URL = "https://raw.githubusercontent.com/oKafuChino/TelegramNameUpdate/main"
SERVICE_USER = "tg_updater"
DEFAULT_NAME_ORDER = ["time", "timezone", "date", "temp", "weather", "emoji"]
LAST_NAME_FIELD_TYPES = DEFAULT_NAME_ORDER.copy()
LAST_NAME_ITEM_TYPES = (*LAST_NAME_FIELD_TYPES, "text")
ORDER_LABELS = {
    "time": "时间",
    "timezone": "时区",
    "date": "日期",
    "temp": "温度",
    "weather": "天气",
    "emoji": "Emoji",
    "text": "自定义文本",
}
DEFAULT_CONFIG = {"show_time": True, "show_timezone": True, "show_date": False, "show_temp": True, "show_weather": True, "location": "Los Angeles", "digit_style": "sans_bold", "letter_style": "normal", "name_order": DEFAULT_NAME_ORDER.copy(), "last_name_mode": "classic", "last_name_rules": [], "last_name_default_items": [{"type": item} for item in DEFAULT_NAME_ORDER], "bio_enabled": False, "birth_date": "", "fixed_bio": "", "bio_template": "elapsed_en", "update_interval": 1, "emoji_schedules": []}
BOOL_CONFIG_KEYS = ("show_time", "show_timezone", "show_date", "show_temp", "show_weather", "bio_enabled")
UPDATE_INTERVALS = (1, 5, 15, 30, 60)
MAX_LOCATION_LENGTH = 80
MAX_BIO_LENGTH = 70
MAX_EMOJI_RULES = 20
MAX_EMOJI_TEXT_LENGTH = 32
MAX_ACTIVE_EMOJI_LENGTH = 32
MAX_LAST_NAME_RULES = 20
MAX_LAST_NAME_TEXT_LENGTH = 32
MAX_LAST_NAME_RULE_NAME_LENGTH = 24
MAX_CONFIG_FILE_SIZE = 256 * 1024
MAX_REMOTE_FILE_SIZE = 2 * 1024 * 1024
MAX_VERSION_RESPONSE_SIZE = 512 * 1024
USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None and os.environ.get("TERM") != "dumb"
COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "blue": "\033[34m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "magenta": "\033[35m",
    "white": "\033[37m",
}

def color(text, *styles):
    if not USE_COLOR:
        return text
    prefix = "".join(COLORS[style] for style in styles if style in COLORS)
    return f"{prefix}{text}{COLORS['reset']}"

def display_width(text):
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("F", "W") else 1
    return width

def pad_right(text, width):
    return text + " " * max(0, width - display_width(text))

def state_text(enabled):
    if enabled:
        return color("● 开启", "green", "bold")
    return color("○ 关闭", "red")

def normalize_name_order(order):
    if not isinstance(order, list):
        order = []

    normalized = []
    for item in order:
        if item in DEFAULT_NAME_ORDER and item not in normalized:
            normalized.append(item)

    for item in DEFAULT_NAME_ORDER:
        if item not in normalized:
            normalized.append(item)

    return normalized

def format_name_order(order):
    return " > ".join(ORDER_LABELS[item] for item in normalize_name_order(order))

def normalize_last_name_text(value):
    if not isinstance(value, str):
        return ""
    cleaned = " ".join("".join(char for char in value.strip() if char.isprintable()).split())
    return cleaned[:MAX_LAST_NAME_TEXT_LENGTH]

def normalize_last_name_items(items):
    if not isinstance(items, list):
        return []

    normalized = []
    for item in items:
        if isinstance(item, str):
            item = {"type": item}
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in LAST_NAME_FIELD_TYPES:
            normalized.append({"type": item_type})
        elif item_type == "text":
            text = normalize_last_name_text(item.get("value"))
            if text:
                normalized.append({"type": "text", "value": text})
        if len(normalized) >= len(DEFAULT_NAME_ORDER) + 6:
            break
    return normalized

def default_last_name_items_from_order(order):
    return [{"type": item} for item in normalize_name_order(order)]

def normalize_last_name_rules(rules):
    if not isinstance(rules, list):
        return []

    normalized = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        start = parse_time_text(rule.get("start"))
        end = parse_time_text(rule.get("end"))
        items = normalize_last_name_items(rule.get("items"))
        if not start or not end or start == end or not items:
            continue
        name = normalize_last_name_text(rule.get("name"))[:MAX_LAST_NAME_RULE_NAME_LENGTH] or f"{start}-{end}"
        normalized.append({"name": name, "start": start, "end": end, "items": items})
        if len(normalized) >= MAX_LAST_NAME_RULES:
            break
    return normalized

def format_last_name_items(items):
    labels = []
    for item in normalize_last_name_items(items):
        if item["type"] == "text":
            labels.append(f"文本:{safe_display(item['value'])}")
        else:
            labels.append(ORDER_LABELS[item["type"]])
    return " > ".join(labels) if labels else "未设置"

def safe_display(value):
    return "".join(char if char.isprintable() else "?" for char in str(value))

def parse_time_text(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value.strip()):
        return None
    return value.strip()

def is_emoji_codepoint(char):
    codepoint = ord(char)
    return (
        0x1F000 <= codepoint <= 0x1FAFF
        or 0x2600 <= codepoint <= 0x27BF
        or 0x2300 <= codepoint <= 0x23FF
        or 0x2B00 <= codepoint <= 0x2BFF
        or codepoint in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x3030, 0x303D, 0x3297, 0x3299)
    )

def sanitize_emoji_text(value):
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(value.strip().split())
    has_keycap = "\u20e3" in cleaned
    allowed_components = {"\u200d", "\ufe0e", "\ufe0f", "\u20e3"}
    if (
        not cleaned
        or len(cleaned) > MAX_EMOJI_TEXT_LENGTH
        or not (any(is_emoji_codepoint(char) for char in cleaned) or has_keycap)
        or any(
            not (
                is_emoji_codepoint(char)
                or char in allowed_components
                or char == " "
                or (has_keycap and char in "#*0123456789")
            )
            for char in cleaned
        )
    ):
        return ""
    return cleaned

def time_to_minute(value):
    return int(value[:2]) * 60 + int(value[3:])

def is_rule_active(rule, minute_of_day):
    start = time_to_minute(rule["start"])
    end = time_to_minute(rule["end"])
    if start < end:
        return start <= minute_of_day < end
    return minute_of_day >= start or minute_of_day < end

def max_active_emoji_length(schedules):
    return max(
        (sum(len(rule["emoji"]) for rule in schedules if is_rule_active(rule, minute)) for minute in range(1440)),
        default=0,
    )

def normalize_emoji_schedules(schedules):
    if not isinstance(schedules, list):
        return []

    normalized = []
    for rule in schedules:
        if not isinstance(rule, dict):
            continue
        start = parse_time_text(rule.get("start"))
        end = parse_time_text(rule.get("end"))
        emoji = sanitize_emoji_text(rule.get("emoji"))
        candidate = {"start": start, "end": end, "emoji": emoji}
        if start and end and start != end and emoji and max_active_emoji_length([*normalized, candidate]) <= MAX_ACTIVE_EMOJI_LENGTH:
            normalized.append(candidate)
        if len(normalized) >= MAX_EMOJI_RULES:
            break
    return normalized

def parse_birth_date(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed <= date.today() else None

def add_months(value, months):
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

def calculate_elapsed(birth_date, today=None):
    today = today or date.today()
    if birth_date > today:
        raise ValueError("出生日期不能晚于今天")

    years = today.year - birth_date.year
    anniversary = add_months(birth_date, years * 12)
    if anniversary > today:
        years -= 1
        anniversary = add_months(birth_date, years * 12)

    months = 0
    while months < 11 and add_months(anniversary, months + 1) <= today:
        months += 1
    checkpoint = add_months(anniversary, months)
    return years, months, (today - checkpoint).days

def get_utc_offset_text(local_time):
    offset_seconds = getattr(local_time, "tm_gmtoff", None)
    if offset_seconds is None:
        offset_seconds = time.mktime(local_time) - time.mktime(time.gmtime(time.mktime(local_time)))

    sign = "+" if offset_seconds >= 0 else "-"
    offset_seconds = abs(int(offset_seconds))
    hours, remainder = divmod(offset_seconds, 3600)
    minutes = remainder // 60
    if minutes:
        return f"UTC{sign}{hours}:{minutes:02d}"
    return f"UTC{sign}{hours}"

def join_non_empty(parts):
    return " ".join(str(part) for part in parts if part)

def build_bio_context(birth_date, fixed_bio, today=None, config=None, local_time=None, weather_data=None):
    years, months, days = calculate_elapsed(birth_date, today)
    today = today or date.today()
    local_time = local_time or time.localtime()
    config = config or DEFAULT_CONFIG
    weather_data = weather_data or {"temp": "", "emoji": ""}
    ctx = {
        "years": years,
        "months": months,
        "days": days,
        "birth_date": birth_date,
        "today": today,
        "fixed_bio": fixed_bio,
        "time": time.strftime("%H:%M", local_time),
        "timezone": get_utc_offset_text(local_time),
        "date": time.strftime("%m-%d", local_time),
        "location": config.get("location", ""),
        "temp": weather_data.get("temp", ""),
        "weather": weather_data.get("emoji", ""),
        "digit_style": config.get("digit_style", "sans_bold"),
        "letter_style": config.get("letter_style", "normal"),
        "max_length": MAX_BIO_LENGTH,
    }
    ctx["join"] = join_non_empty
    letter_map = LETTER_STYLE_MAPS.get(ctx["letter_style"], LETTER_STYLE_MAPS["normal"])
    ctx["letters"] = lambda value: str(value).translate(letter_map)
    ctx["elapsed_en"] = lambda: bio_templates.elapsed_en(ctx)
    return ctx

def build_bio_text(birth_date, fixed_bio, today=None, template_name="elapsed_en", config=None, local_time=None, weather_data=None):
    ctx = build_bio_context(birth_date, fixed_bio, today, config, local_time, weather_data)
    try:
        return bio_template_loader.render_bio(template_name, ctx, DATA_DIR)
    except Exception:
        return bio_template_loader.render_bio("elapsed_en", ctx, DATA_DIR)

def build_bio_text_strict(birth_date, fixed_bio, today=None, template_name="elapsed_en", config=None, local_time=None, weather_data=None):
    ctx = build_bio_context(birth_date, fixed_bio, today, config, local_time, weather_data)
    registry = bio_template_loader.load_templates(DATA_DIR)
    entry = registry.entries.get(template_name)
    if entry is None:
        raise KeyError(f"Bio template {template_name!r} is not available")
    value = entry.render(ctx)
    if not isinstance(value, str):
        raise TypeError(f"Bio template {template_name!r} must return str")
    return value

def sanitize_config(raw_config):
    config = copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(raw_config, dict):
        raw_config = {}

    for key in BOOL_CONFIG_KEYS:
        if isinstance(raw_config.get(key), bool):
            config[key] = raw_config[key]

    digit_style = raw_config.get("digit_style")
    if digit_style in DIGIT_STYLES:
        config["digit_style"] = digit_style
    elif isinstance(raw_config.get("use_bold"), bool):
        config["digit_style"] = "sans_bold" if raw_config["use_bold"] else "normal"

    letter_style = raw_config.get("letter_style")
    if letter_style in LETTER_STYLES:
        config["letter_style"] = letter_style

    location = raw_config.get("location")
    if isinstance(location, str) and location.strip():
        printable_location = "".join(char for char in location.strip() if char.isprintable())
        cleaned_location = " ".join(printable_location.split())
        if cleaned_location:
            config["location"] = cleaned_location[:MAX_LOCATION_LENGTH]

    config["name_order"] = normalize_name_order(raw_config.get("name_order"))
    if raw_config.get("last_name_mode") == "custom":
        config["last_name_mode"] = "custom"
    config["last_name_default_items"] = normalize_last_name_items(raw_config.get("last_name_default_items"))
    if not config["last_name_default_items"]:
        config["last_name_default_items"] = default_last_name_items_from_order(config["name_order"])
    config["last_name_rules"] = normalize_last_name_rules(raw_config.get("last_name_rules"))
    birth_date = parse_birth_date(raw_config.get("birth_date"))
    if birth_date:
        config["birth_date"] = birth_date.isoformat()

    fixed_bio = raw_config.get("fixed_bio")
    if isinstance(fixed_bio, str):
        config["fixed_bio"] = "".join(char for char in fixed_bio.strip() if char.isprintable())[:MAX_BIO_LENGTH]

    bio_template = raw_config.get("bio_template")
    if bio_template_loader.template_exists(bio_template, DATA_DIR):
        config["bio_template"] = bio_template

    if not config["birth_date"] or not config["fixed_bio"]:
        config["bio_enabled"] = False
    elif len(build_bio_text(birth_date, config["fixed_bio"], template_name=config["bio_template"], config=config)) > MAX_BIO_LENGTH:
        config["bio_enabled"] = False

    update_interval = raw_config.get("update_interval")
    if isinstance(update_interval, int) and not isinstance(update_interval, bool) and update_interval in UPDATE_INTERVALS:
        config["update_interval"] = update_interval
    config["emoji_schedules"] = normalize_emoji_schedules(raw_config.get("emoji_schedules"))
    return config

def menu_line(key, label, detail="", accent="cyan"):
    key_text = color(pad_right(f"[{key}]", 4), accent, "bold")
    label_text = pad_right(label, 18)
    if detail:
        detail_text = detail if "\033[" in detail else color(detail, "dim")
        print(f"  {key_text} {label_text} {detail_text}")
    else:
        print(f"  {key_text} {label_text}")

def menu_section(title):
    print()
    print(color(f"  {title}", "yellow", "bold"))

def box_row(text, highlight="", text_styles=()):
    width = 54
    plain_text = text + highlight
    display_text = (color(text, *text_styles) if text_styles else text) + (color(highlight, "green", "bold") if highlight else "")
    padding = " " * max(0, width - display_width(plain_text))
    print(color("│", "cyan") + display_text + padding + color("│", "cyan"))

def render_menu(config):
    print(color("╭" + "─"*54 + "╮", "cyan"))
    box_row("        Telegram 名字动态更新面板", text_styles=("bold", "white"))
    box_row("        当前版本: ", CURRENT_VERSION)
    box_row("        作者: ", AUTHOR)
    print(color("╰" + "─"*54 + "╯", "cyan"))

    menu_section("账号与状态")
    menu_line("1", "更新账号 Session", "重新登录或更换账号", "blue")
    menu_line("2", "查看运行日志", "最近 50 条 systemd 日志", "blue")

    menu_section("展示内容")
    menu_line("3", "显示时间", state_text(config['show_time']), "magenta")
    menu_line("4", "显示时区", state_text(config['show_timezone']), "magenta")
    menu_line("5", "显示日期", state_text(config['show_date']), "magenta")
    menu_line("6", "显示温度", state_text(config['show_temp']), "magenta")
    menu_line("7", "显示天气", state_text(config['show_weather']), "magenta")
    menu_line("8", "数字字体", f"样式: {DIGIT_STYLES[config['digit_style']]}", "magenta")
    menu_line("9", "字母字体", f"样式: {LETTER_STYLES[config['letter_style']]}", "magenta")
    menu_line("10", "设置地区", f"当前: {safe_display(config['location'])}", "magenta")
    menu_line("11", "输出顺序", format_name_order(config["name_order"]), "magenta")
    menu_line("12", "一键开启全部", "时间 / 时区 / 日期 / 温度 / 天气", "magenta")

    menu_section("自动化设置")
    menu_line("13", "Bio 自动更新", state_text(config['bio_enabled']), "blue")
    menu_line("14", "Last Name 频率", f"每 {config['update_interval']} 分钟", "blue")
    mode_text = "自定义" if config["last_name_mode"] == "custom" else "经典"
    menu_line("15", "Last Name 规则", f"{mode_text} / {len(config['last_name_rules'])} 条规则", "blue")

    menu_section("维护工具")
    menu_line("16", "重启后台服务", "立即重载配置", "green")
    menu_line("17", "检查并更新", "从 GitHub 拉取核心脚本", "green")
    menu_line("18", "同步服务器时区", "改名显示将使用 UTC 偏移", "green")
    menu_line("19", "强制更新 Last Name", "立即按当前配置更新一次", "green")
    menu_line("20", "强制更新 Bio", "立即按当前配置更新一次", "green")

    print()
    menu_line("99", "一键卸载脚本", "停止服务并删除程序与配置", "red")
    menu_line("0", "退出管理面板", "", "red")
    print(color("─"*56, "cyan"))

def is_root_user():
    return hasattr(os, "geteuid") and os.geteuid() == 0

def quote_shell_command(command):
    return " ".join(shlex.quote(str(part)) for part in command)

def command_as_user(user, command, command_exists=shutil.which, is_root=None):
    if is_root is None:
        is_root = is_root_user()
    if is_root:
        if command_exists("runuser"):
            return ["runuser", "-u", user, "--", *command]
        if command_exists("sudo"):
            return ["sudo", "-u", user, *command]
        if command_exists("su"):
            return ["su", "-s", "/bin/sh", user, "-c", quote_shell_command(command)]
    return ["sudo", "-u", user, *command]

def prepare_run_command(command, command_exists=shutil.which, is_root=None):
    if not command:
        return command
    if is_root is None:
        is_root = is_root_user()
    if command[0] == "sudo" and is_root:
        if len(command) >= 4 and command[1] == "-u":
            return command_as_user(command[2], command[3:], command_exists, is_root=True)
        return command[1:]
    return command

def run_command(command, **kwargs):
    command = prepare_run_command(command)
    try:
        return subprocess.run(command, check=False, **kwargs).returncode
    except FileNotFoundError:
        print(f"命令不存在: {command[0]}")
        return 127

def trigger_service_update(signal_name, label):
    if run_command(["sudo", "systemctl", "is-active", "--quiet", "tg_name.service"]) != 0:
        input(f"❌ 后台服务未运行，无法更新 {label}。按回车键返回主菜单...")
        return

    result = run_command([
        "sudo", "systemctl", "kill", "--kill-who=main",
        f"--signal={signal_name}", "tg_name.service",
    ])
    if result == 0:
        input(f"✅ 已发送 {label} 强制更新指令，可使用 [2] 查看执行结果。按回车键返回主菜单...")
    else:
        input(f"❌ {label} 强制更新指令发送失败，请使用 [2] 查看日志。按回车键返回主菜单...")

def backup_session_files():
    suffix = f".login.bak.{os.getpid()}.{secrets.token_hex(4)}"
    backups = []
    try:
        for path in (SESSION_FILE, SESSION_JOURNAL_FILE):
            if os.path.lexists(path):
                backup_path = path + suffix
                os.replace(path, backup_path)
                backups.append((path, backup_path))
    except OSError:
        restore_session_files(backups)
        raise
    return backups

def restore_session_files(backups):
    restored = True
    for path in (SESSION_FILE, SESSION_JOURNAL_FILE):
        try:
            if os.path.lexists(path):
                os.unlink(path)
        except OSError:
            restored = False
    for original_path, backup_path in backups:
        try:
            os.replace(backup_path, original_path)
        except OSError:
            restored = False
    return restored

def remove_session_backups(backups):
    removed = True
    for _, backup_path in backups:
        try:
            os.unlink(backup_path)
        except FileNotFoundError:
            pass
        except OSError:
            removed = False
    return removed

def chown_runtime_files():
    if run_command(["id", "-u", SERVICE_USER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.islink(DATA_DIR):
        run_command(["sudo", "chown", f"{SERVICE_USER}:{SERVICE_USER}", DATA_DIR])
        run_command(["sudo", "chmod", "700", DATA_DIR])
    for path in (CONFIG_FILE, SESSION_FILE, SESSION_JOURNAL_FILE, API_CONFIG_FILE, BIO_STATE_FILE, EMOJI_STATE_FILE):
        if os.path.exists(path) and not os.path.islink(path):
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            run_command(["sudo", "chown", f"{SERVICE_USER}:{SERVICE_USER}", path])
            run_command(["sudo", "chmod", "600", path])

def migrate_legacy_runtime_files():
    if DATA_DIR == BASE_DIR:
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    pairs = (
        (LEGACY_CONFIG_FILE, CONFIG_FILE),
        (LEGACY_API_CONFIG_FILE, API_CONFIG_FILE),
        (LEGACY_SESSION_FILE, SESSION_FILE),
        (LEGACY_SESSION_JOURNAL_FILE, SESSION_JOURNAL_FILE),
    )
    for source, target in pairs:
        if os.path.exists(source) and not os.path.exists(target) and not os.path.islink(source):
            run_command(["sudo", "mv", source, target])
    chown_runtime_files()

def harden_code_files():
    if BASE_DIR != "/opt/tg_updater":
        return True

    success = run_command(["sudo", "chown", "root:root", BASE_DIR]) == 0
    success = run_command(["sudo", "chmod", "755", BASE_DIR]) == 0 and success
    for filename in ("tg_panel.py", "tg_daemon.py", "bio_templates.py", "bio_template_loader.py", "requirements.txt"):
        path = os.path.join(BASE_DIR, filename)
        if os.path.isfile(path) and not os.path.islink(path):
            mode = "755" if filename.endswith(".py") else "644"
            success = run_command(["sudo", "chown", "root:root", path]) == 0 and success
            success = run_command(["sudo", "chmod", mode, path]) == 0 and success
    return success

def remote_file_url(filename):
    return f"{REPO_URL}/{filename}?t={int(time.time())}"

def get_remote_version():
    """检查 GitHub 上的最新版本"""
    try:
        req = urllib.request.Request(
            remote_file_url("tg_panel.py"),
            headers={'Cache-Control': 'no-cache, no-store', 'Pragma': 'no-cache'}
        )
        with urllib.request.urlopen(req, timeout=1.5) as response:
            content_bytes = response.read(MAX_VERSION_RESPONSE_SIZE + 1)
            if len(content_bytes) > MAX_VERSION_RESPONSE_SIZE:
                return None
            content = content_bytes.decode('utf-8')
            version = extract_version_from_source(content, "remote tg_panel.py")
            if parse_version(version) is not None:
                return version
    except Exception:
        pass 
    return None

def parse_version(version):
    if not isinstance(version, str):
        return None
    match = re.fullmatch(r"v?(\d{1,6}(?:\.\d{1,6}){0,3})", version.strip())
    if not match:
        return None
    return tuple(int(number) for number in match.group(1).split("."))

def compare_versions(left, right):
    left_parts = parse_version(left)
    right_parts = parse_version(right)
    if left_parts is None or right_parts is None:
        return None

    max_len = max(len(left_parts), len(right_parts))
    left_parts += (0,) * (max_len - len(left_parts))
    right_parts += (0,) * (max_len - len(right_parts))
    return (left_parts > right_parts) - (left_parts < right_parts)

def extract_version_from_file(path):
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return None

    return extract_version_from_source(content, path)

def extract_version_from_source(content, filename="<string>"):
    try:
        tree = ast.parse(content, filename=filename)
    except (TypeError, SyntaxError, ValueError):
        return None

    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "CURRENT_VERSION" for target in node.targets):
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "CURRENT_VERSION":
            value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
    return None

def load_config():
    loaded = {}
    if not os.path.exists(CONFIG_FILE):
        return sanitize_config(loaded)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            content = f.read(MAX_CONFIG_FILE_SIZE + 1)
        if len(content) > MAX_CONFIG_FILE_SIZE:
            raise ValueError("配置文件超过大小限制")
        loaded = json.loads(content)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ 配置文件读取失败，已使用默认配置: {e}")
    except ValueError as e:
        print(f"⚠️ 配置文件无效，已使用默认配置: {e}")
    return sanitize_config(loaded)

def write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".config.", suffix=".tmp", dir=os.path.dirname(path), text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.chmod(tmp_path, 0o600)
        if IS_INSTALLED and run_command(["chown", f"{SERVICE_USER}:{SERVICE_USER}", tmp_path]) != 0:
            raise OSError("无法设置配置文件所有者")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

def save_config(config):
    try:
        write_json_atomic(CONFIG_FILE, config)
    except OSError as e:
        print(f"\n❌ 配置保存失败: {e}")
        return False
    restart_code = run_command(["sudo", "systemctl", "restart", "tg_name.service"])
    if restart_code == 0:
        print("\n✅ 配置已保存，后台服务已自动重启！")
    else:
        print("\n⚠️ 配置已保存，但后台服务重启失败，请使用 [2] 查看日志。")
    return True

def save_config_and_pause(config):
    save_config(config)
    input("按回车键返回主菜单...")

def clear_screen():
    run_command(["clear"])

def download_remote_file(filename, target):
    fd = None
    tmp_target = None
    try:
        target_dir = os.path.dirname(target)
        fd, tmp_target = tempfile.mkstemp(
            prefix=f"{os.path.basename(target)}.{os.getpid()}.{secrets.token_hex(4)}.",
            suffix=".tmp",
            dir=target_dir
        )
        req = urllib.request.Request(
            remote_file_url(filename),
            headers={'Cache-Control': 'no-cache, no-store', 'Pragma': 'no-cache'}
        )
        with os.fdopen(fd, 'wb') as f:
            fd = None
            with urllib.request.urlopen(req, timeout=20) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_REMOTE_FILE_SIZE:
                    raise ValueError("远程文件超过大小限制")
                downloaded = 0
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > MAX_REMOTE_FILE_SIZE:
                        raise ValueError("远程文件超过大小限制")
                    f.write(chunk)
        os.chmod(tmp_target, 0o644)
        return 0, tmp_target
    except Exception as e:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_target:
            try:
                os.unlink(tmp_target)
            except OSError:
                pass
        print(f"下载 {filename} 失败: {e}")
        return 1, tmp_target or ""

def validate_python_file(path, required_symbols=()):
    try:
        if os.path.getsize(path) > MAX_REMOTE_FILE_SIZE:
            return False
        with open(path, 'r', encoding='utf-8-sig') as f:
            tree = ast.parse(f.read(), filename=path)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return False

    symbols = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            symbols.update(target.id for target in targets if isinstance(target, ast.Name))
    return all(symbol in symbols for symbol in required_symbols)

def validate_requirements_file(path):
    try:
        if os.path.getsize(path) > 64 * 1024:
            return False
        with open(path, 'r', encoding='ascii') as f:
            lines = [line.strip() for line in f if line.strip() and not line.lstrip().startswith('#')]
    except (OSError, UnicodeDecodeError):
        return False

    return bool(lines) and all(re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+", line) for line in lines)

def install_requirements_file(path):
    pip_path = "/opt/tg_updater/venv/bin/pip"
    if not os.path.exists(pip_path):
        print("❌ 未找到虚拟环境 pip，请重新执行安装命令。")
        return False
    return run_command([pip_path, "install", "--no-cache-dir", "--no-compile", "-r", path]) == 0

def replace_remote_file(tmp_target, target):
    return run_command(["sudo", "mv", tmp_target, target])

def replace_remote_files(file_pairs):
    backup_suffix = f".bak.{os.getpid()}.{secrets.token_hex(4)}"
    backups = []
    replaced = []
    for tmp_path, target_path in file_pairs:
        backup_path = f"{target_path}{backup_suffix}"
        if os.path.exists(target_path):
            if run_command(["sudo", "cp", "-p", target_path, backup_path]) != 0:
                cleanup_temp_files(*(backup for _, backup in backups if backup))
                return None
        else:
            backup_path = None
        backups.append((target_path, backup_path))

    for tmp_path, target_path in file_pairs:
        if replace_remote_file(tmp_path, target_path) != 0:
            restored = restore_remote_files(replaced)
            if restored:
                cleanup_temp_files(*(backup for _, backup in backups if backup))
            cleanup_temp_files(*(tmp for tmp, _ in file_pairs))
            return None
        replaced.append((target_path, dict(backups)[target_path]))

    return backups

def restore_remote_files(backups):
    restored = True
    for target_path, backup_path in backups:
        if backup_path:
            if run_command(["sudo", "cp", "-p", backup_path, target_path]) != 0:
                restored = False
        elif run_command(["sudo", "rm", "-f", target_path]) != 0:
            restored = False
    return restored

def cleanup_temp_files(*paths):
    existing_paths = [path for path in paths if path and os.path.exists(path)]
    if existing_paths:
        run_command(["sudo", "rm", "-f", *existing_paths])

def uninstall_script():
    if BASE_DIR != "/opt/tg_updater":
        input("❌ 当前面板不在 /opt/tg_updater，已取消卸载以避免误删。按回车键返回主菜单...")
        return

    print("\n⚠️ 即将卸载 TelegramNameUpdate")
    print("将删除以下内容:")
    print("  - systemd 服务: tg_name.service")
    print("  - 全局命令: /usr/local/bin/tg, /usr/local/bin/tg_py")
    print("  - 程序目录: /opt/tg_updater")
    print("  - 配置与登录凭证目录: /var/lib/tg_updater")
    confirm = input("请输入 DELETE 确认卸载 (直接回车取消): ").strip()
    if confirm != "DELETE":
        input("已取消卸载，按回车键返回主菜单...")
        return

    project_dir = "/opt/tg_updater"
    data_dir = "/var/lib/tg_updater"
    allowed_dirs = {project_dir, data_dir}
    for path in allowed_dirs:
        if not path.startswith("/") or path in ("/", "/opt", "/var", "/var/lib"):
            input("❌ 卸载路径校验失败，按回车键返回主菜单...")
            return

    failures = []

    print("\n正在停止并禁用服务...")
    run_command(["sudo", "systemctl", "stop", "tg_name.service"])
    if run_command(["sudo", "systemctl", "is-active", "--quiet", "tg_name.service"]) == 0:
        failures.append("后台服务仍在运行")
    run_command(["sudo", "systemctl", "disable", "tg_name.service"])
    if run_command([
        "sudo", "rm", "-f",
        "/etc/systemd/system/tg_name.service",
        "/etc/systemd/system/multi-user.target.wants/tg_name.service",
    ]) != 0:
        failures.append("systemd 服务文件删除失败")
    if run_command(["sudo", "systemctl", "daemon-reload"]) != 0:
        failures.append("systemd 配置刷新失败")

    print("正在删除快捷命令...")
    if run_command(["sudo", "rm", "-f", "/usr/local/bin/tg", "/usr/local/bin/tg_py"]) != 0:
        failures.append("快捷命令删除失败")

    print("正在删除程序和运行数据...")
    if run_command(["sudo", "rm", "-rf", data_dir]) != 0:
        failures.append("运行数据目录删除失败")
    if run_command(["sudo", "rm", "-rf", project_dir]) != 0:
        failures.append("程序目录删除失败")
    if run_command(["id", "-u", SERVICE_USER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
        if run_command(["sudo", "userdel", SERVICE_USER]) != 0:
            failures.append("专用系统账号删除失败")
    if run_command(["getent", "group", SERVICE_USER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
        if run_command(["sudo", "groupdel", SERVICE_USER]) != 0:
            failures.append("专用系统用户组删除失败")

    remaining_paths = [
        path for path in (
            "/etc/systemd/system/tg_name.service",
            "/etc/systemd/system/multi-user.target.wants/tg_name.service",
            "/usr/local/bin/tg",
            "/usr/local/bin/tg_py",
            data_dir,
            project_dir,
        )
        if os.path.lexists(path)
    ]
    if remaining_paths:
        failures.append("仍有文件未删除: " + ", ".join(remaining_paths))
    if failures:
        print("\n❌ 卸载未完整完成:")
        for failure in failures:
            print(f"  - {failure}")
        print("请检查 sudo 权限并手动清理上述残留。")
        sys.exit(1)
    print("\n✅ 卸载完成。")
    sys.exit(0)

def configure_name_order(config):
    item_keys = DEFAULT_NAME_ORDER
    print("\n当前输出顺序:")
    print(f"  {format_name_order(config['name_order'])}")
    print("\n可选字段:")
    for index, key in enumerate(item_keys, 1):
        print(f"  {index}. {ORDER_LABELS[key]}")
    print("\n请输入新的顺序，例如 1,2,3,4,5,6 或 6,1,2,3,4,5")
    raw_order = input("新顺序 (直接回车取消): ").strip()
    if not raw_order:
        return

    selected = []
    for part in raw_order.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            input("❌ 输入包含非数字项，按回车键返回主菜单...")
            return
        index = int(part)
        if index < 1 or index > len(item_keys):
            input("❌ 输入序号超出范围，按回车键返回主菜单...")
            return
        key = item_keys[index - 1]
        if key not in selected:
            selected.append(key)

    if not selected:
        input("❌ 未输入有效顺序，按回车键返回主菜单...")
        return

    config["name_order"] = normalize_name_order(selected)
    if save_config(config):
        input(f"✅ 输出顺序已更新为: {format_name_order(config['name_order'])}，按回车键返回主菜单...")
    else:
        input("按回车键返回主菜单...")

def get_bio_template_label(template_key):
    registry = bio_template_loader.load_templates(DATA_DIR)
    entry = registry.entries.get(template_key)
    return entry.name if entry else template_key


def render_bio_preview(config):
    birth_date = parse_birth_date(config.get("birth_date"))
    if birth_date is None or not config.get("fixed_bio"):
        return ""
    return build_bio_text(
        birth_date,
        config["fixed_bio"],
        template_name=config.get("bio_template", "elapsed_en"),
        config=config,
    )


def render_bio_preview_strict(config):
    birth_date = parse_birth_date(config.get("birth_date"))
    if birth_date is None or not config.get("fixed_bio"):
        return ""
    return build_bio_text_strict(
        birth_date,
        config["fixed_bio"],
        template_name=config.get("bio_template", "elapsed_en"),
        config=config,
    )


def save_bio_config_or_pause(config, success_message):
    if save_config(config):
        input(success_message)
    else:
        input("按回车键继续...")


def reset_bio_state_for_new_config():
    try:
        if os.path.lexists(BIO_STATE_FILE):
            os.unlink(BIO_STATE_FILE)
    except OSError as exc:
        print(color(f"⚠️ Bio 状态重置失败: {exc}", "yellow"))


def toggle_bio_enabled(config):
    if config.get("bio_enabled"):
        config["bio_enabled"] = False
        save_bio_config_or_pause(config, "✅ Bio 自动更新已关闭，按回车键继续...")
        return

    birth_date = parse_birth_date(config.get("birth_date"))
    if birth_date is None or not config.get("fixed_bio"):
        input("❌ 请先设置出生日期和固定 Bio，按回车键继续...")
        return

    try:
        preview = render_bio_preview_strict(config)
    except Exception as exc:
        input(f"❌ Bio 模板渲染失败: {exc}。按回车键继续...")
        return
    if not preview or len(preview) > MAX_BIO_LENGTH:
        input(f"❌ Bio 预览无效或超过 {MAX_BIO_LENGTH} 字符，按回车键继续...")
        return

    config["bio_enabled"] = True
    reset_bio_state_for_new_config()
    save_bio_config_or_pause(config, "✅ Bio 自动更新已开启，按回车键继续...")


def set_bio_birth_date(config):
    current = config.get("birth_date", "")
    raw_value = input(f"出生日期 YYYY-MM-DD [{current}]: ").strip() or current
    birth_date = parse_birth_date(raw_value)
    if birth_date is None:
        input("❌ 出生日期无效或晚于今天，按回车键继续...")
        return
    config["birth_date"] = birth_date.isoformat()
    config["bio_enabled"] = False
    save_bio_config_or_pause(config, "✅ 出生日期已保存，Bio 已暂时关闭，请确认预览后重新开启。按回车键继续...")


def set_bio_fixed_text(config):
    current = config.get("fixed_bio", "")
    value = input(f"固定 Bio [{current}]: ").strip() or current
    value = "".join(char for char in value if char.isprintable())
    if not value:
        input("❌ 固定 Bio 不能为空，按回车键继续...")
        return
    config["fixed_bio"] = value[:MAX_BIO_LENGTH]
    config["bio_enabled"] = False
    save_bio_config_or_pause(config, "✅ 固定 Bio 已保存，Bio 已暂时关闭，请确认预览后重新开启。按回车键继续...")


def select_bio_template(config):
    registry = bio_template_loader.load_templates(DATA_DIR)
    entries = list(registry.entries.values())
    if not entries:
        input("❌ 没有可用 Bio 模板，按回车键继续...")
        return

    print("\n可用 Bio 模板:")
    for index, entry in enumerate(entries, 1):
        marker = " (当前)" if entry.key == config.get("bio_template") else ""
        description = f"  {entry.description}" if entry.description else ""
        print(f"[{index}] {entry.name}  {entry.source}{description}{marker}")

    raw_value = input("请选择模板编号 ([0] 返回): ").strip()
    if raw_value == "0":
        return
    if not raw_value.isdigit() or not 1 <= int(raw_value) <= len(entries):
        input("❌ Bio 模板选项无效，按回车键继续...")
        return

    selected = entries[int(raw_value) - 1]
    previous = config.get("bio_template", "elapsed_en")
    config["bio_template"] = selected.key
    try:
        preview = render_bio_preview_strict(config)
    except Exception as exc:
        config["bio_template"] = previous
        input(f"❌ Bio 模板渲染失败: {exc}。按回车键继续...")
        return
    if preview and len(preview) > MAX_BIO_LENGTH:
        config["bio_template"] = previous
        input(f"❌ 完整 Bio 长度为 {len(preview)}，超过 Telegram 的 {MAX_BIO_LENGTH} 字符限制。按回车键继续...")
        return
    config["bio_enabled"] = False
    save_bio_config_or_pause(config, "✅ Bio 模板已保存，Bio 已暂时关闭，请确认预览后重新开启。按回车键继续...")


def preview_current_bio(config):
    preview = render_bio_preview(config)
    if not preview:
        input("❌ 请先设置出生日期和固定 Bio，按回车键继续...")
        return
    input(f"Bio 预览: {preview}\n长度: {len(preview)}/{MAX_BIO_LENGTH}\n按回车键继续...")


def show_bio_template_path():
    input(f"用户模板文件:\n{bio_template_loader.get_user_template_path(DATA_DIR)}\n按回车键继续...")


def configure_bio(config):
    while True:
        print("\n" + color("Bio 自动更新", "cyan", "bold"))
        print(f"当前状态: {state_text(config.get('bio_enabled', False))}")
        print(f"当前模板: {safe_display(get_bio_template_label(config.get('bio_template', 'elapsed_en')))}")
        print(f"出生日期: {safe_display(config.get('birth_date') or '未设置')}")
        print(f"固定 Bio: {safe_display(config.get('fixed_bio') or '未设置')}")
        preview = render_bio_preview(config)
        if preview:
            print(f"今日预览: {safe_display(preview)}")
        registry = bio_template_loader.load_templates(DATA_DIR)
        for error in registry.errors:
            print(color(f"模板提示: {error}", "yellow"))

        print("\n[1] 开启 / 关闭 Bio 自动更新")
        print("[2] 设置出生日期")
        print("[3] 设置固定 Bio")
        print("[4] 选择 Bio 模板")
        print("[5] 预览当前 Bio")
        print("[6] 查看用户模板文件路径")
        print("[0] 返回主菜单")
        choice = input("请选择: ").strip()

        if choice == "1":
            toggle_bio_enabled(config)
        elif choice == "2":
            set_bio_birth_date(config)
        elif choice == "3":
            set_bio_fixed_text(config)
        elif choice == "4":
            select_bio_template(config)
        elif choice == "5":
            preview_current_bio(config)
        elif choice == "6":
            show_bio_template_path()
        elif choice == "0":
            return
        else:
            input("❌ 无效选项，按回车键继续...")

def configure_update_interval(config):
    print(f"\n当前 Last Name 更新频率: 每 {config['update_interval']} 分钟")
    print("可选频率:")
    for index, interval in enumerate(UPDATE_INTERVALS, 1):
        if interval == 60:
            schedule = "每小时整点"
        elif interval == 1:
            schedule = "每个整分钟"
        else:
            schedule = "每小时 " + "、".join(f"{minute:02d} 分" for minute in range(0, 60, interval))
        print(f"  {index}. {interval} 分钟 ({schedule})")

    choice = input("请选择频率 (直接回车取消): ").strip()
    if not choice:
        return
    if not choice.isdigit() or not 1 <= int(choice) <= len(UPDATE_INTERVALS):
        input("❌ 选项无效，按回车键返回主菜单...")
        return

    config["update_interval"] = UPDATE_INTERVALS[int(choice) - 1]
    if save_config(config):
        input(f"✅ Last Name 更新频率已设置为每 {config['update_interval']} 分钟，按回车键返回主菜单...")
    else:
        input("按回车键返回主菜单...")

def configure_digit_style(config):
    style_keys = list(DIGIT_STYLES)
    print("\n请选择数字字体:")
    for index, key in enumerate(style_keys, 1):
        marker = " (当前)" if key == config["digit_style"] else ""
        sample = "0123456789".translate(str.maketrans("0123456789", {
            "normal": "0123456789",
            "sans_bold": "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵",
            "serif_bold": "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗",
            "double_struck": "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡",
        }[key]))
        print(f"  {index}. {sample}{marker}")

    choice = input("请选择字体 (直接回车取消): ").strip()
    if not choice:
        return
    if not choice.isdigit() or not 1 <= int(choice) <= len(style_keys):
        input("❌ 选项无效，按回车键返回主菜单...")
        return

    config["digit_style"] = style_keys[int(choice) - 1]
    if save_config(config):
        input(f"✅ 数字字体已切换为 {DIGIT_STYLES[config['digit_style']]}，按回车键返回主菜单...")
    else:
        input("按回车键返回主菜单...")

def configure_letter_style(config):
    style_keys = list(LETTER_STYLES)
    print("\n请选择英文字母字体:")
    for index, key in enumerate(style_keys, 1):
        marker = " (当前)" if key == config["letter_style"] else ""
        print(f"  {index}. {LETTER_STYLES[key]}{marker}")

    choice = input("请选择字体 (直接回车取消): ").strip()
    if not choice:
        return
    if not choice.isdigit() or not 1 <= int(choice) <= len(style_keys):
        input("❌ 选项无效，按回车键返回主菜单...")
        return

    config["letter_style"] = style_keys[int(choice) - 1]
    if save_config(config):
        input(f"✅ 英文字母字体已切换为 {LETTER_STYLES[config['letter_style']]}，按回车键返回主菜单...")
    else:
        input("按回车键返回主菜单...")

def read_last_name_items(prompt):
    print("\n可选字段:")
    item_types = LAST_NAME_ITEM_TYPES
    for index, item_type in enumerate(item_types, 1):
        print(f"  {index}. {ORDER_LABELS[item_type]}")
    print("请输入输出顺序，例如 7,1,2,4。选择自定义文本时会继续要求输入内容。")
    raw_order = input(prompt).strip()
    if not raw_order:
        return None

    items = []
    for part in raw_order.replace("，", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or not 1 <= int(part) <= len(item_types):
            input("❌ 输入序号无效，按回车键继续...")
            return None
        item_type = item_types[int(part) - 1]
        if item_type == "text":
            text = normalize_last_name_text(input("自定义文本 / Emoji: "))
            if not text:
                input("❌ 自定义文本不能为空，按回车键继续...")
                return None
            items.append({"type": "text", "value": text})
        else:
            items.append({"type": item_type})
    normalized = normalize_last_name_items(items)
    if not normalized:
        input("❌ 未输入有效输出内容，按回车键继续...")
        return None
    return normalized

def print_last_name_rules(config):
    print(f"当前模式: {'自定义' if config['last_name_mode'] == 'custom' else '经典'}")
    print(f"默认输出: {format_last_name_items(config['last_name_default_items'])}")
    if not config["last_name_rules"]:
        print("时间段规则: 暂无")
        return
    print("时间段规则:")
    for index, rule in enumerate(config["last_name_rules"], 1):
        suffix = " (跨午夜)" if rule["start"] > rule["end"] else ""
        print(f"  {index}. {safe_display(rule['name'])}  {rule['start']}-{rule['end']}{suffix}")
        print(f"     {format_last_name_items(rule['items'])}")

def configure_last_name_rules(config):
    while True:
        clear_screen()
        print(color("Last Name 规则", "cyan", "bold"))
        print("经典模式继续使用展示开关、输出顺序和 Emoji 时段。")
        print("自定义模式会按时间段规则输出完整 Last Name；没有命中规则时使用默认输出。\n")
        print_last_name_rules(config)
        print("\n  [1] 切换经典 / 自定义模式")
        print("  [2] 设置默认输出")
        print("  [3] 添加时间段规则")
        print("  [4] 删除时间段规则")
        print("  [5] 清空时间段规则")
        print("  [6] 经典 Emoji 时段")
        print("  [0] 返回主菜单")
        choice = input("\n请选择操作: ").strip()

        if choice == "0":
            return

        if choice == "1":
            old_mode = config["last_name_mode"]
            config["last_name_mode"] = "custom" if old_mode == "classic" else "classic"
            if save_config(config):
                input(f"✅ Last Name 模式已切换为 {'自定义' if config['last_name_mode'] == 'custom' else '经典'}，按回车键继续...")
            else:
                config["last_name_mode"] = old_mode
                input("按回车键继续...")
            continue

        if choice == "2":
            items = read_last_name_items("默认输出顺序 (直接回车取消): ")
            if items is None:
                continue
            old_items = config["last_name_default_items"]
            config["last_name_default_items"] = items
            if save_config(config):
                input("✅ 默认输出已更新，按回车键继续...")
            else:
                config["last_name_default_items"] = old_items
                input("按回车键继续...")
            continue

        if choice == "3":
            if len(config["last_name_rules"]) >= MAX_LAST_NAME_RULES:
                input(f"❌ 最多只能添加 {MAX_LAST_NAME_RULES} 条规则，按回车键继续...")
                continue
            name = normalize_last_name_text(input("规则名称: "))[:MAX_LAST_NAME_RULE_NAME_LENGTH]
            start = parse_time_text(input("开始时间 HH:MM: ").strip())
            end = parse_time_text(input("结束时间 HH:MM: ").strip())
            if not start or not end or start == end:
                input("❌ 时间格式无效，且开始时间不能等于结束时间。按回车键继续...")
                continue
            items = read_last_name_items("规则输出顺序 (直接回车取消): ")
            if items is None:
                continue
            candidate = {
                "name": name or f"{start}-{end}",
                "start": start,
                "end": end,
                "items": items,
            }
            config["last_name_rules"].append(candidate)
            if save_config(config):
                input("✅ Last Name 规则已添加，按回车键继续...")
            else:
                config["last_name_rules"].pop()
                input("按回车键继续...")
            continue

        if choice == "4":
            if not config["last_name_rules"]:
                input("暂无可删除规则，按回车键继续...")
                continue
            raw_index = input("请输入要删除的规则编号 (直接回车取消): ").strip()
            if not raw_index:
                continue
            if not raw_index.isdigit() or not 1 <= int(raw_index) <= len(config["last_name_rules"]):
                input("❌ 规则编号无效，按回车键继续...")
                continue
            removed = config["last_name_rules"].pop(int(raw_index) - 1)
            if save_config(config):
                input(f"✅ 已删除 {safe_display(removed['name'])}，按回车键继续...")
            else:
                config["last_name_rules"].insert(int(raw_index) - 1, removed)
                input("按回车键继续...")
            continue

        if choice == "5":
            if input("输入 DELETE 确认清空全部 Last Name 规则: ").strip() == "DELETE":
                old_rules = config["last_name_rules"]
                config["last_name_rules"] = []
                if save_config(config):
                    input("✅ Last Name 规则已清空，按回车键继续...")
                else:
                    config["last_name_rules"] = old_rules
                    input("按回车键继续...")
            continue

        if choice == "6":
            configure_emoji_schedules(config)
            config = load_config()
            continue

        input("❌ 选项无效，按回车键继续...")

def print_emoji_schedules(schedules):
    if not schedules:
        print("  暂无规则")
        return
    for index, rule in enumerate(schedules, 1):
        suffix = " (跨午夜)" if rule["start"] > rule["end"] else ""
        print(f"  {index}. {rule['start']}-{rule['end']}  {rule['emoji']}{suffix}")

def configure_emoji_schedules(config):
    while True:
        clear_screen()
        print(color("Emoji 时段规则", "cyan", "bold"))
        print("时间区间为左闭右开，例如 09:00-12:00 在 12:00 停止显示。")
        print("多条规则同时命中时，Emoji 会按规则顺序合并。\n")
        print_emoji_schedules(config["emoji_schedules"])
        print("\n  [1] 添加规则")
        print("  [2] 删除规则")
        print("  [3] 清空规则")
        print("  [0] 返回主菜单")
        choice = input("\n请选择操作: ").strip()

        if choice == "0":
            return

        if choice == "1":
            if len(config["emoji_schedules"]) >= MAX_EMOJI_RULES:
                input(f"❌ 最多只能添加 {MAX_EMOJI_RULES} 条规则，按回车键继续...")
                continue
            start = parse_time_text(input("开始时间 HH:MM: ").strip())
            end = parse_time_text(input("结束时间 HH:MM: ").strip())
            emoji = sanitize_emoji_text(input("Emoji (可输入多个): ").strip())
            if not start or not end or start == end:
                input("❌ 时间格式无效，且开始时间不能等于结束时间。按回车键继续...")
                continue
            if not emoji:
                input("❌ Emoji 无效或过长，请至少输入一个 Emoji。按回车键继续...")
                continue
            candidate = {"start": start, "end": end, "emoji": emoji}
            if max_active_emoji_length([*config["emoji_schedules"], candidate]) > MAX_ACTIVE_EMOJI_LENGTH:
                input(f"❌ 所有规则同时命中时最多允许 {MAX_ACTIVE_EMOJI_LENGTH} 个字符，请减少 Emoji。按回车键继续...")
                continue
            config["emoji_schedules"].append(candidate)
            if save_config(config):
                input("✅ Emoji 规则已添加，按回车键继续...")
            else:
                config["emoji_schedules"].pop()
                input("按回车键继续...")
            continue

        if choice == "2":
            if not config["emoji_schedules"]:
                input("暂无可删除规则，按回车键继续...")
                continue
            raw_index = input("请输入要删除的规则编号 (直接回车取消): ").strip()
            if not raw_index:
                continue
            if not raw_index.isdigit() or not 1 <= int(raw_index) <= len(config["emoji_schedules"]):
                input("❌ 规则编号无效，按回车键继续...")
                continue
            removed = config["emoji_schedules"].pop(int(raw_index) - 1)
            if save_config(config):
                input(f"✅ 已删除 {removed['start']}-{removed['end']} {removed['emoji']}，按回车键继续...")
            else:
                config["emoji_schedules"].insert(int(raw_index) - 1, removed)
                input("按回车键继续...")
            continue

        if choice == "3":
            if input("输入 DELETE 确认清空全部规则: ").strip() == "DELETE":
                previous_schedules = config["emoji_schedules"]
                config["emoji_schedules"] = []
                if save_config(config):
                    input("✅ Emoji 规则已清空，按回车键继续...")
                else:
                    config["emoji_schedules"] = previous_schedules
                    input("按回车键继续...")
            continue

        input("❌ 选项无效，按回车键继续...")

def main_menu():
    migrate_legacy_runtime_files()
    while True:
        clear_screen()
        config = load_config()
        render_menu(config)
        
        choice = input(color("请输入选项 (0-19, 99): ", "cyan", "bold")).strip()
        
        if choice == '0':
            print("退出面板。")
            sys.exit()
            
        elif choice == '99':
            uninstall_script()
            
        elif choice == '1':
            harden_code_files()
            service_was_active = run_command(["sudo", "systemctl", "is-active", "--quiet", "tg_name.service"]) == 0
            print("正在停止后台服务...")
            run_command(["sudo", "systemctl", "stop", "tg_name.service"])
            if run_command(["sudo", "systemctl", "is-active", "--quiet", "tg_name.service"]) == 0:
                input("❌ 后台服务未能停止，为避免 Session 冲突，已取消登录。按回车键返回主菜单...")
                continue
            try:
                session_backups = backup_session_files()
            except OSError as e:
                if service_was_active:
                    run_command(["sudo", "systemctl", "restart", "tg_name.service"])
                input(f"❌ 旧凭证备份失败: {e}。按回车键返回主菜单...")
                continue

            try:
                print("旧凭证已临时备份，请按提示重新登录：")
                venv_python = os.path.join(os.path.dirname(__file__), 'venv', 'bin', 'python3')
                if not os.path.exists(venv_python):
                    venv_python = sys.executable
                daemon_path = os.path.join(os.path.dirname(__file__), 'tg_daemon.py')
                chown_runtime_files()
                login_command = [venv_python, daemon_path, '--login']
                if IS_INSTALLED and run_command(["id", "-u", SERVICE_USER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                    login_command = command_as_user(SERVICE_USER, login_command)
                login_result = run_command(login_command)
                if login_result == 0:
                    backups_removed = remove_session_backups(session_backups)
                    chown_runtime_files()
                    print("\n正在重启后台服务...")
                    restart_code = run_command(["sudo", "systemctl", "restart", "tg_name.service"])
                    if restart_code == 0:
                        message = "✅ 配置已生效"
                        if not backups_removed:
                            message += "，但旧 Session 备份清理失败"
                        input(f"{message}。按回车键返回主菜单...")
                    else:
                        input("⚠️ 登录成功，但后台服务重启失败，请使用 [2] 查看日志。按回车键返回主菜单...")
                else:
                    restored = restore_session_files(session_backups)
                    chown_runtime_files()
                    service_restored = not service_was_active or run_command(["sudo", "systemctl", "restart", "tg_name.service"]) == 0
                    if restored and service_restored:
                        input("❌ 登录失败，已恢复旧 Session 和原服务状态。按回车键返回主菜单...")
                    else:
                        input("❌ 登录失败，旧 Session 或服务状态未能完整恢复，请检查 [2] 日志。按回车键返回主菜单...")
            except (OSError, KeyboardInterrupt) as e:
                restored = restore_session_files(session_backups)
                chown_runtime_files()
                if service_was_active:
                    run_command(["sudo", "systemctl", "restart", "tg_name.service"])
                input(f"❌ 登录过程已中断，旧 Session {'已恢复' if restored else '恢复失败'}: {e}。按回车键返回主菜单...")
            
        elif choice == '2':
            print("\n--- 最近 50 条系统运行日志 ---\n")
            run_command(["sudo", "journalctl", "-u", "tg_name.service", "-n", "50", "--no-pager"])
            print("\n------------------------------\n")
            input("按回车键返回主菜单...")
            
        elif choice == '3':
            config['show_time'] = not config['show_time']
            save_config_and_pause(config)
            
        elif choice == '4':
            config['show_timezone'] = not config['show_timezone']
            save_config_and_pause(config)
            
        elif choice == '5':
            config['show_date'] = not config['show_date']
            save_config_and_pause(config)
            
        elif choice == '6':
            config['show_temp'] = not config['show_temp']
            save_config_and_pause(config)
            
        elif choice == '7':
            config['show_weather'] = not config['show_weather']
            save_config_and_pause(config)
            
        elif choice == '8':
            configure_digit_style(config)
            
        elif choice == '9':
            configure_letter_style(config)
            
        elif choice == '10':
            new_loc = input("请输入新的城市名称 (拼音或英文): ").strip()
            if new_loc:
                if len(new_loc) > MAX_LOCATION_LENGTH:
                    input(f"❌ 地区名称过长，请限制在 {MAX_LOCATION_LENGTH} 个字符内。按回车键返回主菜单...")
                    continue
                config['location'] = new_loc
                save_config_and_pause(config)
                
        elif choice == '11':
            configure_name_order(config)
                
        elif choice == '12':
            config.update({"show_time": True, "show_timezone": True, "show_date": True, "show_temp": True, "show_weather": True})
            save_config_and_pause(config)
            
        elif choice == '13':
            configure_bio(config)

        elif choice == '14':
            configure_update_interval(config)

        elif choice == '15':
            configure_last_name_rules(config)

        elif choice == '16':
            print("\n正在强制重启后台服务...")
            restart_code = run_command(["sudo", "systemctl", "restart", "tg_name.service"])
            if restart_code == 0:
                print("✅ 服务已重启，Last Name 将在下一个设定时间点更新。")
            else:
                print("❌ 服务重启失败，请使用 [2] 查看日志。")
            input("按回车键返回主菜单...")
            
        elif choice == '17':
            if BASE_DIR != "/opt/tg_updater":
                input("❌ 当前面板不在 /opt/tg_updater，已取消更新以避免覆盖安装目录。按回车键返回主菜单...")
                continue
            harden_code_files()
            print("\n>> 正在从 GitHub 检查最新版本...")
            remote_version = get_remote_version()
            remote_compare = compare_versions(remote_version, CURRENT_VERSION)
            if remote_compare == 0:
                print(f">> GitHub 返回版本与本地相同 ({CURRENT_VERSION})，将继续拉取并校验实际下载文件。")
            elif remote_compare and remote_compare > 0:
                print(f">> GitHub 返回新版本 {remote_version}，正在拉取最新代码...")
            elif remote_compare and remote_compare < 0:
                print(f">> GitHub 返回版本 {remote_version}，低于本地版本 {CURRENT_VERSION}，将下载后再次校验，避免误降级。")
            elif remote_version:
                print(f">> GitHub 返回版本 {remote_version}，正在拉取并校验实际下载文件...")
            else:
                print(">> 无法获取远程版本号，仍尝试拉取最新代码...")
            daemon_target = "/opt/tg_updater/tg_daemon.py"
            panel_target = "/opt/tg_updater/tg_panel.py"
            bio_templates_target = "/opt/tg_updater/bio_templates.py"
            bio_template_loader_target = "/opt/tg_updater/bio_template_loader.py"
            requirements_target = "/opt/tg_updater/requirements.txt"
            res1, daemon_tmp = download_remote_file("tg_daemon.py", daemon_target)
            res2, panel_tmp = download_remote_file("tg_panel.py", panel_target)
            res3, bio_templates_tmp = download_remote_file("bio_templates.py", bio_templates_target)
            res4, bio_template_loader_tmp = download_remote_file("bio_template_loader.py", bio_template_loader_target)
            res5, requirements_tmp = download_remote_file("requirements.txt", requirements_target)
            
            if res1 == 0 and res2 == 0 and res3 == 0 and res4 == 0 and res5 == 0:
                daemon_valid = validate_python_file(daemon_tmp, ("main", "change_name_auto"))
                panel_valid = validate_python_file(panel_tmp, ("CURRENT_VERSION", "main_menu"))
                bio_templates_valid = validate_python_file(bio_templates_tmp, ("BIO_TEMPLATES", "render_bio"))
                bio_template_loader_valid = validate_python_file(bio_template_loader_tmp, ("load_templates", "render_bio"))
                requirements_valid = validate_requirements_file(requirements_tmp)
                if not daemon_valid or not panel_valid or not bio_templates_valid or not bio_template_loader_valid or not requirements_valid:
                    cleanup_temp_files(daemon_tmp, panel_tmp, bio_templates_tmp, bio_template_loader_tmp, requirements_tmp)
                    print("\n❌ 更新失败！下载文件未通过语法或依赖格式校验，已取消覆盖。")
                    input("按回车键返回主菜单...")
                    continue

                downloaded_version = extract_version_from_file(panel_tmp)
                if downloaded_version is None or parse_version(downloaded_version) is None:
                    cleanup_temp_files(daemon_tmp, panel_tmp, bio_templates_tmp, bio_template_loader_tmp, requirements_tmp)
                    print("\n❌ 更新失败！下载到的面板脚本版本号缺失或格式无效，已取消覆盖。")
                    input("按回车键返回主菜单...")
                    continue
                downloaded_compare = compare_versions(downloaded_version, CURRENT_VERSION)
                if downloaded_compare is not None and downloaded_compare < 0:
                    cleanup_temp_files(daemon_tmp, panel_tmp, bio_templates_tmp, bio_template_loader_tmp, requirements_tmp)
                    print(f"\n❌ 已取消更新：下载到的版本是 {downloaded_version}，低于当前版本 {CURRENT_VERSION}。")
                    print("请确认 GitHub main 分支已经推送最新代码，或等待 raw.githubusercontent.com 缓存刷新。")
                    input("按回车键返回主菜单...")
                    continue
                if downloaded_compare == 0:
                    print(f">> 下载文件版本与本地相同 ({CURRENT_VERSION})，继续覆盖以同步文件内容。")
                elif downloaded_version:
                    print(f">> 下载文件版本确认: {downloaded_version}")

                service_was_active = run_command(["sudo", "systemctl", "is-active", "--quiet", "tg_name.service"]) == 0
                try:
                    with open(requirements_target, 'rb') as current_file, open(requirements_tmp, 'rb') as new_file:
                        requirements_changed = current_file.read() != new_file.read()
                except OSError:
                    requirements_changed = True
                backups = replace_remote_files((
                    (daemon_tmp, daemon_target),
                    (panel_tmp, panel_target),
                    (bio_templates_tmp, bio_templates_target),
                    (bio_template_loader_tmp, bio_template_loader_target),
                    (requirements_tmp, requirements_target),
                ))
                if backups is not None:
                    update_ok = harden_code_files()
                    if update_ok and requirements_changed:
                        print(">> 依赖文件发生变化，正在同步 Python 虚拟环境...")
                        update_ok = install_requirements_file(requirements_target)
                    if update_ok and service_was_active:
                        print(">> 正在重启后台服务并检查运行状态...")
                        update_ok = run_command(["sudo", "systemctl", "restart", "tg_name.service"]) == 0
                        if update_ok:
                            time.sleep(2)
                            update_ok = run_command(["sudo", "systemctl", "is-active", "--quiet", "tg_name.service"]) == 0

                    if update_ok:
                        cleanup_temp_files(*(backup for _, backup in backups))
                        if service_was_active:
                            print("\n✅ 更新成功！核心代码与后台服务均已同步至 GitHub 最新版本。")
                        else:
                            print("\n✅ 更新成功！后台服务原本未运行，因此保持停止状态。")
                    else:
                        print("\n⚠️ 新版本未能正常运行，正在恢复更新前文件...")
                        restored = restore_remote_files(backups)
                        if restored:
                            harden_code_files()
                            cleanup_temp_files(*(backup for _, backup in backups))
                            rollback_started = not service_was_active or run_command(["sudo", "systemctl", "restart", "tg_name.service"]) == 0
                            if rollback_started:
                                print("❌ 更新失败，已自动恢复旧版本。")
                            else:
                                print("❌ 已恢复旧文件，但后台服务重启失败，请使用 [2] 查看日志。")
                        else:
                            print("❌ 更新和自动恢复均失败，备份文件已保留在 /opt/tg_updater，请勿继续更新并检查磁盘与权限。")
                    print("⚠️ 提示：当前面板仍是内存中的旧界面，请输入 [0] 退出后重新运行 'tg'。")
                else:
                    cleanup_temp_files(daemon_tmp, panel_tmp, bio_templates_tmp, bio_template_loader_tmp, requirements_tmp)
                    print("\n❌ 更新失败！文件替换失败，已尝试恢复旧版本，请检查 /opt/tg_updater 权限。")
            else:
                cleanup_temp_files(daemon_tmp, panel_tmp, bio_templates_tmp, bio_template_loader_tmp, requirements_tmp)
                print("\n❌ 更新失败！请检查 VPS 网络连接或 GitHub 仓库地址是否正确。")
            input("按回车键返回主菜单...")
            
        elif choice == '18':
            loc = config.get('location', '').lower()
            # 建立常见城市与标准时区 (IANA) 的映射字典
            tz_mapping = {
                "beijing": "Asia/Shanghai", "北京": "Asia/Shanghai",
                "shanghai": "Asia/Shanghai", "上海": "Asia/Shanghai",
                "guangzhou": "Asia/Shanghai", "广州": "Asia/Shanghai",
                "shenzhen": "Asia/Shanghai", "深圳": "Asia/Shanghai",
                "hong kong": "Asia/Hong_Kong", "香港": "Asia/Hong_Kong",
                "taipei": "Asia/Taipei", "台北": "Asia/Taipei",
                "tokyo": "Asia/Tokyo", "东京": "Asia/Tokyo",
                "seoul": "Asia/Seoul", "首尔": "Asia/Seoul",
                "singapore": "Asia/Singapore", "新加坡": "Asia/Singapore",
                "london": "Europe/London", "伦敦": "Europe/London",
                "new york": "America/New_York", "纽约": "America/New_York",
                "los angeles": "America/Los_Angeles", "洛杉矶": "America/Los_Angeles",
                "san francisco": "America/Los_Angeles", "旧金山": "America/Los_Angeles",
                "sydney": "Australia/Sydney", "悉尼": "Australia/Sydney"
            }
            
            target_tz = tz_mapping.get(loc)
            timezone_changed = False
            if target_tz:
                print(f"\n>> 识别到设定城市 [{config['location']}]，正在修改 VPS 系统时区为: {target_tz}...")
                timezone_changed = run_command(["sudo", "timedatectl", "set-timezone", target_tz]) == 0
                if timezone_changed:
                    print("✅ 时区同步成功！改名显示将按当前服务器时区显示 UTC 偏移。")
                else:
                    print("❌ 时区同步失败，请检查 sudo 权限或系统是否支持 timedatectl。")
            else:
                print(f"\n❌ 无法自动匹配城市 [{config['location']}] 的标准时区。")
                print("您可以手动输入 IANA 标准时区格式（例如: Asia/Shanghai, America/New_York）")
                manual_tz = input("请输入标准时区 (直接回车取消): ").strip()
                if manual_tz:
                    res = run_command(["sudo", "timedatectl", "set-timezone", manual_tz], stderr=subprocess.DEVNULL)
                    if res == 0:
                        timezone_changed = True
                        print(f"✅ 时区已手动设置为: {manual_tz}！改名显示将按当前服务器时区显示 UTC 偏移。")
                    else:
                        print("❌ 设置失败，请检查时区名称是否拼写正确。")
            
            if timezone_changed:
                print("\n正在重启后台服务刷新显示时间...")
                if run_command(["sudo", "systemctl", "restart", "tg_name.service"]) != 0:
                    print("⚠️ 时区已设置，但后台服务重启失败，请使用 [2] 查看日志。")
            input("按回车键返回主菜单...")

        elif choice == '19':
            trigger_service_update("SIGUSR1", "Last Name")

        elif choice == '20':
            if not config.get("bio_enabled"):
                input("❌ Bio 自动更新尚未开启，请先使用 [13] 完成配置。按回车键返回主菜单...")
                continue
            trigger_service_update("SIGUSR2", "Bio")

        else:
            input("❌ 选项无效，按回车键返回主菜单...")
if __name__ == "__main__":
    main_menu()
