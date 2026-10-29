import os

# ==============================
# API CONFIGURATION
# ==============================

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

# ==============================
# BOT CONFIGURATION
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Pyrogram Userbot Session String
SESSION_STRING = os.getenv("SESSION_STRING", "")

# ==============================
# OWNER CONFIGURATION
# ==============================

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "llNOBI_XDll")

# ==============================
# SUPPORT CONFIGURATION
# ==============================

SUPPORT_CHAT = os.getenv(
    "SUPPORT_CHAT",
    "https://t.me/lVAMPIRE_WORLDl"
)

UPDATE_CHANNEL = os.getenv(
    "UPDATE_CHANNEL",
    "https://t.me/lVAMPIRE_WORLDl"
)
