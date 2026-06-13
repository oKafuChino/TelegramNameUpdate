#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import os
import sys
import logging
import asyncio
import json
import urllib.request
from time import strftime
from telethon import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest

BASE_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
api_auth_file = os.path.join(BASE_DIR, 'api_auth')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOLD_MAP = str.maketrans("0123456789", "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵")
current_weather_data = {"temp": "", "emoji": ""}

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"show_time": True, "show_date": False, "show_temp": True, "show_weather": True, "location": "Los Angeles", "use_bold": True}

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
            time_cur = strftime("%m-%d:%H:%M:%S", time.localtime())
            month_day, hour, minu, seco = time_cur.split(':')
            
            if seco == '00':
                config = load_config()
                parts = []
                
                if config['show_date']: parts.append(month_day)
                if config['show_time']: parts.append(f"{hour}:{minu}")
                if config['show_temp'] and current_weather_data['temp']: parts.append(current_weather_data['temp'])
                if config['show_weather'] and current_weather_data['emoji']: parts.append(current_weather_data['emoji'])
                
                raw_name = " ".join(parts)
                last_name = raw_name.translate(BOLD_MAP) if config['use_bold'] else raw_name
                
                await client(UpdateProfileRequest(last_name=last_name))
                logger.info(f'Updated -> {last_name}')
                
        except Exception as e:
            logger.error(f"Error: {e}")
        await asyncio.sleep(1)

# ==========================================
# 【主入口】
# ==========================================
async def main():
    if not os.path.exists(api_auth_file+'.session'):
        api_id = input('请输入 api_id: ')
        api_hash = input('请输入 api_hash: ')
    else:
        api_id, api_hash = 123456, '00000000000000000000000000000000'
        
    client = TelegramClient(api_auth_file, api_id, api_hash)
    await client.start()
    
    # 如果仅为登录模式，则启动后直接退出
    if len(sys.argv) > 1 and sys.argv[1] == '--login':
        print("✅ 登录成功！凭证已生成。")
        return

    loop = asyncio.get_event_loop()
    task_name = loop.create_task(change_name_auto(client))
    task_weather = loop.create_task(update_weather_loop(loop))
    
    await asyncio.gather(task_name, task_weather)
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())