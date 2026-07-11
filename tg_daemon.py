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
import signal
import copy
from datetime import date
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.account import UpdateProfileRequest
import bio_templates
import bio_template_loader

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
LETTER_SOURCE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
LETTER_STYLE_MAPS = {
    "normal": str.maketrans("", ""),
    "sans_bold": str.maketrans(LETTER_SOURCE, "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇"),
    "script": str.maketrans(LETTER_SOURCE, "𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏"),
    "bold_script": str.maketrans(LETTER_SOURCE, "𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃"),
    "monospace": str.maketrans(LETTER_SOURCE, "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣"),
    "double_struck": str.maketrans(LETTER_SOURCE, "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫"),
}
current_weather_data = {"temp": "", "emoji": ""}
DEFAULT_NAME_ORDER = ["time", "timezone", "date", "temp", "weather", "emoji"]
LAST_NAME_FIELD_TYPES = DEFAULT_NAME_ORDER.copy()
LAST_NAME_ITEM_TYPES = (*LAST_NAME_FIELD_TYPES, "text")
ORDER_LABELS = {
    "time": "时间",
    "timezone": "时区",
    "date": "日期",
    "temp": "温度",
    "weather": "天气",
    "emoji": "Emoji",
    "text": "自定义文本",
}
DEFAULT_CONFIG = {"show_time": True, "show_timezone": True, "show_date": False, "show_temp": True, "show_weather": True, "location": "Los Angeles", "digit_style": "sans_bold", "letter_style": "normal", "name_order": DEFAULT_NAME_ORDER.copy(), "last_name_mode": "classic", "last_name_rules": [], "last_name_default_items": [{"type": item} for item in DEFAULT_NAME_ORDER], "bio_enabled": False, "birth_date": "", "fixed_bio": "", "bio_template": "elapsed_en", "update_interval": 1, "emoji_schedules": []}
BOOL_CONFIG_KEYS = ("show_time", "show_timezone", "show_date", "show_temp", "show_weather", "bio_enabled")
UPDATE_INTERVALS = (1, 5, 15, 30, 60)
MAX_LOCATION_LENGTH = 80
MAX_BIO_LENGTH = 70
MAX_EMOJI_RULES = 20
MAX_EMOJI_TEXT_LENGTH = 32
MAX_ACTIVE_EMOJI_LENGTH = 32
MAX_ACTIVE_STATE_LENGTH = 128
MAX_LAST_NAME_LENGTH = 64
MAX_LAST_NAME_RULES = 20
MAX_LAST_NAME_TEXT_LENGTH = 32
MAX_LAST_NAME_RULE_NAME_LENGTH = 24
MAX_CONFIG_FILE_SIZE = 256 * 1024
MAX_API_CONFIG_FILE_SIZE = 16 * 1024
MAX_WEATHER_RESPONSE_SIZE = 512 * 1024

def normalize_name_order(order):
    if not isinstance(order, list):
        order = []

    normalized = []
    for item in order:
        if item in DEFAULT_NAME_ORDER and item not in normalized:
            normalized.append(item)

    for item in DEFAULT_NAME_ORDER:
        if item not in normalized:
            normalized.append(item)

    return normalized

def normalize_last_name_text(value):
    if not isinstance(value, str):
        return ""
    cleaned = " ".join("".join(char for char in value.strip() if char.isprintable()).split())
    return cleaned[:MAX_LAST_NAME_TEXT_LENGTH]

def normalize_last_name_items(items):
    if not isinstance(items, list):
        return []

    normalized = []
    for item in items:
        if isinstance(item, str):
            item = {"type": item}
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in LAST_NAME_FIELD_TYPES:
            normalized.append({"type": item_type})
        elif item_type == "text":
            text = normalize_last_name_text(item.get("value"))
            if text:
                normalized.append({"type": "text", "value": text})
        if len(normalized) >= len(DEFAULT_NAME_ORDER) + 6:
            break
    return normalized

def default_last_name_items_from_order(order):
    return [{"type": item} for item in normalize_name_order(order)]

def normalize_last_name_rules(rules):
    if not isinstance(rules, list):
        return []

    normalized = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        start = parse_time_text(rule.get("start"))
        end = parse_time_text(rule.get("end"))
        items = normalize_last_name_items(rule.get("items"))
        if not start or not end or start == end or not items:
            continue
        name = normalize_last_name_text(rule.get("name"))[:MAX_LAST_NAME_RULE_NAME_LENGTH] or f"{start}-{end}"
        normalized.append({"name": name, "start": start, "end": end, "items": items})
        if len(normalized) >= MAX_LAST_NAME_RULES:
            break
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

def join_non_empty(parts):
    return " ".join(str(part) for part in parts if part)

def build_bio_context(birth_date, fixed_bio, today=None, config=None, local_time=None, weather_data=None):
    years, months, days = calculate_elapsed(birth_date, today)
    today = today or date.today()
    local_time = local_time or time.localtime()
    config = config or DEFAULT_CONFIG
    weather_data = weather_data or {"temp": "", "emoji": ""}
    ctx = {
        "years": years,
        "months": months,
        "days": days,
        "birth_date": birth_date,
        "today": today,
        "fixed_bio": fixed_bio,
        "time": time.strftime("%H:%M", local_time),
        "timezone": get_utc_offset_text(local_time),
        "date": time.strftime("%m-%d", local_time),
        "location": config.get("location", ""),
        "temp": weather_data.get("temp", ""),
        "weather": weather_data.get("emoji", ""),
        "digit_style": config.get("digit_style", "sans_bold"),
        "letter_style": config.get("letter_style", "normal"),
        "max_length": MAX_BIO_LENGTH,
    }
    ctx["join"] = join_non_empty
    ctx["elapsed_en"] = lambda: bio_templates.elapsed_en(ctx)
    return ctx

def build_bio_text(birth_date, fixed_bio, today=None, template_name="elapsed_en", config=None, local_time=None, weather_data=None):
    ctx = build_bio_context(birth_date, fixed_bio, today, config, local_time, weather_data)
    try:
        return bio_template_loader.render_bio(template_name, ctx, DATA_DIR)
    except Exception:
        logger.warning("Bio template %s failed; using elapsed_en", template_name, exc_info=True)
        return bio_template_loader.render_bio("elapsed_en", ctx, DATA_DIR)

def sanitize_config(raw_config):
    config = copy.deepcopy(DEFAULT_CONFIG)
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

    letter_style = raw_config.get("letter_style")
    if letter_style in LETTER_STYLE_MAPS:
        config["letter_style"] = letter_style

    location = raw_config.get("location")
    if isinstance(location, str) and location.strip():
        printable_location = "".join(char for char in location.strip() if char.isprintable())
        cleaned_location = " ".join(printable_location.split())
        if cleaned_location:
            config["location"] = cleaned_location[:MAX_LOCATION_LENGTH]

    config["name_order"] = normalize_name_order(raw_config.get("name_order"))
    if raw_config.get("last_name_mode") == "custom":
        config["last_name_mode"] = "custom"
    config["last_name_default_items"] = normalize_last_name_items(raw_config.get("last_name_default_items"))
    if not config["last_name_default_items"]:
        config["last_name_default_items"] = default_last_name_items_from_order(config["name_order"])
    config["last_name_rules"] = normalize_last_name_rules(raw_config.get("last_name_rules"))
    birth_date = parse_birth_date(raw_config.get("birth_date"))
    if birth_date:
        config["birth_date"] = birth_date.isoformat()

    fixed_bio = raw_config.get("fixed_bio")
    if isinstance(fixed_bio, str):
        config["fixed_bio"] = "".join(char for char in fixed_bio.strip() if char.isprintable())[:MAX_BIO_LENGTH]

    bio_template = raw_config.get("bio_template")
    if bio_template_loader.template_exists(bio_template, DATA_DIR):
        config["bio_template"] = bio_template

    if not config["birth_date"] or not config["fixed_bio"]:
        config["bio_enabled"] = False
    elif len(build_bio_text(birth_date, config["fixed_bio"], template_name=config["bio_template"], config=config)) > MAX_BIO_LENGTH:
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

def normalize_api_hash(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value.lower() if re.fullmatch(r"[0-9a-fA-F]{32}", value) else None

def normalize_api_id(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        api_id = value
    elif isinstance(value, str) and value.strip().isdigit():
        api_id = int(value.strip())
    else:
        return None
    return api_id if 0 < api_id <= 2_147_483_647 else None

def load_api_credentials(allow_prompt=False):
    env_api_id = os.environ.get("TELEGRAM_API_ID")
    env_api_hash = os.environ.get("TELEGRAM_API_HASH")
    if env_api_id is not None or env_api_hash is not None:
        if not env_api_id or not env_api_hash:
            raise RuntimeError("TELEGRAM_API_ID 和 TELEGRAM_API_HASH 必须同时设置。")
        api_id = normalize_api_id(env_api_id)
        api_hash = normalize_api_hash(env_api_hash)
        if api_id is None or api_hash is None:
            raise RuntimeError("TELEGRAM_API_ID 必须为正整数，TELEGRAM_API_HASH 必须是 32 位十六进制字符串。")
        return api_id, api_hash

    try:
        with open(API_CONFIG_FILE, 'r', encoding='utf-8') as f:
            content = f.read(MAX_API_CONFIG_FILE_SIZE + 1)
        if len(content) > MAX_API_CONFIG_FILE_SIZE:
            raise ValueError
        data = json.loads(content)
        api_id = normalize_api_id(data["api_id"])
        api_hash = normalize_api_hash(data["api_hash"])
        if api_id is None or api_hash is None:
            raise ValueError
        return api_id, api_hash
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        pass

    if not allow_prompt:
        raise RuntimeError("缺少 Telegram API 凭证，请先运行 `tg` 并使用选项 [1] 初始化账号。")

    raw_api_id = input('请输入 api_id: ').strip()
    api_hash = normalize_api_hash(getpass.getpass('请输入 api_hash: '))
    api_id = normalize_api_id(raw_api_id)
    if api_id is None or api_hash is None:
        raise RuntimeError("api_id 必须是正整数，api_hash 必须是 32 位十六进制字符串。")
    os.makedirs(DATA_DIR, exist_ok=True)
    save_text_atomic(
        API_CONFIG_FILE,
        json.dumps({"api_id": api_id, "api_hash": api_hash}, indent=2),
        'utf-8',
    )
    return api_id, api_hash

def harden_runtime_files():
    for path in (CONFIG_FILE, API_CONFIG_FILE, api_auth_file + '.session', api_auth_file + '.session-journal', BIO_STATE_FILE, EMOJI_STATE_FILE):
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

async def refresh_weather(loop):
    global current_weather_data
    config = load_config()
    if not (config['show_temp'] or config['show_weather']):
        current_weather_data = {"temp": "", "emoji": ""}
        return True

    result = await loop.run_in_executor(None, fetch_weather_sync, config['location'])
    current_weather_data = result
    return bool(result['temp'])

async def update_weather_loop(loop):
    while True:
        success = await refresh_weather(loop)
        delay = 3600 if success else 300
        await asyncio.sleep(delay)

# ==========================================
# 【核心拼接模块】
# ==========================================
def is_update_minute(minute, interval):
    return interval in UPDATE_INTERVALS and minute % interval == 0

def get_active_emoji(schedules, local_time):
    minute_of_day = local_time.tm_hour * 60 + local_time.tm_min
    return [rule["emoji"] for rule in schedules if is_rule_active(rule, minute_of_day)]

def get_active_last_name_rule(rules, local_time):
    minute_of_day = local_time.tm_hour * 60 + local_time.tm_min
    for rule in rules:
        if is_rule_active(rule, minute_of_day):
            return rule
    return None

def compose_last_name(parts):
    selected = []
    used = 0
    for part in parts:
        extra = len(part) + (1 if selected else 0)
        if used + extra > MAX_LAST_NAME_LENGTH:
            continue
        selected.append(part)
        used += extra
    return " ".join(selected)

def build_last_name_context(config, local_time, respect_switches=True):
    active_emojis = get_active_emoji(config['emoji_schedules'], local_time)
    return {
        "time": time.strftime("%H:%M", local_time) if not respect_switches or config['show_time'] else "",
        "timezone": get_utc_offset_text(local_time) if not respect_switches or config['show_timezone'] else "",
        "date": time.strftime("%m-%d", local_time) if not respect_switches or config['show_date'] else "",
        "temp": current_weather_data['temp'] if not respect_switches or config['show_temp'] else "",
        "weather": current_weather_data['emoji'] if not respect_switches or config['show_weather'] else "",
        "emoji": "".join(active_emojis),
    }

def render_last_name_items(items, context, digit_style, letter_style="normal"):
    digit_map = DIGIT_STYLE_MAPS[digit_style]
    letter_map = LETTER_STYLE_MAPS[letter_style]
    parts = []
    active_state_parts = []
    for item in items:
        item_type = item.get("type")
        value = item.get("value", "") if item_type == "text" else context.get(item_type, "")
        if value:
            if item_type == "emoji":
                parts.append(value)
            else:
                parts.append(value.translate(digit_map).translate(letter_map))
        if item_type in ("emoji", "text") and value:
            active_state_parts.append(value)
    return compose_last_name(parts), "|".join(active_state_parts)

def build_classic_last_name(config, local_time):
    context = build_last_name_context(config, local_time)
    return render_last_name_items(
        [{"type": item} for item in config["name_order"]],
        context,
        config["digit_style"],
        config["letter_style"],
    )

def build_custom_last_name(config, local_time):
    context = build_last_name_context(config, local_time, respect_switches=False)
    rule = get_active_last_name_rule(config["last_name_rules"], local_time)
    items = rule["items"] if rule else config["last_name_default_items"]
    last_name, active_state = render_last_name_items(items, context, config["digit_style"], config["letter_style"])
    if rule:
        rule_state = f"rule:{rule['start']}-{rule['end']}:{rule['name']}"
    else:
        rule_state = "default"
    return last_name, f"{rule_state}|{active_state}"[:MAX_ACTIVE_STATE_LENGTH]

def build_dynamic_last_name(config, local_time):
    if config.get("last_name_mode") == "custom":
        return build_custom_last_name(config, local_time)
    return build_classic_last_name(config, local_time)

def should_skip_for_bio_update(config, local_time):
    return bool(config.get("bio_enabled")) and local_time.tm_hour == 3 and local_time.tm_min == 0

def load_emoji_active_state():
    try:
        with open(EMOJI_STATE_FILE, 'r', encoding='utf-8') as f:
            return f.read(MAX_ACTIVE_STATE_LENGTH + 1)[:MAX_ACTIVE_STATE_LENGTH]
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

async def wait_for_next_name_update(force_event):
    delay = 60 - (time.time() % 60)
    try:
        await asyncio.wait_for(force_event.wait(), timeout=max(delay, 0.05))
        force_event.clear()
        return True
    except asyncio.TimeoutError:
        return False

async def update_profile(client, update_lock, **fields):
    async with update_lock:
        await client(UpdateProfileRequest(**fields))

async def get_current_last_name(client, update_lock):
    async with update_lock:
        me = await client.get_me()
    return me.last_name or ""

def save_emoji_state_safely(value):
    try:
        save_emoji_active_state(value)
    except OSError:
        logger.warning("Failed to save Emoji state", exc_info=True)

async def update_last_name_once(
    client,
    update_lock,
    config,
    local_time,
    last_sent_name,
    last_active_emoji,
    forced=False,
    force_restore=False,
    skip_once=False,
):
    if not forced and (skip_once or should_skip_for_bio_update(config, local_time)):
        logger.info("Skipped one Last Name update after Bio update")
        return last_sent_name, last_active_emoji, False

    last_name, active_emoji = build_dynamic_last_name(config, local_time)
    emoji_changed = active_emoji != last_active_emoji
    if not forced and not force_restore and not emoji_changed and not is_update_minute(local_time.tm_min, config['update_interval']):
        return last_sent_name, last_active_emoji, False

    if not forced and last_name == last_sent_name:
        if emoji_changed:
            save_emoji_state_safely(active_emoji)
            last_active_emoji = active_emoji
        return last_sent_name, last_active_emoji, False

    await update_profile(client, update_lock, last_name=last_name)
    save_emoji_state_safely(active_emoji)
    logger.info('Updated -> %s', last_name)
    return last_name, active_emoji, True

async def change_name_auto(client, update_lock, force_event=None, skip_once_event=None):
    force_event = force_event or asyncio.Event()
    skip_once_event = skip_once_event or asyncio.Event()
    last_sent_name = None
    last_active_emoji = load_emoji_active_state()
    first_run = True
    while True:
        force_restore = False
        try:
            if first_run:
                forced = force_event.is_set()
                if forced:
                    force_event.clear()
                last_sent_name = await get_current_last_name(client, update_lock)
                first_run = False
                initial_time = time.localtime()
                force_restore = last_sent_name == "💤"
                if not forced and not force_restore and initial_time.tm_sec > 1:
                    forced = await wait_for_next_name_update(force_event)
            else:
                forced = await wait_for_next_name_update(force_event)

            now = time.localtime()
            config = load_config()
            skip_once = skip_once_event.is_set()
            if skip_once:
                skip_once_event.clear()
            last_sent_name, last_active_emoji, _ = await update_last_name_once(
                client,
                update_lock,
                config,
                now,
                last_sent_name,
                last_active_emoji,
                forced=forced,
                force_restore=force_restore,
                skip_once=skip_once,
            )
        except FloodWaitError as e:
            logger.warning(f"Flood wait: sleeping {e.seconds} seconds")
            if forced:
                force_event.set()
            await asyncio.sleep(e.seconds)
                
        except Exception as e:
            logger.error("Last Name update error: %s", e, exc_info=True)
            if forced:
                await asyncio.sleep(60)
                force_event.set()
            if first_run:
                await wait_for_next_name_update(force_event)

def load_bio_update_date():
    try:
        with open(BIO_STATE_FILE, 'r', encoding='ascii') as f:
            return date.fromisoformat(f.read(32).strip())
    except (OSError, ValueError):
        return None

def save_bio_update_date(value):
    save_text_atomic(BIO_STATE_FILE, value.isoformat(), 'ascii')

async def update_bio_once(client, update_lock, config, today, last_updated_date, forced=False, skip_once_event=None):
    birth_date = parse_birth_date(config.get("birth_date"))
    should_update = forced or last_updated_date != today
    if not config['bio_enabled'] or birth_date is None or not should_update:
        return last_updated_date, False

    bio_text = build_bio_text(
        birth_date,
        config['fixed_bio'],
        today,
        config["bio_template"],
        config=config,
        local_time=time.localtime(),
        weather_data=current_weather_data,
    )
    if len(bio_text) > MAX_BIO_LENGTH:
        logger.error("Bio is too long: %s/%s characters", len(bio_text), MAX_BIO_LENGTH)
        return last_updated_date, False

    await update_profile(client, update_lock, about=bio_text)
    try:
        save_bio_update_date(today)
    except OSError:
        logger.warning("Failed to save Bio update state", exc_info=True)
    if skip_once_event is not None and not forced:
        skip_once_event.set()
    logger.info('Updated Bio -> %s', bio_text)
    return today, True

async def wait_for_next_bio_check(force_event):
    delay = 60 - (time.time() % 60)
    try:
        await asyncio.wait_for(force_event.wait(), timeout=max(delay, 0.05))
        force_event.clear()
        return True
    except asyncio.TimeoutError:
        return False

async def update_bio_auto(client, update_lock, force_event=None, skip_once_event=None):
    force_event = force_event or asyncio.Event()
    last_updated_date = load_bio_update_date()
    forced = force_event.is_set()
    if forced:
        force_event.clear()
    while True:
        try:
            now = time.localtime()
            today = date(now.tm_year, now.tm_mon, now.tm_mday)
            config = load_config()
            if forced or now.tm_hour >= 3:
                last_updated_date, _ = await update_bio_once(
                    client,
                    update_lock,
                    config,
                    today,
                    last_updated_date,
                    forced=forced,
                    skip_once_event=skip_once_event,
                )
        except FloodWaitError as e:
            logger.warning("Bio flood wait: sleeping %s seconds", e.seconds)
            if forced:
                force_event.set()
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error("Bio update error: %s", e, exc_info=True)
            if forced:
                await asyncio.sleep(60)
                force_event.set()
        forced = await wait_for_next_bio_check(force_event)

# ==========================================
# 【主入口】
# ==========================================
async def main():
    os.umask(0o077)
    login_only = len(sys.argv) > 1 and sys.argv[1] == '--login'
    loop = asyncio.get_running_loop()
    force_name_event = asyncio.Event()
    force_bio_event = asyncio.Event()
    skip_last_name_once_event = asyncio.Event()
    if not login_only:
        loop.add_signal_handler(signal.SIGUSR1, force_name_event.set)
        loop.add_signal_handler(signal.SIGUSR2, force_bio_event.set)

    migrate_legacy_runtime_files()
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

    update_lock = asyncio.Lock()
    task_name = asyncio.create_task(change_name_auto(client, update_lock, force_name_event, skip_last_name_once_event))
    task_weather = asyncio.create_task(update_weather_loop(loop))
    task_bio = asyncio.create_task(update_bio_auto(client, update_lock, force_bio_event, skip_last_name_once_event))
    
    try:
        await client.run_until_disconnected()
    finally:
        task_name.cancel()
        task_weather.cancel()
        task_bio.cancel()
        await asyncio.gather(task_name, task_weather, task_bio, return_exceptions=True)

if __name__ == '__main__':
    asyncio.run(main())
