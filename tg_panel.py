#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
SESSION_FILE = os.path.join(os.path.dirname(__file__), 'api_auth.session')

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"show_time": True, "show_date": False, "show_temp": True, "show_weather": True, "location": "Los Angeles", "use_bold": True}
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    # 修改配置后自动重启后台服务
    os.system("sudo systemctl restart tg_name.service")
    print("\n✅ 配置已保存，后台服务已重启！")

def clear_screen():
    os.system('clear')

def main_menu():
    while True:
        clear_screen()
        config = load_config()
        print("="*45)
        print(" ✨ Telegram 名字动态更新面板 ✨")
        print("="*45)
        print(f" [1] 更新账号 Session (重新登录)")
        print(f" [2] 查看运行日志")
        print(f" [3] 显示时间: {'✅ 开启' if config['show_time'] else '❌ 关闭'}")
        print(f" [4] 显示日期: {'✅ 开启' if config['show_date'] else '❌ 关闭'}")
        print(f" [5] 显示温度: {'✅ 开启' if config['show_temp'] else '❌ 关闭'}")
        print(f" [6] 显示天气: {'✅ 开启' if config['show_weather'] else '❌ 关闭'}")
        print(f" [7] 设置地区: 当前 [{config['location']}]")
        print(f" [8] 粗体显示: {'✅ 开启' if config['use_bold'] else '❌ 关闭'}")
        print(f" [9] 🚀 一键开启所有展示项目")
        print(f" [0] 退出管理面板")
        print("="*45)
        
        choice = input("请输入选项 (0-9): ").strip()
        
        if choice == '0':
            print("退出面板。")
            sys.exit()
        elif choice == '1':
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
            print("旧凭证已删除，请按提示重新登录：")
            # 调用后台核心脚本进行交互式登录
            os.system(f"{sys.executable} {os.path.join(os.path.dirname(__file__), 'tg_daemon.py')} --login")
            input("按回车键返回主菜单...")
        elif choice == '2':
            os.system("sudo journalctl -u tg_name.service -f -n 50")
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
            
if __name__ == "__main__":
    main_menu()