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
CURRENT_VERSION = "v1.0.0"

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
SESSION_FILE = os.path.join(os.path.dirname(__file__), 'api_auth.session')
REPO_URL = "https://raw.githubusercontent.com/oKafuChino/TelegramNameUpdate/main"

def check_for_updates():
    """静默检查 GitHub 上的最新版本"""
    try:
        req = urllib.request.Request(f"{REPO_URL}/tg_panel.py", headers={'Cache-Control': 'no-cache'})
        # 设置 1.5 秒超时，防止网络不好时导致面板卡顿
        with urllib.request.urlopen(req, timeout=1.5) as response:
            content = response.read().decode('utf-8')
            match = re.search(r'CURRENT_VERSION\s*=\s*"([^"]+)"', content)
            if match:
                remote_version = match.group(1)
                if remote_version != CURRENT_VERSION:
                    return f" | 🚀 发现新版本 {remote_version}，请按 [11] 更新"
    except Exception:
        pass # 如果网络异常直接跳过，不打扰用户
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
        # 渲染面板前先检查更新（会稍微等待约1秒钟）
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
        print(f" [0]  退出管理面板")
        print("="*48)
        
        choice = input("请输入选项 (0-11): ").strip()
        
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
            # 使用 curl 下载覆盖核心运行脚本
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
            
if __name__ == "__main__":
    main_menu()