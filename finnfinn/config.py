import os
from zoneinfo import ZoneInfo

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
_owners = [int(x) for x in os.environ.get("OWNER_IDS", "").split(",") if x.strip()]
OWNER_IDS = set(_owners)
FIRST_OWNER = _owners[0] if _owners else None
WEBAPP_URL = os.environ.get("WEBAPP_URL", "http://localhost:8080")
DB_PATH = os.environ.get("DB_PATH", "/data/finnfinn.db")
PORT = int(os.environ.get("PORT", "8080"))
OCR_ENABLED = os.environ.get("OCR", "on").lower() not in ("off", "0", "false", "no")
BACKUP_TO_TELEGRAM = os.environ.get("BACKUP_TO_TELEGRAM", "0") == "1"
DEV_NO_AUTH = os.environ.get("DEV_NO_AUTH", "0") == "1"
WIB = ZoneInfo("Asia/Jakarta")
