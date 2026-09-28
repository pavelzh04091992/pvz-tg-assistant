import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

def get_int_env(key: str, default: int) -> int:
    val = os.getenv(key, "")
    try:
        return int(val) if val.strip() else default
    except ValueError:
        return default

# Telegram Client (Userbot) credentials
# Get these at https://my.telegram.org (API development tools)
TG_API_ID = get_int_env("TG_API_ID", 0)
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_PHONE = os.getenv("TG_PHONE", "")
SESSION_NAME = str(BASE_DIR / "user_session")

# Telegram Control Bot (Aiogram) credentials
# Create bot in @BotFather and get token
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Your Telegram User ID (get via @userinfobot)
ADMIN_ID = get_int_env("ADMIN_ID", 0)

# OpenRouter AI Settings
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-3.8-flash")

# Target Chat IDs to monitor (list of integers, e.g. -1001980500934)
# Default IDs from analyzed chats:
# Ozon: -1001980500934, WB: -1003576456799
raw_chats = os.getenv("TARGET_CHAT_IDS", "-1001980500934,-1003576456799")
TARGET_CHAT_IDS = [int(c.strip()) for c in raw_chats.split(",") if c.strip()]

# Rate limit settings
MAX_DAILY_REPLIES_PER_CHAT = int(os.getenv("MAX_DAILY_REPLIES_PER_CHAT", "2"))
MIN_HOURS_BETWEEN_REPLIES = int(os.getenv("MIN_HOURS_BETWEEN_REPLIES", "3"))
TYPING_DELAY_SECONDS = int(os.getenv("TYPING_DELAY_SECONDS", "7"))
