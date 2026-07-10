#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import os
import sys
import logging
import asyncio
import json
import urllib.request
import urllib.parse
import calendar
from datetime import date
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.account import UpdateProfileRequest

BASE_DIR = os.path.dirname(__file__)
DEFAULT_DATA_DIR = "/var/lib/tg_updater" if os.path.abspath(BASE_DIR) == "/opt/tg_updater" else BASE_DIR
DATA_DIR = os.environ.get("TG_UPDATER_DATA_DIR", DEFAULT_DATA_DIR)
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
API_CONFIG_FILE = os.path.join(DATA_DIR, 'api_auth.json')
BIO_STATE_FILE = os.path.join(DATA_DIR, 'bio_last_update.txt')
api_auth_file = os.path.join(DATA_DIR, 'api_auth')
LEGACY_CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
LEGACY_API_CONFIG_FILE = os.path.join(BASE_DIR, 'api_auth.json')
LEGACY_SESSION_FILE = os.path.join(BASE_DIR, 'api_auth.session')
LEGACY_SESSION_JOURNAL_FILE = os.path.join(BASE_DIR, 'api_auth.session-journal')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOLD_MAP = str.maketrans("0123456789", "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵")
current_weather_data = {"temp": "", "emoji": ""}
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

def load_config():
    loaded = {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
    except Exception:
        pass
    return sanitize_config(loaded)

def migrate_legacy_runtime_files():
    if DATA_DIR == BASE_DIR:
        return

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        return

    pairs = (
        (LEGACY_CONFIG_FILE, CONFIG_FILE),
        (LEGACY_API_CONFIG_FILE, API_CONFIG_FILE),
        (LEGACY_SESSION_FILE, api_auth_file + '.session'),
        (LEGACY_SESSION_JOURNAL_FILE, api_auth_file + '.session-journal'),
    )
    for source, target in pairs:
        try:
            if os.path.exists(source) and not os.path.exists(target) and not os.path.islink(source):
                os.replace(source, target)
        except OSError:
            pass

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

def load_api_credentials(allow_prompt=False):
    env_api_id = os.environ.get("TELEGRAM_API_ID")
    env_api_hash = os.environ.get("TELEGRAM_API_HASH")
    if env_api_id and env_api_hash:
        try:
            return int(env_api_id), env_api_hash
        except ValueError as exc:
            raise RuntimeError("环境变量 TELEGRAM_API_ID 必须是数字。") from exc

    try:
        with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return int(data["api_id"]), data["api_hash"]
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        pass

    if not allow_prompt:
        raise RuntimeError("缺少 Telegram API 凭证，请先运行 `tg` 并使用选项 [1] 初始化账号。")

    raw_api_id = input('请输入 api_id: ').strip()
    api_hash = input('请输入 api_hash: ').strip()
    if not raw_api_id.isdigit() or not api_hash:
        raise RuntimeError("api_id 必须是数字，api_hash 不能为空。")
    api_id = int(raw_api_id)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(API_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({"api_id": api_id, "api_hash": api_hash}, f, indent=2)
    try:
        os.chmod(API_CONFIG_FILE, 0o600)
    except OSError:
        pass
    return api_id, api_hash

def harden_runtime_files():
    for path in (API_CONFIG_FILE, api_auth_file + '.session', api_auth_file + '.session-journal', BIO_STATE_FILE):
        try:
            if os.path.exists(path) and not os.path.islink(path):
                os.chmod(path, 0o600)
        except OSError:
            pass

# ==========================================
# 【天气模块】
# ==========================================
def fetch_weather_sync(city_name):
    safe_city = urllib.parse.quote(city_name.strip())
    url = f"https://wttr.in/{safe_city}?format=j1"
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
    last_sent_name = None
    while True:
        try:
            now = time.localtime()
            month_day = time.strftime("%m-%d", now)
            hour_minute = time.strftime("%H:%M", now)
            timezone_name = get_utc_offset_text(now)
            config = load_config()
            if config['bio_enabled'] and 2 <= now.tm_hour < 4:
                last_name = "💤"
                if last_name != last_sent_name:
                    await client(UpdateProfileRequest(last_name=last_name))
                    last_sent_name = last_name
                    logger.info('Updated Last Name -> 💤')
                await asyncio.sleep(60 - (time.time() % 60))
                continue

            values = {
                "time": hour_minute if config['show_time'] else "",
                "timezone": timezone_name if config['show_timezone'] else "",
                "date": month_day if config['show_date'] else "",
                "temp": current_weather_data['temp'] if config['show_temp'] else "",
                "weather": current_weather_data['emoji'] if config['show_weather'] else "",
            }
            parts = [values[item] for item in config["name_order"] if values.get(item)]
            
            raw_name = " ".join(parts)
            last_name = raw_name.translate(BOLD_MAP) if config['use_bold'] else raw_name
            if last_name == last_sent_name:
                await asyncio.sleep(60 - (time.time() % 60))
                continue
            
            await client(UpdateProfileRequest(last_name=last_name))
            last_sent_name = last_name
            logger.info(f'Updated -> {last_name}')
        except FloodWaitError as e:
            logger.warning(f"Flood wait: sleeping {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
                
        except Exception as e:
            logger.error(f"Error: {e}")
        await asyncio.sleep(60 - (time.time() % 60))

def load_bio_update_date():
    try:
        with open(BIO_STATE_FILE, 'r', encoding='ascii') as f:
            return date.fromisoformat(f.read().strip())
    except (OSError, ValueError):
        return None

def save_bio_update_date(value):
    with open(BIO_STATE_FILE, 'w', encoding='ascii') as f:
        f.write(value.isoformat())
    os.chmod(BIO_STATE_FILE, 0o600)

async def update_bio_auto(client):
    last_updated_date = load_bio_update_date()
    while True:
        try:
            now = time.localtime()
            today = date(now.tm_year, now.tm_mon, now.tm_mday)
            config = load_config()
            birth_date = parse_birth_date(config.get("birth_date"))
            if config['bio_enabled'] and birth_date and now.tm_hour >= 3 and last_updated_date != today:
                bio_text = build_bio_text(birth_date, config['fixed_bio'], today)
                if len(bio_text) > MAX_BIO_LENGTH:
                    logger.error("Bio is too long: %s/%s characters", len(bio_text), MAX_BIO_LENGTH)
                else:
                    await client(UpdateProfileRequest(about=bio_text))
                    last_updated_date = today
                    save_bio_update_date(today)
                    logger.info('Updated Bio -> %s', bio_text)
        except FloodWaitError as e:
            logger.warning("Bio flood wait: sleeping %s seconds", e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error("Bio update error: %s", e)
        await asyncio.sleep(60 - (time.time() % 60))

# ==========================================
# 【主入口】
# ==========================================
async def main():
    migrate_legacy_runtime_files()
    login_only = len(sys.argv) > 1 and sys.argv[1] == '--login'
    session_exists = os.path.exists(api_auth_file+'.session')
    if not login_only and not session_exists and not sys.stdin.isatty():
        raise RuntimeError("缺少 Telegram 登录 Session，请先运行 `tg` 并使用选项 [1] 初始化账号。")

    api_id, api_hash = load_api_credentials(allow_prompt=sys.stdin.isatty())
        
    client = TelegramClient(api_auth_file, api_id, api_hash)
    await client.start()
    harden_runtime_files()
    
    # 如果仅为登录模式，则启动后直接退出
    if login_only:
        print("✅ 登录成功！凭证已生成。")
        await client.disconnect()
        return

    loop = asyncio.get_running_loop()
    task_name = asyncio.create_task(change_name_auto(client))
    task_weather = asyncio.create_task(update_weather_loop(loop))
    task_bio = asyncio.create_task(update_bio_auto(client))
    
    try:
        await client.run_until_disconnected()
    finally:
        task_name.cancel()
        task_weather.cancel()
        task_bio.cancel()
        await asyncio.gather(task_name, task_weather, task_bio, return_exceptions=True)

if __name__ == '__main__':
    asyncio.run(main())
