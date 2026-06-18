#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import urllib.request
import re

# ==========================================
# 【版本定义】
# 每次修改代码推送到 GitHub 前，请手动提升此版本号
# ==========================================
CURRENT_VERSION = "v1.1.0"

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
SESSION_FILE = os.path.join(os.path.dirname(__file__), 'api_auth.session')
REPO_URL = "https://raw.githubusercontent.com/oKafuChino/TelegramNameUpdate/main"

def check_for_updates():
    """静默检查 GitHub 上的最新版本"""
    try:
        req = urllib.request.Request(f"{REPO_URL}/tg_panel.py", headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=1.5) as response:
            content = response.read().decode('utf-8')
            match = re.search(r'CURRENT_VERSION\s*=\s*"([^"]+)"', content)
            if match:
                remote_version = match.group(1)
                if remote_version != CURRENT_VERSION:
                    return f" | 🚀 发现新版本 {remote_version}，请按 [11] 更新"
    except Exception:
        pass 
    return ""

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"show_time": True, "show_date": False, "show_temp": True, "show_weather": True, "location": "Los Angeles", "use_bold": True}
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    os.system("sudo systemctl restart tg_name.service")
    print("\n✅ 配置已保存，后台服务已自动重启！")

def clear_screen():
    os.system('clear')

def main_menu():
    while True:
        clear_screen()
        update_msg = check_for_updates()
        config = load_config()
        
        print("="*48)
        print("      ✨ Telegram 名字动态更新面板 ✨")
        print(f"      当前版本: {CURRENT_VERSION}{update_msg}")
        print("="*48)
        print(f" [1]  更新账号 Session (重新登录)")
        print(f" [2]  查看运行日志")
        print(f" [3]  显示时间: {'✅ 开启' if config['show_time'] else '❌ 关闭'}")
        print(f" [4]  显示日期: {'✅ 开启' if config['show_date'] else '❌ 关闭'}")
        print(f" [5]  显示温度: {'✅ 开启' if config['show_temp'] else '❌ 关闭'}")
        print(f" [6]  显示天气: {'✅ 开启' if config['show_weather'] else '❌ 关闭'}")
        print(f" [7]  设置地区: 当前 [{config['location']}]")
        print(f" [8]  粗体显示: {'✅ 开启' if config['use_bold'] else '❌ 关闭'}")
        print(f" [9]  🚀 一键开启所有展示项目")
        print(f" [10] 🔄 强制重启后台服务")
        print(f" [11] ⬇️ 从 GitHub 检查并自动更新脚本")
        print(f" [12] 🌍 同步服务器时区至设定城市")
        print(f" [0]  退出管理面板")
        print("="*48)
        
        choice = input("请输入选项 (0-12): ").strip()
        
        if choice == '0':
            print("退出面板。")
            sys.exit()
            
        elif choice == '1':
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
            print("旧凭证已删除，请按提示重新登录：")
            venv_python = os.path.join(os.path.dirname(__file__), 'venv', 'bin', 'python3')
            os.system(f"{venv_python} {os.path.join(os.path.dirname(__file__), 'tg_daemon.py')} --login")
            print("\n正在重启后台服务...")
            os.system("sudo systemctl restart tg_name.service")
            input("✅ 配置已生效，按回车键返回主菜单...")
            
        elif choice == '2':
            print("\n--- 最近 50 条系统运行日志 ---\n")
            os.system("sudo journalctl -u tg_name.service -n 50 --no-pager")
            print("\n------------------------------\n")
            input("按回车键返回主菜单...")
            
        elif choice == '3':
            config['show_time'] = not config['show_time']
            save_config(config)
            
        elif choice == '4':
            config['show_date'] = not config['show_date']
            save_config(config)
            
        elif choice == '5':
            config['show_temp'] = not config['show_temp']
            save_config(config)
            
        elif choice == '6':
            config['show_weather'] = not config['show_weather']
            save_config(config)
            
        elif choice == '7':
            new_loc = input("请输入新的城市名称 (拼音或英文): ").strip()
            if new_loc:
                config['location'] = new_loc
                save_config(config)
                
        elif choice == '8':
            config['use_bold'] = not config['use_bold']
            save_config(config)
            
        elif choice == '9':
            config.update({"show_time": True, "show_date": True, "show_temp": True, "show_weather": True, "use_bold": True})
            save_config(config)
            
        elif choice == '10':
            print("\n正在强制重启后台服务...")
            os.system("sudo systemctl restart tg_name.service")
            print("✅ 服务已重启，将立即触发一次强制更新！")
            input("按回车键返回主菜单...")
            
        elif choice == '11':
            print("\n>> 正在从 GitHub 检查并拉取最新版本代码...")
            res1 = os.system(f"sudo curl -sL '{REPO_URL}/tg_daemon.py' -o /opt/tg_updater/tg_daemon.py")
            res2 = os.system(f"sudo curl -sL '{REPO_URL}/tg_panel.py' -o /opt/tg_updater/tg_panel.py")
            
            if res1 == 0 and res2 == 0:
                os.system("sudo chmod +x /opt/tg_updater/tg_panel.py")
                os.system("sudo chmod +x /opt/tg_updater/tg_daemon.py")
                print(">> 正在重启后台服务...")
                os.system("sudo systemctl restart tg_name.service")
                print("\n✅ 更新成功！核心代码与后台服务均已同步至 GitHub 最新版本。")
                print("⚠️ 提示：由于当前管理面板已载入内存，建议您输入 [0] 退出面板并重新敲击 'tg' 载入新版本界面。")
            else:
                print("\n❌ 更新失败！请检查 VPS 网络连接或 GitHub 仓库地址是否正确。")
            input("按回车键返回主菜单...")
            
        elif choice == '12':
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
                os.system(f"sudo timedatectl set-timezone {target_tz}")
                print("✅ 时区同步成功！")
            else:
                print(f"\n❌ 无法自动匹配城市 [{config['location']}] 的标准时区。")
                print("您可以手动输入 IANA 标准时区格式（例如: Asia/Shanghai, America/New_York）")
                manual_tz = input("请输入标准时区 (直接回车取消): ").strip()
                if manual_tz:
                    res = os.system(f"sudo timedatectl set-timezone {manual_tz} 2>/dev/null")
                    if res == 0:
                        print(f"✅ 时区已手动设置为: {manual_tz}！")
                    else:
                        print("❌ 设置失败，请检查时区名称是否拼写正确。")
            
            print("\n正在重启后台服务刷新显示时间...")
            os.system("sudo systemctl restart tg_name.service")
            input("按回车键返回主菜单...")

if __name__ == "__main__":
    main_menu()