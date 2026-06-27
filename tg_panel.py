#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import urllib.request
import re
import subprocess
import time

# ==========================================
# 【版本定义】
# 每次修改代码推送到 GitHub 前，请手动提升此版本号
# ==========================================
CURRENT_VERSION = "v1.3.1"

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
SESSION_FILE = os.path.join(os.path.dirname(__file__), 'api_auth.session')
SESSION_JOURNAL_FILE = os.path.join(os.path.dirname(__file__), 'api_auth.session-journal')
API_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'api_auth.json')
REPO_URL = "https://raw.githubusercontent.com/oKafuChino/TelegramNameUpdate/main"
SERVICE_USER = "tg_updater"
DEFAULT_CONFIG = {"show_time": True, "show_timezone": True, "show_date": False, "show_temp": True, "show_weather": True, "location": "Los Angeles", "use_bold": True}
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

def state_text(enabled):
    if enabled:
        return color("● 开启", "green", "bold")
    return color("○ 关闭", "red")

def menu_line(key, label, detail="", accent="cyan"):
    key_text = color(f"[{key}]", accent, "bold")
    if detail:
        print(f"  {key_text} {label:<18} {color(detail, 'dim')}")
    else:
        print(f"  {key_text} {label}")

def menu_section(title):
    print()
    print(color(f"  {title}", "yellow", "bold"))

def box_row(text, highlight="", text_styles=()):
    width = 54
    plain_text = text + highlight
    display_text = (color(text, *text_styles) if text_styles else text) + (color(highlight, "green", "bold") if highlight else "")
    padding = " " * max(0, width - len(plain_text))
    print(color("│", "cyan") + display_text + padding + color("│", "cyan"))

def render_menu(config):
    print(color("╭" + "─"*54 + "╮", "cyan"))
    box_row("        Telegram 名字动态更新面板", text_styles=("bold", "white"))
    box_row("        当前版本: ", CURRENT_VERSION)
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
    menu_line("9", "设置地区", f"当前: {config['location']}", "magenta")
    menu_line("10", "一键开启全部", "时间 / 时区 / 日期 / 温度 / 天气 / 粗体", "magenta")

    menu_section("维护工具")
    menu_line("11", "重启后台服务", "立即重载配置", "green")
    menu_line("12", "检查并更新", "从 GitHub 拉取核心脚本", "green")
    menu_line("13", "同步服务器时区", "按当前城市匹配 IANA 时区", "green")

    print()
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
    for path in (CONFIG_FILE, SESSION_FILE, SESSION_JOURNAL_FILE, API_CONFIG_FILE):
        if os.path.exists(path):
            run_command(["sudo", "chown", f"{SERVICE_USER}:{SERVICE_USER}", path])

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

def load_config():
    config = DEFAULT_CONFIG.copy()
    if not os.path.exists(CONFIG_FILE):
        return config
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config.update(json.load(f))
        return config

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    chown_runtime_files()
    run_command(["sudo", "systemctl", "restart", "tg_name.service"])
    print("\n✅ 配置已保存，后台服务已自动重启！")

def clear_screen():
    run_command(["clear"])

def download_remote_file(filename, target):
    return run_command([
        "sudo", "curl", "-fsSL",
        "-H", "Cache-Control: no-cache",
        "-H", "Pragma: no-cache",
        remote_file_url(filename),
        "-o", target
    ])

def main_menu():
    while True:
        clear_screen()
        config = load_config()
        render_menu(config)
        
        choice = input(color("请输入选项 (0-13): ", "cyan", "bold")).strip()
        
        if choice == '0':
            print("退出面板。")
            sys.exit()
            
        elif choice == '1':
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
                config['location'] = new_loc
                save_config(config)
                
        elif choice == '10':
            config.update({"show_time": True, "show_timezone": True, "show_date": True, "show_temp": True, "show_weather": True, "use_bold": True})
            save_config(config)
            
        elif choice == '11':
            print("\n正在强制重启后台服务...")
            run_command(["sudo", "systemctl", "restart", "tg_name.service"])
            print("✅ 服务已重启，将立即触发一次强制更新！")
            input("按回车键返回主菜单...")
            
        elif choice == '12':
            print("\n>> 正在从 GitHub 检查最新版本...")
            remote_version = get_remote_version()
            if remote_version == CURRENT_VERSION:
                print(f">> 远程版本号与本地相同 ({CURRENT_VERSION})，仍将重新拉取核心脚本以避免缓存或本地文件不一致。")
            elif remote_version:
                print(f">> 发现新版本 {remote_version}，正在拉取最新代码...")
            else:
                print(">> 无法获取远程版本号，仍尝试拉取最新代码...")
            res1 = download_remote_file("tg_daemon.py", "/opt/tg_updater/tg_daemon.py")
            res2 = download_remote_file("tg_panel.py", "/opt/tg_updater/tg_panel.py")
            
            if res1 == 0 and res2 == 0:
                run_command(["sudo", "chmod", "+x", "/opt/tg_updater/tg_panel.py"])
                run_command(["sudo", "chmod", "+x", "/opt/tg_updater/tg_daemon.py"])
                run_command(["sudo", "chown", f"{SERVICE_USER}:{SERVICE_USER}", "/opt/tg_updater/tg_daemon.py"])
                run_command(["sudo", "chown", f"{SERVICE_USER}:{SERVICE_USER}", "/opt/tg_updater/tg_panel.py"])
                print(">> 正在重启后台服务...")
                run_command(["sudo", "systemctl", "restart", "tg_name.service"])
                print("\n✅ 更新成功！核心代码与后台服务均已同步至 GitHub 最新版本。")
                print("⚠️ 提示：由于当前管理面板已载入内存，建议您输入 [0] 退出面板并重新敲击 'tg' 载入新版本界面。")
            else:
                print("\n❌ 更新失败！请检查 VPS 网络连接或 GitHub 仓库地址是否正确。")
            input("按回车键返回主菜单...")
            
        elif choice == '13':
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
                print("✅ 时区同步成功！")
            else:
                print(f"\n❌ 无法自动匹配城市 [{config['location']}] 的标准时区。")
                print("您可以手动输入 IANA 标准时区格式（例如: Asia/Shanghai, America/New_York）")
                manual_tz = input("请输入标准时区 (直接回车取消): ").strip()
                if manual_tz:
                    res = run_command(["sudo", "timedatectl", "set-timezone", manual_tz], stderr=subprocess.DEVNULL)
                    if res == 0:
                        print(f"✅ 时区已手动设置为: {manual_tz}！")
                    else:
                        print("❌ 设置失败，请检查时区名称是否拼写正确。")
            
            print("\n正在重启后台服务刷新显示时间...")
            run_command(["sudo", "systemctl", "restart", "tg_name.service"])
            input("按回车键返回主菜单...")

if __name__ == "__main__":
    main_menu()
