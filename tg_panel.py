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
from datetime import date

# ==========================================
# 【版本定义】
# 每次修改代码推送到 GitHub 前，请手动提升此版本号
# ==========================================
CURRENT_VERSION = "v1.5.0"
AUTHOR = "oKafuChino"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = "/var/lib/tg_updater" if BASE_DIR == "/opt/tg_updater" else BASE_DIR
DATA_DIR = os.environ.get("TG_UPDATER_DATA_DIR", DEFAULT_DATA_DIR)
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
SESSION_FILE = os.path.join(DATA_DIR, 'api_auth.session')
SESSION_JOURNAL_FILE = os.path.join(DATA_DIR, 'api_auth.session-journal')
API_CONFIG_FILE = os.path.join(DATA_DIR, 'api_auth.json')
BIO_STATE_FILE = os.path.join(DATA_DIR, 'bio_last_update.txt')
LEGACY_CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
LEGACY_SESSION_FILE = os.path.join(BASE_DIR, 'api_auth.session')
LEGACY_SESSION_JOURNAL_FILE = os.path.join(BASE_DIR, 'api_auth.session-journal')
LEGACY_API_CONFIG_FILE = os.path.join(BASE_DIR, 'api_auth.json')
REPO_URL = "https://raw.githubusercontent.com/oKafuChino/TelegramNameUpdate/main"
SERVICE_USER = "tg_updater"
DEFAULT_NAME_ORDER = ["time", "timezone", "date", "temp", "weather"]
ORDER_LABELS = {
    "time": "时间",
    "timezone": "时区",
    "date": "日期",
    "temp": "温度",
    "weather": "天气",
}
DEFAULT_CONFIG = {"show_time": True, "show_timezone": True, "show_date": False, "show_temp": True, "show_weather": True, "location": "Los Angeles", "use_bold": True, "name_order": DEFAULT_NAME_ORDER.copy(), "bio_enabled": False, "birth_date": "", "fixed_bio": ""}
BOOL_CONFIG_KEYS = ("show_time", "show_timezone", "show_date", "show_temp", "show_weather", "use_bold", "bio_enabled")
MAX_LOCATION_LENGTH = 80
MAX_BIO_LENGTH = 70
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

    location = raw_config.get("location")
    if isinstance(location, str) and location.strip():
        config["location"] = location.strip()[:MAX_LOCATION_LENGTH]

    config["name_order"] = normalize_name_order(raw_config.get("name_order"))
    birth_date = parse_birth_date(raw_config.get("birth_date"))
    if birth_date:
        config["birth_date"] = birth_date.isoformat()

    fixed_bio = raw_config.get("fixed_bio")
    if isinstance(fixed_bio, str):
        config["fixed_bio"] = "".join(char for char in fixed_bio.strip() if char.isprintable())[:MAX_BIO_LENGTH]

    if not config["birth_date"] or not config["fixed_bio"]:
        config["bio_enabled"] = False
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
    menu_line("8", "粗体显示", state_text(config['use_bold']), "magenta")
    menu_line("9", "设置地区", f"当前: {safe_display(config['location'])}", "magenta")
    menu_line("10", "输出顺序", format_name_order(config["name_order"]), "magenta")
    menu_line("11", "一键开启全部", "时间 / 时区 / 日期 / 温度 / 天气 / 粗体", "magenta")

    menu_section("Bio 功能")
    menu_line("12", "Bio 自动更新", state_text(config['bio_enabled']), "blue")

    menu_section("维护工具")
    menu_line("13", "重启后台服务", "立即重载配置", "green")
    menu_line("14", "检查并更新", "从 GitHub 拉取核心脚本", "green")
    menu_line("15", "同步服务器时区", "改名显示将使用 UTC 偏移", "green")

    print()
    menu_line("99", "一键卸载脚本", "停止服务并删除程序与配置", "red")
    menu_line("0", "退出管理面板", "", "red")
    print(color("─"*56, "cyan"))

def run_command(command, **kwargs):
    try:
        return subprocess.run(command, check=False, **kwargs).returncode
    except FileNotFoundError:
        print(f"命令不存在: {command[0]}")
        return 127

def chown_runtime_files():
    if run_command(["id", "-u", SERVICE_USER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.islink(DATA_DIR):
        run_command(["sudo", "chown", f"{SERVICE_USER}:{SERVICE_USER}", DATA_DIR])
        run_command(["sudo", "chmod", "700", DATA_DIR])
    for path in (CONFIG_FILE, SESSION_FILE, SESSION_JOURNAL_FILE, API_CONFIG_FILE, BIO_STATE_FILE):
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
        return

    run_command(["sudo", "chown", "-R", "root:root", BASE_DIR])
    run_command(["sudo", "chmod", "755", BASE_DIR])
    for filename in ("tg_panel.py", "tg_daemon.py"):
        path = os.path.join(BASE_DIR, filename)
        if os.path.exists(path):
            run_command(["sudo", "chmod", "755", path])

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
            content = response.read().decode('utf-8')
            match = re.search(r'CURRENT_VERSION\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)
    except Exception:
        pass 
    return None

def parse_version(version):
    if not version:
        return None
    numbers = re.findall(r'\d+', version)
    if not numbers:
        return None
    return tuple(int(number) for number in numbers)

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
    except OSError:
        return None

    match = re.search(r'CURRENT_VERSION\s*=\s*"([^"]+)"', content)
    return match.group(1) if match else None

def load_config():
    loaded = {}
    if not os.path.exists(CONFIG_FILE):
        return sanitize_config(loaded)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️ 配置文件读取失败，已使用默认配置: {e}")
    return sanitize_config(loaded)

def write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".config.", suffix=".tmp", dir=os.path.dirname(path), text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

def save_config(config):
    write_json_atomic(CONFIG_FILE, config)
    chown_runtime_files()
    restart_code = run_command(["sudo", "systemctl", "restart", "tg_name.service"])
    if restart_code == 0:
        print("\n✅ 配置已保存，后台服务已自动重启！")
    else:
        print("\n⚠️ 配置已保存，但后台服务重启失败，请使用 [2] 查看日志。")

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
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
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

def validate_python_file(path):
    return run_command([
        sys.executable,
        "-c",
        "import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'), filename=sys.argv[1])",
        path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

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
            return False
        backups.append((target_path, backup_path))

    for tmp_path, target_path in file_pairs:
        if replace_remote_file(tmp_path, target_path) != 0:
            for restored_target, backup_path in replaced:
                run_command(["sudo", "cp", "-p", backup_path, restored_target])
            cleanup_temp_files(*(backup for _, backup in backups), *(tmp for tmp, _ in file_pairs))
            return False
        replaced.append((target_path, dict(backups)[target_path]))

    cleanup_temp_files(*(backup for _, backup in backups))
    return True

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

    print("\n正在停止并禁用服务...")
    run_command(["sudo", "systemctl", "stop", "tg_name.service"])
    run_command(["sudo", "systemctl", "disable", "tg_name.service"])
    run_command(["sudo", "rm", "-f", "/etc/systemd/system/tg_name.service"])
    run_command(["sudo", "systemctl", "daemon-reload"])

    print("正在删除快捷命令...")
    run_command(["sudo", "rm", "-f", "/usr/local/bin/tg", "/usr/local/bin/tg_py"])

    print("正在删除程序和运行数据...")
    run_command(["sudo", "rm", "-rf", project_dir])
    run_command(["sudo", "rm", "-rf", data_dir])

    print("\n✅ 卸载完成。")
    sys.exit(0)

def configure_name_order(config):
    item_keys = DEFAULT_NAME_ORDER
    print("\n当前输出顺序:")
    print(f"  {format_name_order(config['name_order'])}")
    print("\n可选字段:")
    for index, key in enumerate(item_keys, 1):
        print(f"  {index}. {ORDER_LABELS[key]}")
    print("\n请输入新的顺序，例如 1,2,3,4,5 或 3,1,2,4,5")
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
    save_config(config)
    input(f"✅ 输出顺序已更新为: {format_name_order(config['name_order'])}，按回车键返回主菜单...")

def configure_bio(config):
    if config.get("bio_enabled"):
        config["bio_enabled"] = False
        save_config(config)
        input("✅ Bio 自动更新已关闭，按回车键返回主菜单...")
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
    try:
        os.unlink(BIO_STATE_FILE)
    except FileNotFoundError:
        pass
    save_config(config)
    print(f"\nBio 预览: {preview}")
    input("✅ Bio 自动更新已开启，按回车键返回主菜单...")

def main_menu():
    migrate_legacy_runtime_files()
    while True:
        clear_screen()
        config = load_config()
        render_menu(config)
        
        choice = input(color("请输入选项 (0-15, 99): ", "cyan", "bold")).strip()
        
        if choice == '0':
            print("退出面板。")
            sys.exit()
            
        elif choice == '99':
            uninstall_script()
            
        elif choice == '1':
            harden_code_files()
            print("正在停止后台服务...")
            run_command(["sudo", "systemctl", "stop", "tg_name.service"])
            for path in (SESSION_FILE, SESSION_JOURNAL_FILE):
                if os.path.exists(path):
                    os.remove(path)
            print("旧凭证已删除，请按提示重新登录：")
            venv_python = os.path.join(os.path.dirname(__file__), 'venv', 'bin', 'python3')
            if not os.path.exists(venv_python):
                venv_python = sys.executable
            login_result = run_command([venv_python, os.path.join(os.path.dirname(__file__), 'tg_daemon.py'), '--login'])
            if login_result == 0:
                chown_runtime_files()
                print("\n正在重启后台服务...")
                run_command(["sudo", "systemctl", "restart", "tg_name.service"])
                input("✅ 配置已生效，按回车键返回主菜单...")
            else:
                input("❌ 登录失败，后台服务未重启。按回车键返回主菜单...")
            
        elif choice == '2':
            print("\n--- 最近 50 条系统运行日志 ---\n")
            run_command(["sudo", "journalctl", "-u", "tg_name.service", "-n", "50", "--no-pager"])
            print("\n------------------------------\n")
            input("按回车键返回主菜单...")
            
        elif choice == '3':
            config['show_time'] = not config['show_time']
            save_config(config)
            
        elif choice == '4':
            config['show_timezone'] = not config['show_timezone']
            save_config(config)
            
        elif choice == '5':
            config['show_date'] = not config['show_date']
            save_config(config)
            
        elif choice == '6':
            config['show_temp'] = not config['show_temp']
            save_config(config)
            
        elif choice == '7':
            config['show_weather'] = not config['show_weather']
            save_config(config)
            
        elif choice == '8':
            config['use_bold'] = not config['use_bold']
            save_config(config)
            
        elif choice == '9':
            new_loc = input("请输入新的城市名称 (拼音或英文): ").strip()
            if new_loc:
                if len(new_loc) > MAX_LOCATION_LENGTH:
                    input(f"❌ 地区名称过长，请限制在 {MAX_LOCATION_LENGTH} 个字符内。按回车键返回主菜单...")
                    continue
                config['location'] = new_loc
                save_config(config)
                
        elif choice == '10':
            configure_name_order(config)
                
        elif choice == '11':
            config.update({"show_time": True, "show_timezone": True, "show_date": True, "show_temp": True, "show_weather": True, "use_bold": True})
            save_config(config)
            
        elif choice == '12':
            configure_bio(config)

        elif choice == '13':
            print("\n正在强制重启后台服务...")
            run_command(["sudo", "systemctl", "restart", "tg_name.service"])
            print("✅ 服务已重启，将立即触发一次强制更新！")
            input("按回车键返回主菜单...")
            
        elif choice == '14':
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
            res1, daemon_tmp = download_remote_file("tg_daemon.py", daemon_target)
            res2, panel_tmp = download_remote_file("tg_panel.py", panel_target)
            
            if res1 == 0 and res2 == 0:
                if not validate_python_file(daemon_tmp) or not validate_python_file(panel_tmp):
                    cleanup_temp_files(daemon_tmp, panel_tmp)
                    print("\n❌ 更新失败！下载文件未通过 Python 语法校验，已取消覆盖。")
                    input("按回车键返回主菜单...")
                    continue

                downloaded_version = extract_version_from_file(panel_tmp)
                if downloaded_version is None:
                    cleanup_temp_files(daemon_tmp, panel_tmp)
                    print("\n❌ 更新失败！下载到的面板脚本缺少 CURRENT_VERSION，已取消覆盖。")
                    input("按回车键返回主菜单...")
                    continue
                downloaded_compare = compare_versions(downloaded_version, CURRENT_VERSION)
                if downloaded_compare is not None and downloaded_compare < 0:
                    cleanup_temp_files(daemon_tmp, panel_tmp)
                    print(f"\n❌ 已取消更新：下载到的版本是 {downloaded_version}，低于当前版本 {CURRENT_VERSION}。")
                    print("请确认 GitHub main 分支已经推送最新代码，或等待 raw.githubusercontent.com 缓存刷新。")
                    input("按回车键返回主菜单...")
                    continue
                if downloaded_compare == 0:
                    print(f">> 下载文件版本与本地相同 ({CURRENT_VERSION})，继续覆盖以同步文件内容。")
                elif downloaded_version:
                    print(f">> 下载文件版本确认: {downloaded_version}")

                if replace_remote_files(((daemon_tmp, daemon_target), (panel_tmp, panel_target))):
                    run_command(["sudo", "chmod", "+x", panel_target])
                    run_command(["sudo", "chmod", "+x", daemon_target])
                    run_command(["sudo", "chown", "root:root", daemon_target])
                    run_command(["sudo", "chown", "root:root", panel_target])
                    harden_code_files()
                    print(">> 正在重启后台服务...")
                    run_command(["sudo", "systemctl", "restart", "tg_name.service"])
                    print("\n✅ 更新成功！核心代码与后台服务均已同步至 GitHub 最新版本。")
                    print("⚠️ 提示：由于当前管理面板已载入内存，建议您输入 [0] 退出面板并重新敲击 'tg' 载入新版本界面。")
                else:
                    cleanup_temp_files(daemon_tmp, panel_tmp)
                    print("\n❌ 更新失败！文件替换失败，已尝试恢复旧版本，请检查 /opt/tg_updater 权限。")
            else:
                cleanup_temp_files(daemon_tmp, panel_tmp)
                print("\n❌ 更新失败！请检查 VPS 网络连接或 GitHub 仓库地址是否正确。")
            input("按回车键返回主菜单...")
            
        elif choice == '15':
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
            if target_tz:
                print(f"\n>> 识别到设定城市 [{config['location']}]，正在修改 VPS 系统时区为: {target_tz}...")
                run_command(["sudo", "timedatectl", "set-timezone", target_tz])
                print("✅ 时区同步成功！改名显示将按当前服务器时区显示 UTC 偏移。")
            else:
                print(f"\n❌ 无法自动匹配城市 [{config['location']}] 的标准时区。")
                print("您可以手动输入 IANA 标准时区格式（例如: Asia/Shanghai, America/New_York）")
                manual_tz = input("请输入标准时区 (直接回车取消): ").strip()
                if manual_tz:
                    res = run_command(["sudo", "timedatectl", "set-timezone", manual_tz], stderr=subprocess.DEVNULL)
                    if res == 0:
                        print(f"✅ 时区已手动设置为: {manual_tz}！改名显示将按当前服务器时区显示 UTC 偏移。")
                    else:
                        print("❌ 设置失败，请检查时区名称是否拼写正确。")
            
            print("\n正在重启后台服务刷新显示时间...")
            run_command(["sudo", "systemctl", "restart", "tg_name.service"])
            input("按回车键返回主菜单...")
if __name__ == "__main__":
    main_menu()
