#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import os
import sys
import logging
import asyncio
import json
import urllib.request
from telethon import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest

BASE_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
API_CONFIG_FILE = os.path.join(BASE_DIR, 'api_auth.json')
api_auth_file = os.path.join(BASE_DIR, 'api_auth')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOLD_MAP = str.maketrans("0123456789", "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵")
current_weather_data = {"temp": "", "emoji": ""}
DEFAULT_CONFIG = {"show_time": True, "show_timezone": True, "show_date": False, "show_temp": True, "show_weather": True, "location": "Los Angeles", "use_bold": True}

def load_config():
    config = DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config.update(json.load(f))
    except Exception:
        pass
    return config

def load_api_credentials(allow_prompt=False):
    env_api_id = os.environ.get("TELEGRAM_API_ID")
    env_api_hash = os.environ.get("TELEGRAM_API_HASH")
    if env_api_id and env_api_hash:
        return int(env_api_id), env_api_hash

    try:
        with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return int(data["api_id"]), data["api_hash"]
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        pass

    if not allow_prompt:
        raise RuntimeError("缺少 Telegram API 凭证，请先运行 `tg` 并使用选项 [1] 初始化账号。")

    api_id = int(input('请输入 api_id: ').strip())
    api_hash = input('请输入 api_hash: ').strip()
    with open(API_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({"api_id": api_id, "api_hash": api_hash}, f, indent=2)
    try:
        os.chmod(API_CONFIG_FILE, 0o600)
    except OSError:
        pass
    return api_id, api_hash

# ==========================================
# 【天气模块】
# ==========================================
def fetch_weather_sync(city_name):
    url = f"https://wttr.in/{city_name.replace(' ', '+')}?format=j1"
    req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            condition = data['current_condition'][0]['weatherDesc'][0]['value'].lower()
            current_temp = data['current_condition'][0]['temp_C']
            
            emoji = "☁️" 
            if "sun" in condition or "clear" in condition: emoji = "☀️"
            elif "partly cloudy" in condition: emoji = "⛅"
            elif "rain" in condition or "shower" in condition or "drizzle" in condition: emoji = "🌧️"
            elif "snow" in condition: emoji = "❄️"
            elif "thunder" in condition or "storm" in condition: emoji = "⛈️"
            elif "fog" in condition or "mist" in condition: emoji = "🌫️"
            
            return {"temp": f"{current_temp}°C", "emoji": emoji}
    except Exception as e:
        return {"temp": "", "emoji": ""}

async def update_weather_loop(loop):
    global current_weather_data
    while True:
        config = load_config()
        if config['show_temp'] or config['show_weather']:
            result = await loop.run_in_executor(None, fetch_weather_sync, config['location'])
            if result['temp']: current_weather_data = result
        await asyncio.sleep(3600)

# ==========================================
# 【核心拼接模块】
# ==========================================
async def change_name_auto(client):
    while True:
        try:
            now = time.localtime()
            month_day = time.strftime("%m-%d", now)
            hour_minute = time.strftime("%H:%M", now)
            timezone_name = time.strftime("%Z", now)
            config = load_config()
            parts = []
            
            if config['show_time']: parts.append(hour_minute)
            if config['show_timezone'] and timezone_name: parts.append(timezone_name)
            if config['show_date']: parts.append(month_day)
            if config['show_temp'] and current_weather_data['temp']: parts.append(current_weather_data['temp'])
            if config['show_weather'] and current_weather_data['emoji']: parts.append(current_weather_data['emoji'])
            
            raw_name = " ".join(parts)
            last_name = raw_name.translate(BOLD_MAP) if config['use_bold'] else raw_name
            
            await client(UpdateProfileRequest(last_name=last_name))
            logger.info(f'Updated -> {last_name}')
                
        except Exception as e:
            logger.error(f"Error: {e}")
        await asyncio.sleep(60 - (time.time() % 60))

# ==========================================
# 【主入口】
# ==========================================
async def main():
    login_only = len(sys.argv) > 1 and sys.argv[1] == '--login'
    session_exists = os.path.exists(api_auth_file+'.session')
    if not login_only and not session_exists and not sys.stdin.isatty():
        raise RuntimeError("缺少 Telegram 登录 Session，请先运行 `tg` 并使用选项 [1] 初始化账号。")

    api_id, api_hash = load_api_credentials(allow_prompt=sys.stdin.isatty())
        
    client = TelegramClient(api_auth_file, api_id, api_hash)
    await client.start()
    
    # 如果仅为登录模式，则启动后直接退出
    if login_only:
        print("✅ 登录成功！凭证已生成。")
        await client.disconnect()
        return

    loop = asyncio.get_running_loop()
    task_name = asyncio.create_task(change_name_auto(client))
    task_weather = asyncio.create_task(update_weather_loop(loop))
    
    try:
        await client.run_until_disconnected()
    finally:
        task_name.cancel()
        task_weather.cancel()
        await asyncio.gather(task_name, task_weather, return_exceptions=True)

if __name__ == '__main__':
    asyncio.run(main())
