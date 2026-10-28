import asyncio
import logging
import numpy as np

# Create one event loop for Pyrogram and PyTgCalls.
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from pyrogram import Client, filters, idle
from pyrogram.types import Message

from pytgcalls import PyTgCalls
from pytgcalls import filters as call_filters
from pytgcalls.types import (
    Device,
    Direction,
    ExternalMedia,
    MediaStream,
    RecordStream,
    StreamFrames,
)
from pytgcalls.types.raw import AudioParameters

from config import API_ID, API_HASH, SESSION_STRING, OWNER_ID


# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TelegramFightVC")


# ================= SUDO USERS =================
SUDO_USERS = {OWNER_ID}


# ================= INITIALIZE CLIENTS =================
app = Client(
    "tg_fight_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
)

call_py = PyTgCalls(app)


# ================= ACTIVE VC VARIABLES =================
current_logger_chat = None
current_target_chat = None
current_volume = 100
USERBOT_ID = None

bridge_lock = asyncio.Lock()

AUDIO_PARAMETERS = AudioParameters(
    bitrate=48000,
    channels=2,
)


# ================= AUTHORIZATION =================
def is_authorized(_, __, message: Message):
    if not message.from_user:
        return False

    return (
        message.from_user.id in SUDO_USERS
        or (
            USERBOT_ID is not None
            and message.from_user.id == USERBOT_ID
        )
    )


sudo_filter = filters.create(is_authorized)


# ================= AUDIO RELAY =================
@call_py.on_update(
    call_filters.stream_frame(
        Direction.INCOMING,
        Device.MICROPHONE,
    )
)
async def relay_audio(_, update: StreamFrames):
    global current_logger_chat
    global current_target_chat
    global current_volume

    if current_logger_chat is None or current_target_chat is None:
        return

    if update.chat_id != current_logger_chat:
        return

    if not update.frames:
        return

    try:
        sample_arrays = [
            np.frombuffer(item.frame, dtype=np.int16)
            for item in update.frames
            if item.frame
        ]

        if not sample_arrays:
            return

        audio = np.concatenate(sample_arrays)

        gain = current_volume / 100.0

        audio = np.clip(
            audio.astype(np.float32) * gain,
            -32768,
            32767,
        ).astype(np.int16)

        await call_py.send_frame(
            current_target_chat,
            Device.MICROPHONE,
            audio.tobytes(),
        )

    except Exception:
        logger.exception("Audio relay failed")


# ================= COMMAND: .HELP =================
@app.on_message(
    filters.command("help", prefixes=".") & sudo_filter
)
async def help_command(client: Client, message: Message):
    await message.reply(
        "🔥 **Telegram Fight Voice Chat Bot** 🔥\n\n"
        "• `.help` - Show help.\n"
        "• `.joinvc <logger_id> <target_id>` - Start audio bridge.\n"
        "• `.leavevc` - Stop the bridge.\n"
        "• `.volume <1-500>` - Set audio gain.\n"
        "• `.addsudo <user_id>` - Add sudo (owner only).\n"
        "• `.rmsudo <user_id>` - Remove sudo (owner only).\n"
        "• `.sudolist` - Show sudo users."
    )


# ================= COMMAND: .ADDSUDO =================
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
            f"✅ Added `{user_id}` to sudo users."
        )

    except ValueError:
        await message.reply(
            "❌ Enter a valid numeric user ID."
        )

    except Exception as e:
        logger.exception("Add sudo error")
        await message.reply(f"❌ Error: {e}")


# ================= COMMAND: .RMSUDO =================
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
                "❌ You cannot remove the owner."
            )
            return

        if user_id not in SUDO_USERS:
            await message.reply(
                "⚠️ This user is not in the sudo list."
            )
            return

        SUDO_USERS.remove(user_id)

        await message.reply(
            f"✅ Removed `{user_id}` from sudo users."
        )

    except ValueError:
        await message.reply(
            "❌ Enter a valid numeric user ID."
        )

    except Exception as e:
        logger.exception("Remove sudo error")
        await message.reply(f"❌ Error: {e}")


# ================= COMMAND: .SUDOLIST =================
@app.on_message(
    filters.command("sudolist", prefixes=".") & sudo_filter
)
async def sudo_list(client: Client, message: Message):
    users = "\n".join(
        f"• `{uid}`" for uid in sorted(SUDO_USERS)
    )

    await message.reply(
        "👑 **Authorized Sudo Users**\n\n"
        + (users or "No sudo users.")
    )


# ================= COMMAND: .JOINVC =================
@app.on_message(
    filters.command("joinvc", prefixes=".") & sudo_filter
)
async def join_vc(client: Client, message: Message):
    global current_logger_chat
    global current_target_chat

    args = (message.text or "").split()

    if len(args) < 3:
        await message.reply(
            "Usage: `.joinvc <logger_group_id> <target_group_id>`"
        )
        return

    try:
        logger_chat = int(args[1])
        target_chat = int(args[2])

        if logger_chat == target_chat:
            await message.reply(
                "❌ Logger and target groups must be different."
            )
            return

        async with bridge_lock:
            if current_logger_chat is not None:
                await message.reply(
                    "⚠️ A bridge is already active. "
                    "Use `.leavevc` first."
                )
                return

            await message.reply(
                "🔄 Connecting to both voice chats and setting up audio..."
            )

            try:
                # Set up outgoing audio in the target group.
                await call_py.play(
                    target_chat,
                    MediaStream(
                        ExternalMedia.AUDIO,
                        AUDIO_PARAMETERS,
                    ),
                )

                # Set up recording in the logger group.
                await call_py.record(
                    logger_chat,
                    RecordStream(
                        True,
                        AUDIO_PARAMETERS,
                    ),
                )

                current_logger_chat = logger_chat
                current_target_chat = target_chat

                await message.reply(
                    "✅ **Voice bridge setup completed.**\n\n"
                    f"📡 Logger group: `{logger_chat}`\n"
                    f"🔊 Target group: `{target_chat}`\n"
                    f"🎚 Gain: `{current_volume}%`"
                )

            except Exception as e:
                logger.exception("Failed to start voice bridge")

                for chat_id in (logger_chat, target_chat):
                    try:
                        await call_py.leave_call(chat_id)
                    except Exception:
                        logger.warning(
                            "Cleanup failed for chat %s",
                            chat_id,
                            exc_info=True,
                        )

                current_logger_chat = None
                current_target_chat = None

                await message.reply(
                    "❌ Could not start the voice bridge.\n\n"
                    f"Error: `{type(e).__name__}: {e}`\n\n"
                    "Check that both groups have active voice chats, "
                    "the account can join, and the installed PyTgCalls "
                    "version supports the requested methods."
                )

    except ValueError:
        await message.reply(
            "❌ Both group IDs must be numeric."
        )

    except Exception as e:
        logger.exception("Join VC error")
        await message.reply(
            f"❌ Join failed: {type(e).__name__}: {e}"
        )


# ================= COMMAND: .VOLUME =================
@app.on_message(
    filters.command("volume", prefixes=".") & sudo_filter
)
async def set_volume(client: Client, message: Message):
    global current_volume

    args = (message.text or "").split()

    if len(args) < 2:
        await message.reply(
            f"Current gain: `{current_volume}%`\n"
            "Usage: `.volume <1-500>`"
        )
        return

    try:
        value = int(args[1])

        if not 1 <= value <= 500:
            await message.reply(
                "⚠️ Choose a value between 1 and 500."
            )
            return

        current_volume = value

        await message.reply(
            f"🔊 Requested audio gain set to `{current_volume}%`."
        )

    except ValueError:
        await message.reply(
            "❌ Enter a valid number."
        )

    except Exception as e:
        logger.exception("Volume error")
        await message.reply(f"❌ Volume error: {e}")


# ================= COMMAND: .LEAVEVC =================
@app.on_message(
    filters.command("leavevc", prefixes=".") & sudo_filter
)
async def leave_vc(client: Client, message: Message):
    global current_logger_chat
    global current_target_chat

    async with bridge_lock:
        if (
            current_logger_chat is None
            and current_target_chat is None
        ):
            await message.reply("⚠️ No active bridge.")
            return

        chat_ids = {
            chat_id
            for chat_id in (
                current_logger_chat,
                current_target_chat,
            )
            if chat_id is not None
        }

        errors = []

        for chat_id in chat_ids:
            try:
                await call_py.leave_call(chat_id)

            except Exception as e:
                errors.append(f"{chat_id}: {e}")

                logger.exception(
                    "Failed leaving chat %s",
                    chat_id,
                )

        current_logger_chat = None
        current_target_chat = None

        if errors:
            await message.reply(
                "⚠️ Some voice chats may not have disconnected:\n"
                + "\n".join(errors)
            )
        else:
            await message.reply(
                "🔌 Left both voice chats."
            )


# ================= MAIN =================
async def main():
    global USERBOT_ID

    logger.info("Starting Telegram Fight Voice Bridge...")

    await app.start()

    try:
        await call_py.start()

        me = await app.get_me()
        USERBOT_ID = me.id

        logger.info(
            "Userbot started as @%s (ID: %s)",
            me.username,
            me.id,
        )

        await idle()

    finally:
        try:
            await call_py.stop()
        except Exception:
            logger.exception("Error stopping PyTgCalls")

        try:
            if app.is_connected:
                await app.stop()
        except Exception:
            logger.exception("Error stopping Pyrogram")


# ================= ENTRY POINT =================
if __name__ == "__main__":
    try:
        loop.run_until_complete(main())

    except KeyboardInterrupt:
        logger.info("Bot stopped by keyboard interrupt.")

    except Exception:
        logger.exception("Fatal startup error.")

    finally:
        if not loop.is_closed():
            loop.close()
