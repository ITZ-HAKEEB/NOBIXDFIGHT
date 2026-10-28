import os
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped, AudioQuality
from config import API_ID, API_HASH, SESSION_STRING, OWNER_ID

# Set to store authorized Sudo users
SUDO_USERS = {OWNER_ID}

# Initialize Pyrogram Client (Userbot) & PyTgCalls
app = Client(
    "tg_fight_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)
call_py = PyTgCalls(app)

# Active VC and volume tracking variables
current_logger_chat = None
current_target_chat = None
current_volume = 100  # Default volume 100 (Range: 1 to 500)
USERBOT_ID = None

# ================= HELPER: AUTHORIZATION CHECKER =================
def is_authorized(_, __, message: Message):
    if not message.from_user:
        return False
    user_id = message.from_user.id
    return user_id in SUDO_USERS or (USERBOT_ID and user_id == USERBOT_ID)

sudo_filter = filters.create(is_authorized)

# ================= COMMAND: .help =================
@app.on_message(filters.command("help", prefixes=".") & sudo_filter)
async def help_command(client: Client, message: Message):
    help_text = (
        "🔥 **Telegram Fight Voice Chat Bot - Help Menu** 🔥\n\n"
        "• **.help** - Show this help menu.\n"
        "• **.joinvc <logger_id> <target_id>** - Connect userbot to Logger VC & Target VC.\n"
        "• **.leavevc** - Disconnect from active voice chats.\n"
        "• **.volume <1-500>** - Adjust audio boost volume level (1 to 500).\n"
        "• **.addsudo <user_id>** - Add a new user to sudo list (Owner only).\n"
        "• **.rmsudo <user_id>** - Remove a user from sudo list (Owner only).\n"
        "• **.sudolist** - View all current sudo users."
    )
    await message.reply(help_text)

# ================= COMMAND: .addsudo & .rmsudo =================
@app.on_message(filters.command("addsudo", prefixes=".") & filters.user(OWNER_ID))
async def add_sudo(client: Client, message: Message):
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.reply("Usage: `.addsudo <user_id>`")
            return
        user_id = int(args[1])
        SUDO_USERS.add(user_id)
        await message.reply(f"✅ Successfully added `{user_id}` to Sudo Users.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

@app.on_message(filters.command("rmsudo", prefixes=".") & filters.user(OWNER_ID))
async def remove_sudo(client: Client, message: Message):
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.reply("Usage: `.rmsudo <user_id>`")
            return
        user_id = int(args[1])
        if user_id == OWNER_ID:
            await message.reply("❌ You cannot remove the owner from sudo!")
            return
        if user_id in SUDO_USERS:
            SUDO_USERS.remove(user_id)
            await message.reply(f"✅ Successfully removed `{user_id}` from Sudo Users.")
        else:
            await message.reply("⚠️ This user is not in the sudo list.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

@app.on_message(filters.command("sudolist", prefixes=".") & sudo_filter)
async def sudo_list(client: Client, message: Message):
    sudos = "\n".join([f"• `{uid}`" for uid in SUDO_USERS])
    await message.reply(f"👑 **Authorized Sudo Users (plus Userbot Account):**\n\n{sudos}")

# ================= COMMAND: .joinvc =================
@app.on_message(filters.command("joinvc", prefixes=".") & sudo_filter)
async def join_vc(client: Client, message: Message):
    global current_logger_chat, current_target_chat, current_volume
    try:
        args = message.text.split()
        if len(args) < 3:
            await message.reply("Usage: `.joinvc <logger_group_id> <target_group_id>`")
            return
        
        current_logger_chat = int(args[1])
        current_target_chat = int(args[2])
        
        await message.reply("🔄 Joining Voice Chats in Logger & Target groups...")
        
        await call_py.join_group_call(
            current_target_chat,
            AudioPiped(
                f"pipe:{current_logger_chat}",
                audio_parameters=AudioQuality.STUDIO_QUALITY,
            ),
        )
        
        await message.reply(
            f"🚀 **Successfully Joined Voice Chats!**\n\n"
            f"📡 **Logger Group:** `{current_logger_chat}`\n"
            f"🎯 **Target Group:** `{current_target_chat}`\n"
            f"🔊 **Volume Boost:** `{current_volume}%`"
        )
    except Exception as e:
        await message.reply(f"❌ Failed to join Voice Chat: {e}")

# ================= COMMAND: .volume =================
@app.on_message(filters.command("volume", prefixes=".") & sudo_filter)
async def set_volume(client: Client, message: Message):
    global current_volume
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.reply(f"Current Volume: `{current_volume}%`\nUsage: `.volume <1-500>`")
            return
        
        vol = int(args[1])
        if 1 <= vol <= 500:
            current_volume = vol
            await message.reply(f"🔊 Volume successfully updated to `{current_volume}%` (High Boost Active)")
        else:
            await message.reply("⚠️ Please enter a volume value between **1 and 500**.")
    except Exception as e:
        await message.reply(f"❌ Error setting volume: {e}")

# ================= COMMAND: .leavevc =================
@app.on_message(filters.command("leavevc", prefixes=".") & sudo_filter)
async def leave_vc(client: Client, message: Message):
    global current_logger_chat, current_target_chat
    try:
        if current_target_chat:
            await call_py.leave_group_call(current_target_chat)
            current_logger_chat = None
            current_target_chat = None
            await message.reply("🔌 Successfully left the Voice Chats.")
        else:
            await message.reply("⚠️ The userbot is not connected to any voice chat.")
    except Exception as e:
        await message.reply(f"❌ Error leaving VC: {e}")

# ================= MAIN ENTRYPOINT =================
async def main():
    global USERBOT_ID
    print("Starting Telegram Fight Userbot & PyTgCalls on Heroku...")
    await app.start()
    await call_py.start()
    
    me = await app.get_me()
    USERBOT_ID = me.id
    print(f"Userbot started successfully as @{me.username} (ID: {USERBOT_ID})!")
    
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
