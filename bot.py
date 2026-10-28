
import os
import asyncio

from pyrogram import Client, filters, idle
from pyrogram.types import Message

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, AudioQuality

from config import API_ID, API_HASH, SESSION_STRING, OWNER_ID


# ================= SUDO USERS =================
SUDO_USERS = {OWNER_ID}


# ================= INITIALIZE CLIENTS =================
app = Client(
    "tg_fight_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

call_py = PyTgCalls(app)


# ================= ACTIVE VC VARIABLES =================
current_logger_chat = None
current_target_chat = None
current_volume = 100
USERBOT_ID = None


# ================= AUTHORIZATION CHECKER =================
def is_authorized(_, __, message: Message):
    if not message.from_user:
        return False

    user_id = message.from_user.id

    return (
        user_id in SUDO_USERS
        or (USERBOT_ID is not None and user_id == USERBOT_ID)
    )


sudo_filter = filters.create(is_authorized)


# ================= COMMAND: .help =================
@app.on_message(filters.command("help", prefixes=".") & sudo_filter)
async def help_command(client: Client, message: Message):
    help_text = (
        "🔥 **Telegram Fight Voice Chat Bot - Help Menu** 🔥\n\n"
        "• **.help** - Show this help menu.\n"
        "• **.joinvc <logger_id> <target_id>** - Set logger and target groups.\n"
        "• **.leavevc** - Disconnect from the active voice chat.\n"
        "• **.volume <1-500>** - Set the requested volume level.\n"
        "• **.addsudo <user_id>** - Add a sudo user (Owner only).\n"
        "• **.rmsudo <user_id>** - Remove a sudo user (Owner only).\n"
        "• **.sudolist** - View all current sudo users."
    )

    await message.reply(help_text)


# ================= COMMAND: .addsudo =================
@app.on_message(
    filters.command("addsudo", prefixes=".") & filters.user(OWNER_ID)
)
async def add_sudo(client: Client, message: Message):
    try:
        args = (message.text or "").split()

        if len(args) < 2:
            await message.reply("Usage: `.addsudo <user_id>`")
            return

        user_id = int(args[1])
        SUDO_USERS.add(user_id)

        await message.reply(
            f"✅ Successfully added `{user_id}` to Sudo Users."
        )

    except ValueError:
        await message.reply("❌ Please provide a valid numeric user ID.")

    except Exception as e:
        await message.reply(f"❌ Error: {e}")


# ================= COMMAND: .rmsudo =================
@app.on_message(
    filters.command("rmsudo", prefixes=".") & filters.user(OWNER_ID)
)
async def remove_sudo(client: Client, message: Message):
    try:
        args = (message.text or "").split()

        if len(args) < 2:
            await message.reply("Usage: `.rmsudo <user_id>`")
            return

        user_id = int(args[1])

        if user_id == OWNER_ID:
            await message.reply(
                "❌ You cannot remove the owner from sudo!"
            )
            return

        if user_id in SUDO_USERS:
            SUDO_USERS.remove(user_id)

            await message.reply(
                f"✅ Successfully removed `{user_id}` from Sudo Users."
            )
        else:
            await message.reply(
                "⚠️ This user is not in the sudo list."
            )

    except ValueError:
        await message.reply("❌ Please provide a valid numeric user ID.")

    except Exception as e:
        await message.reply(f"❌ Error: {e}")


# ================= COMMAND: .sudolist =================
@app.on_message(
    filters.command("sudolist", prefixes=".") & sudo_filter
)
async def sudo_list(client: Client, message: Message):
    sudos = "\n".join(
        f"• `{uid}`" for uid in sorted(SUDO_USERS)
    )

    if not sudos:
        sudos = "No sudo users configured."

    await message.reply(
        "👑 **Authorized Sudo Users (plus Userbot Account):**\n\n"
        f"{sudos}"
    )


# ================= COMMAND: .joinvc =================
@app.on_message(
    filters.command("joinvc", prefixes=".") & sudo_filter
)
async def join_vc(client: Client, message: Message):
    global current_logger_chat, current_target_chat

    try:
        args = (message.text or "").split()

        if len(args) < 3:
            await message.reply(
                "Usage: `.joinvc <logger_group_id> <target_group_id>`"
            )
            return

        logger_chat = int(args[1])
        target_chat = int(args[2])

        await message.reply(
            "⚠️ Logger and target IDs received.\n\n"
            "A Telegram group ID is not an audio stream source. "
            "The previous `pipe:<logger_id>` input cannot relay audio "
            "from one Telegram voice chat into another.\n\n"
            "To implement actual VC-to-VC audio relay, the logger "
            "voice chat's audio must be captured and forwarded using "
            "a supported audio-streaming setup."
        )

        # Keep the requested IDs for subsequent commands.
        current_logger_chat = logger_chat
        current_target_chat = target_chat

    except ValueError:
        await message.reply(
            "❌ Invalid group ID. Please provide numeric group IDs."
        )

    except Exception as e:
        await message.reply(f"❌ Failed to process VC request: {e}")


# ================= COMMAND: .volume =================
@app.on_message(
    filters.command("volume", prefixes=".") & sudo_filter
)
async def set_volume(client: Client, message: Message):
    global current_volume

    try:
        args = (message.text or "").split()

        if len(args) < 2:
            await message.reply(
                f"Current requested volume: `{current_volume}%`\n"
                "Usage: `.volume <1-500>`"
            )
            return

        vol = int(args[1])

        if 1 <= vol <= 500:
            current_volume = vol

            await message.reply(
                f"🔊 Requested volume set to `{current_volume}%`.\n\n"
                "Note: this command stores the value; it does not "
                "apply audio amplification until a playback/relay "
                "pipeline is implemented."
            )
        else:
            await message.reply(
                "⚠️ Please enter a volume value between **1 and 500**."
            )

    except ValueError:
        await message.reply(
            "❌ Please enter a valid number between 1 and 500."
        )

    except Exception as e:
        await message.reply(f"❌ Error setting volume: {e}")


# ================= COMMAND: .leavevc =================
@app.on_message(
    filters.command("leavevc", prefixes=".") & sudo_filter
)
async def leave_vc(client: Client, message: Message):
    global current_logger_chat, current_target_chat

    try:
        if current_target_chat is None:
            await message.reply(
                "⚠️ No target voice chat is currently recorded."
            )
            return

        # Leave only if this PyTgCalls instance has an active call there.
        await call_py.leave_call(current_target_chat)

        current_logger_chat = None
        current_target_chat = None

        await message.reply(
            "🔌 Leave request completed."
        )

    except Exception as e:
        current_logger_chat = None
        current_target_chat = None

        await message.reply(
            f"⚠️ Could not leave the voice chat: {e}"
        )


# ================= MAIN ENTRYPOINT =================
async def main():
    global USERBOT_ID

    print("Starting Telegram Fight Userbot & PyTgCalls...")

    await app.start()

    try:
        await call_py.start()

        me = await app.get_me()
        USERBOT_ID = me.id

        print(
            f"Userbot started successfully as "
            f"@{me.username} (ID: {USERBOT_ID})!"
        )

        await idle()

    finally:
        try:
            await call_py.stop()
        except Exception:
            pass

        if app.is_connected:
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
