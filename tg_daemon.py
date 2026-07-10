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
import tempfile
import re
import getpass
from datetime import date
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.account import UpdateProfileRequest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_INSTALLED = BASE_DIR == "/opt/tg_updater"
DEFAULT_DATA_DIR = "/var/lib/tg_updater" if IS_INSTALLED else BASE_DIR
DATA_DIR = DEFAULT_DATA_DIR if IS_INSTALLED else os.environ.get("TG_UPDATER_DATA_DIR", DEFAULT_DATA_DIR)
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
API_CONFIG_FILE = os.path.join(DATA_DIR, 'api_auth.json')
BIO_STATE_FILE = os.path.join(DATA_DIR, 'bio_last_update.txt')
EMOJI_STATE_FILE = os.path.join(DATA_DIR, 'emoji_last_active.txt')
api_auth_file = os.path.join(DATA_DIR, 'api_auth')
LEGACY_CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
LEGACY_API_CONFIG_FILE = os.path.join(BASE_DIR, 'api_auth.json')
LEGACY_SESSION_FILE = os.path.join(BASE_DIR, 'api_auth.session')
LEGACY_SESSION_JOURNAL_FILE = os.path.join(BASE_DIR, 'api_auth.session-journal')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DIGIT_STYLE_MAPS = {
    "normal": str.maketrans("", ""),
    "sans_bold": str.maketrans("0123456789", "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"),
    "serif_bold": str.maketrans("0123456789", "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"),
    "double_struck": str.maketrans("0123456789", "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"),
}
current_weather_data = {"temp": "", "emoji": ""}
DEFAULT_NAME_ORDER = ["time", "timezone", "date", "temp", "weather"]
ORDER_LABELS = {
    "time": "时间",
    "timezone": "时区",
    "date": "日期",
    "temp": "温度",
    "weather": "天气",
}
DEFAULT_CONFIG = {"show_time": True, "show_timezone": True, "show_date": False, "show_temp": True, "show_weather": True, "location": "Los Angeles", "digit_style": "sans_bold", "name_order": DEFAULT_NAME_ORDER.copy(), "bio_enabled": False, "birth_date": "", "fixed_bio": "", "update_interval": 1, "emoji_schedules": []}
BOOL_CONFIG_KEYS = ("show_time", "show_timezone", "show_date", "show_temp", "show_weather", "bio_enabled")
UPDATE_INTERVALS = (1, 5, 15, 30, 60)
MAX_LOCATION_LENGTH = 80
MAX_BIO_LENGTH = 70
MAX_EMOJI_RULES = 20
MAX_EMOJI_TEXT_LENGTH = 32
MAX_ACTIVE_EMOJI_LENGTH = 32
MAX_LAST_NAME_LENGTH = 64
MAX_CONFIG_FILE_SIZE = 256 * 1024
MAX_API_CONFIG_FILE_SIZE = 16 * 1024
MAX_WEATHER_RESPONSE_SIZE = 512 * 1024

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

def parse_time_text(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if len(value) != 5 or value[2] != ":" or not value[:2].isdigit() or not value[3:].isdigit():
        return None
    hour, minute = int(value[:2]), int(value[3:])
    return value if 0 <= hour <= 23 and 0 <= minute <= 59 else None

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
        if not start or not end or start == end or not emoji:
            continue
        if max_active_emoji_length([*normalized, candidate]) > MAX_ACTIVE_EMOJI_LENGTH:
            continue
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
    if digit_style in DIGIT_STYLE_MAPS:
        config["digit_style"] = digit_style
    elif isinstance(raw_config.get("use_bold"), bool):
        config["digit_style"] = "sans_bold" if raw_config["use_bold"] else "normal"

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
    elif len(build_bio_text(birth_date, config["fixed_bio"])) > MAX_BIO_LENGTH:
        config["bio_enabled"] = False

    update_interval = raw_config.get("update_interval")
    if isinstance(update_interval, int) and not isinstance(update_interval, bool) and update_interval in UPDATE_INTERVALS:
        config["update_interval"] = update_interval
    config["emoji_schedules"] = normalize_emoji_schedules(raw_config.get("emoji_schedules"))
    return config

def load_config():
    loaded = {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            content = f.read(MAX_CONFIG_FILE_SIZE + 1)
        if len(content) > MAX_CONFIG_FILE_SIZE:
            raise ValueError("config file exceeds size limit")
        loaded = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        logger.warning("Failed to load config; using safe defaults", exc_info=True)
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
    if env_api_id is not None or env_api_hash is not None:
        if not env_api_id or not env_api_hash:
            raise RuntimeError("TELEGRAM_API_ID 和 TELEGRAM_API_HASH 必须同时设置。")
        try:
            api_id = int(env_api_id)
        except ValueError as exc:
            raise RuntimeError("环境变量 TELEGRAM_API_ID 必须是数字。") from exc
        if api_id <= 0 or not env_api_hash.strip():
            raise RuntimeError("环境变量 TELEGRAM_API_ID 必须为正整数，TELEGRAM_API_HASH 不能为空。")
        return api_id, env_api_hash.strip()

    try:
        with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
            content = f.read(MAX_API_CONFIG_FILE_SIZE + 1)
        if len(content) > MAX_API_CONFIG_FILE_SIZE:
            raise ValueError
        data = json.loads(content)
        api_id = int(data["api_id"])
        api_hash = data["api_hash"]
        if api_id <= 0 or not isinstance(api_hash, str) or not api_hash.strip():
            raise ValueError
        return api_id, api_hash.strip()
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        pass

    if not allow_prompt:
        raise RuntimeError("缺少 Telegram API 凭证，请先运行 `tg` 并使用选项 [1] 初始化账号。")

    raw_api_id = input('请输入 api_id: ').strip()
    api_hash = getpass.getpass('请输入 api_hash: ').strip()
    if not raw_api_id.isdigit() or int(raw_api_id) <= 0 or not api_hash:
        raise RuntimeError("api_id 必须是正整数，api_hash 不能为空。")
    api_id = int(raw_api_id)
    os.makedirs(DATA_DIR, exist_ok=True)
    save_text_atomic(
        API_CONFIG_FILE,
        json.dumps({"api_id": api_id, "api_hash": api_hash}, indent=2),
        'utf-8',
    )
    return api_id, api_hash

def harden_runtime_files():
    for path in (API_CONFIG_FILE, api_auth_file + '.session', api_auth_file + '.session-journal', BIO_STATE_FILE, EMOJI_STATE_FILE):
        try:
            if os.path.exists(path) and not os.path.islink(path):
                os.chmod(path, 0o600)
        except OSError:
            pass

# ==========================================
# 【天气模块】
# ==========================================
def fetch_weather_sync(city_name):
    safe_city = urllib.parse.quote(city_name.strip(), safe="")
    url = f"https://wttr.in/{safe_city}?format=j1"
    req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_WEATHER_RESPONSE_SIZE:
                raise ValueError("weather response exceeds size limit")
            content = response.read(MAX_WEATHER_RESPONSE_SIZE + 1)
            if len(content) > MAX_WEATHER_RESPONSE_SIZE:
                raise ValueError("weather response exceeds size limit")
            data = json.loads(content.decode('utf-8'))
            condition = data['current_condition'][0]['weatherDesc'][0]['value'].lower()
            current_temp = str(data['current_condition'][0]['temp_C'])
            if not re.fullmatch(r"-?\d{1,3}", current_temp) or not -100 <= int(current_temp) <= 100:
                raise ValueError("invalid weather temperature")
            
            emoji = "☁️" 
            if "sun" in condition or "clear" in condition: emoji = "☀️"
            elif "partly cloudy" in condition: emoji = "⛅"
            elif "rain" in condition or "shower" in condition or "drizzle" in condition: emoji = "🌧️"
            elif "snow" in condition: emoji = "❄️"
            elif "thunder" in condition or "storm" in condition: emoji = "⛈️"
            elif "fog" in condition or "mist" in condition: emoji = "🌫️"
            
            return {"temp": f"{current_temp}°C", "emoji": emoji}
    except Exception:
        logger.warning("Weather update failed for %s", city_name, exc_info=True)
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
def is_update_minute(minute, interval):
    return interval in UPDATE_INTERVALS and minute % interval == 0

def get_active_emoji(schedules, local_time):
    minute_of_day = local_time.tm_hour * 60 + local_time.tm_min
    return [rule["emoji"] for rule in schedules if is_rule_active(rule, minute_of_day)]

def compose_last_name(parts, active_emojis):
    base_name = " ".join(parts)
    if not active_emojis:
        return base_name
    available = MAX_LAST_NAME_LENGTH - len(base_name) - (1 if base_name else 0)
    if available <= 0:
        return base_name[:MAX_LAST_NAME_LENGTH]
    selected = []
    used = 0
    for emoji in active_emojis:
        if used + len(emoji) > available:
            continue
        selected.append(emoji)
        used += len(emoji)
    emoji_text = "".join(selected)
    if not emoji_text:
        return base_name[:MAX_LAST_NAME_LENGTH]
    return f"{base_name} {emoji_text}" if base_name else emoji_text

def load_emoji_active_state():
    try:
        with open(EMOJI_STATE_FILE, 'r', encoding='utf-8') as f:
            return f.read(MAX_ACTIVE_EMOJI_LENGTH + 1)[:MAX_ACTIVE_EMOJI_LENGTH]
    except OSError:
        return None

def save_text_atomic(path, value, encoding):
    fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=DATA_DIR, text=True)
    try:
        with os.fdopen(fd, 'w', encoding=encoding) as f:
            f.write(value)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

def save_emoji_active_state(value):
    save_text_atomic(EMOJI_STATE_FILE, value, 'utf-8')

async def sleep_until_next_minute():
    delay = 60 - (time.time() % 60)
    await asyncio.sleep(max(delay, 0.05))

async def update_profile(client, update_lock, **fields):
    async with update_lock:
        await client(UpdateProfileRequest(**fields))

async def get_current_last_name(client, update_lock):
    async with update_lock:
        me = await client.get_me()
    return me.last_name or ""

async def change_name_auto(client, update_lock):
    last_sent_name = None
    last_active_emoji = load_emoji_active_state()
    first_run = True
    while True:
        force_restore = False
        try:
            if first_run:
                last_sent_name = await get_current_last_name(client, update_lock)
                first_run = False
                initial_time = time.localtime()
                initial_config = load_config()
                is_sleep_window = initial_config['bio_enabled'] and 2 <= initial_time.tm_hour < 4
                force_restore = not is_sleep_window and last_sent_name == "💤"
                if not is_sleep_window and not force_restore and initial_time.tm_sec > 1:
                    await sleep_until_next_minute()
            else:
                await sleep_until_next_minute()

            now = time.localtime()
            month_day = time.strftime("%m-%d", now)
            hour_minute = time.strftime("%H:%M", now)
            timezone_name = get_utc_offset_text(now)
            config = load_config()
            if config['bio_enabled'] and 2 <= now.tm_hour < 4:
                last_name = "💤"
                if last_name != last_sent_name:
                    await update_profile(client, update_lock, last_name=last_name)
                    last_sent_name = last_name
                    logger.info('Updated Last Name -> 💤')
                continue

            active_emojis = get_active_emoji(config['emoji_schedules'], now)
            active_emoji = "".join(active_emojis)
            emoji_changed = active_emoji != last_active_emoji
            if not force_restore and not emoji_changed and not is_update_minute(now.tm_min, config['update_interval']):
                continue

            values = {
                "time": hour_minute if config['show_time'] else "",
                "timezone": timezone_name if config['show_timezone'] else "",
                "date": month_day if config['show_date'] else "",
                "temp": current_weather_data['temp'] if config['show_temp'] else "",
                "weather": current_weather_data['emoji'] if config['show_weather'] else "",
            }
            parts = [values[item] for item in config["name_order"] if values.get(item)]
            styled_parts = [part.translate(DIGIT_STYLE_MAPS[config['digit_style']]) for part in parts]
            last_name = compose_last_name(styled_parts, active_emojis)
            if last_name == last_sent_name:
                if emoji_changed:
                    last_active_emoji = active_emoji
                    try:
                        save_emoji_active_state(active_emoji)
                    except OSError:
                        logger.warning("Failed to save Emoji state", exc_info=True)
                continue
            
            await update_profile(client, update_lock, last_name=last_name)
            last_sent_name = last_name
            last_active_emoji = active_emoji
            try:
                save_emoji_active_state(active_emoji)
            except OSError:
                logger.warning("Failed to save Emoji state", exc_info=True)
            logger.info(f'Updated -> {last_name}')
        except FloodWaitError as e:
            logger.warning(f"Flood wait: sleeping {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
                
        except Exception as e:
            logger.error(f"Error: {e}")
            if first_run:
                await sleep_until_next_minute()

def load_bio_update_date():
    try:
        with open(BIO_STATE_FILE, 'r', encoding='ascii') as f:
            return date.fromisoformat(f.read(32).strip())
    except (OSError, ValueError):
        return None

def save_bio_update_date(value):
    save_text_atomic(BIO_STATE_FILE, value.isoformat(), 'ascii')

async def update_bio_auto(client, update_lock):
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
                    await update_profile(client, update_lock, about=bio_text)
                    last_updated_date = today
                    try:
                        save_bio_update_date(today)
                    except OSError:
                        logger.warning("Failed to save Bio update state", exc_info=True)
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
    os.umask(0o077)
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
    update_lock = asyncio.Lock()
    task_name = asyncio.create_task(change_name_auto(client, update_lock))
    task_weather = asyncio.create_task(update_weather_loop(loop))
    task_bio = asyncio.create_task(update_bio_auto(client, update_lock))
    
    try:
        await client.run_until_disconnected()
    finally:
        task_name.cancel()
        task_weather.cancel()
        task_bio.cancel()
        await asyncio.gather(task_name, task_weather, task_bio, return_exceptions=True)

if __name__ == '__main__':
    asyncio.run(main())
