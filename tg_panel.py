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
from datetime import date

# ==========================================
# 【版本定义】
# 每次修改代码推送到 GitHub 前，请手动提升此版本号
# ==========================================
CURRENT_VERSION = "v1.8.2"
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
ORDER_LABELS = {
    "time": "时间",
    "timezone": "时区",
    "date": "日期",
    "temp": "温度",
    "weather": "天气",
    "emoji": "Emoji",
}
DEFAULT_CONFIG = {"show_time": True, "show_timezone": True, "show_date": False, "show_temp": True, "show_weather": True, "location": "Los Angeles", "digit_style": "sans_bold", "name_order": DEFAULT_NAME_ORDER.copy(), "bio_enabled": False, "birth_date": "", "fixed_bio": "", "update_interval": 1, "emoji_schedules": []}
BOOL_CONFIG_KEYS = ("show_time", "show_timezone", "show_date", "show_temp", "show_weather", "bio_enabled")
DIGIT_STYLES = {
    "normal": "1",
    "sans_bold": "𝟭",
    "serif_bold": "𝟏",
    "double_struck": "𝟙",
}
UPDATE_INTERVALS = (1, 5, 15, 30, 60)
MAX_LOCATION_LENGTH = 80
MAX_BIO_LENGTH = 70
MAX_EMOJI_RULES = 20
MAX_EMOJI_TEXT_LENGTH = 32
MAX_ACTIVE_EMOJI_LENGTH = 32
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
        if item in ORDER_LABELS and item not in normalized:
            normalized.append(item)

    for item in DEFAULT_NAME_ORDER:
        if item not in normalized:
            normalized.append(item)

    return normalized

def format_name_order(order):
    return " > ".join(ORDER_LABELS[item] for item in normalize_name_order(order))

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

def build_bio_text(birth_date, fixed_bio, today=None):
    years, months, days = calculate_elapsed(birth_date, today)
    return f"It lasted {years} years {months} months and {days} days | {fixed_bio}"

def sanitize_config(raw_config):
    config = DEFAULT_CONFIG.copy()
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

    location = raw_config.get("location")
    if isinstance(location, str) and location.strip():
        printable_location = "".join(char for char in location.strip() if char.isprintable())
        cleaned_location = " ".join(printable_location.split())
        if cleaned_location:
            config["location"] = cleaned_location[:MAX_LOCATION_LENGTH]

    config["name_order"] = normalize_name_order(raw_config.get("name_order"))
    birth_date = parse_birth_date(raw_config.get("birth_date"))
    if birth_date:
        config["birth_date"] = birth_date.isoformat()

    fixed_bio = raw_config.get("fixed_bio")
    if isinstance(fixed_bio, str):
        config["fixed_bio"] = "".join(char for char in fixed_bio.strip() if char.isprintable())[:MAX_BIO_LENGTH]

    if not config["birth_date"] or not config["fixed_bio"]:
        config["bio_enabled"] = False
    elif len(build_bio_text(birth_date, config["fixed_bio"])) > MAX_BIO_LENGTH:
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
    menu_line("9", "设置地区", f"当前: {safe_display(config['location'])}", "magenta")
    menu_line("10", "输出顺序", format_name_order(config["name_order"]), "magenta")
    menu_line("11", "一键开启全部", "时间 / 时区 / 日期 / 温度 / 天气", "magenta")

    menu_section("自动化设置")
    menu_line("12", "Bio 自动更新", state_text(config['bio_enabled']), "blue")
    menu_line("13", "Last Name 频率", f"每 {config['update_interval']} 分钟", "blue")
    menu_line("14", "Emoji 时段", f"{len(config['emoji_schedules'])} 条规则", "blue")

    menu_section("维护工具")
    menu_line("15", "重启后台服务", "立即重载配置", "green")
    menu_line("16", "检查并更新", "从 GitHub 拉取核心脚本", "green")
    menu_line("17", "同步服务器时区", "改名显示将使用 UTC 偏移", "green")
    menu_line("18", "强制更新 Last Name", "立即按当前配置更新一次", "green")
    menu_line("19", "强制更新 Bio", "立即按当前配置更新一次", "green")

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
    for filename in ("tg_panel.py", "tg_daemon.py", "requirements.txt"):
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
        with open(path, 'r', encoding='utf-8') as f:
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
        with open(path, 'r', encoding='utf-8') as f:
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

def replace_remote_file(tmp_target, target):
    return run_command(["sudo", "mv", tmp_target, target])

def replace_remote_files(file_pairs):
    backup_suffix = f".bak.{os.getpid()}.{secrets.token_hex(4)}"
    backups = []
    replaced = []
    for tmp_path, target_path in file_pairs:
        backup_path = f"{target_path}{backup_suffix}"
        if run_command(["sudo", "cp", "-p", target_path, backup_path]) != 0:
            cleanup_temp_files(*(backup for _, backup in backups))
            return None
        backups.append((target_path, backup_path))

    for tmp_path, target_path in file_pairs:
        if replace_remote_file(tmp_path, target_path) != 0:
            restored = restore_remote_files(replaced)
            if restored:
                cleanup_temp_files(*(backup for _, backup in backups))
            cleanup_temp_files(*(tmp for tmp, _ in file_pairs))
            return None
        replaced.append((target_path, dict(backups)[target_path]))

    return backups

def restore_remote_files(backups):
    restored = True
    for target_path, backup_path in backups:
        if run_command(["sudo", "cp", "-p", backup_path, target_path]) != 0:
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

def configure_bio(config):
    if config.get("bio_enabled"):
        config["bio_enabled"] = False
        if save_config(config):
            input("✅ Bio 自动更新已关闭，按回车键返回主菜单...")
        else:
            input("按回车键返回主菜单...")
        return

    print("\n开启后，每天 03:00 自动更新 Bio。")
    print("每天 02:00-04:00 暂停动态 Last Name，并显示 💤。")
    current_birth_date = config.get("birth_date", "")
    birth_prompt = f"出生日期 YYYY-MM-DD [{current_birth_date}]: " if current_birth_date else "出生日期 YYYY-MM-DD: "
    raw_birth_date = input(birth_prompt).strip() or current_birth_date
    birth_date = parse_birth_date(raw_birth_date)
    if birth_date is None:
        input("❌ 出生日期无效或晚于今天，按回车键返回主菜单...")
        return

    current_fixed_bio = config.get("fixed_bio", "")
    bio_prompt = f"固定 Bio [{current_fixed_bio}]: " if current_fixed_bio else "固定 Bio: "
    fixed_bio = input(bio_prompt).strip() or current_fixed_bio
    fixed_bio = "".join(char for char in fixed_bio if char.isprintable())
    if not fixed_bio:
        input("❌ 固定 Bio 不能为空，按回车键返回主菜单...")
        return

    preview = build_bio_text(birth_date, fixed_bio)
    if len(preview) > MAX_BIO_LENGTH:
        input(f"❌ 完整 Bio 长度为 {len(preview)}，超过 Telegram 的 {MAX_BIO_LENGTH} 字符限制。请缩短固定 Bio。按回车键返回主菜单...")
        return

    config.update({
        "bio_enabled": True,
        "birth_date": birth_date.isoformat(),
        "fixed_bio": fixed_bio,
    })
    bio_state_backup = None
    try:
        if os.path.lexists(BIO_STATE_FILE):
            bio_state_backup = f"{BIO_STATE_FILE}.bak.{os.getpid()}.{secrets.token_hex(4)}"
            os.replace(BIO_STATE_FILE, bio_state_backup)
    except FileNotFoundError:
        pass
    except OSError as e:
        input(f"❌ Bio 状态准备失败: {e}。按回车键返回主菜单...")
        return
    if save_config(config):
        if bio_state_backup:
            try:
                os.unlink(bio_state_backup)
            except OSError:
                print("⚠️ 旧 Bio 状态备份清理失败，不影响新配置运行。")
        print(f"\nBio 预览: {preview}")
        input("✅ Bio 自动更新已开启，按回车键返回主菜单...")
    else:
        if bio_state_backup:
            try:
                os.replace(bio_state_backup, BIO_STATE_FILE)
            except OSError:
                print("⚠️ 配置保存和 Bio 状态恢复均失败，请检查数据目录权限。")
        input("按回车键返回主菜单...")

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
            new_loc = input("请输入新的城市名称 (拼音或英文): ").strip()
            if new_loc:
                if len(new_loc) > MAX_LOCATION_LENGTH:
                    input(f"❌ 地区名称过长，请限制在 {MAX_LOCATION_LENGTH} 个字符内。按回车键返回主菜单...")
                    continue
                config['location'] = new_loc
                save_config_and_pause(config)
                
        elif choice == '10':
            configure_name_order(config)
                
        elif choice == '11':
            config.update({"show_time": True, "show_timezone": True, "show_date": True, "show_temp": True, "show_weather": True})
            save_config_and_pause(config)
            
        elif choice == '12':
            configure_bio(config)

        elif choice == '13':
            configure_update_interval(config)

        elif choice == '14':
            configure_emoji_schedules(config)

        elif choice == '15':
            print("\n正在强制重启后台服务...")
            restart_code = run_command(["sudo", "systemctl", "restart", "tg_name.service"])
            if restart_code == 0:
                print("✅ 服务已重启，Last Name 将在下一个设定时间点更新。")
            else:
                print("❌ 服务重启失败，请使用 [2] 查看日志。")
            input("按回车键返回主菜单...")
            
        elif choice == '16':
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
            requirements_target = "/opt/tg_updater/requirements.txt"
            res1, daemon_tmp = download_remote_file("tg_daemon.py", daemon_target)
            res2, panel_tmp = download_remote_file("tg_panel.py", panel_target)
            res3, requirements_tmp = download_remote_file("requirements.txt", requirements_target)
            
            if res1 == 0 and res2 == 0 and res3 == 0:
                daemon_valid = validate_python_file(daemon_tmp, ("main", "change_name_auto"))
                panel_valid = validate_python_file(panel_tmp, ("CURRENT_VERSION", "main_menu"))
                requirements_valid = validate_requirements_file(requirements_tmp)
                if not daemon_valid or not panel_valid or not requirements_valid:
                    cleanup_temp_files(daemon_tmp, panel_tmp, requirements_tmp)
                    print("\n❌ 更新失败！下载文件未通过语法或依赖格式校验，已取消覆盖。")
                    input("按回车键返回主菜单...")
                    continue

                downloaded_version = extract_version_from_file(panel_tmp)
                if downloaded_version is None or parse_version(downloaded_version) is None:
                    cleanup_temp_files(daemon_tmp, panel_tmp, requirements_tmp)
                    print("\n❌ 更新失败！下载到的面板脚本版本号缺失或格式无效，已取消覆盖。")
                    input("按回车键返回主菜单...")
                    continue
                downloaded_compare = compare_versions(downloaded_version, CURRENT_VERSION)
                if downloaded_compare is not None and downloaded_compare < 0:
                    cleanup_temp_files(daemon_tmp, panel_tmp, requirements_tmp)
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
                    (requirements_tmp, requirements_target),
                ))
                if backups is not None:
                    update_ok = harden_code_files()
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
                    if update_ok and requirements_changed:
                        print("⚠️ 依赖文件已变化，请重新执行 README 中的安装命令以同步虚拟环境。")
                else:
                    cleanup_temp_files(daemon_tmp, panel_tmp, requirements_tmp)
                    print("\n❌ 更新失败！文件替换失败，已尝试恢复旧版本，请检查 /opt/tg_updater 权限。")
            else:
                cleanup_temp_files(daemon_tmp, panel_tmp, requirements_tmp)
                print("\n❌ 更新失败！请检查 VPS 网络连接或 GitHub 仓库地址是否正确。")
            input("按回车键返回主菜单...")
            
        elif choice == '17':
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

        elif choice == '18':
            trigger_service_update("SIGUSR1", "Last Name")

        elif choice == '19':
            if not config.get("bio_enabled"):
                input("❌ Bio 自动更新尚未开启，请先使用 [12] 完成配置。按回车键返回主菜单...")
                continue
            trigger_service_update("SIGUSR2", "Bio")

        else:
            input("❌ 选项无效，按回车键返回主菜单...")
if __name__ == "__main__":
    main_menu()
