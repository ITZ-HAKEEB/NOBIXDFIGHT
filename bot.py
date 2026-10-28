import asyncio
import logging
import numpy as np

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


# ================= CLIENT =================
app = Client(
    "tg_fight_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
)

call_py = PyTgCalls(app)


# ================= BRIDGE STATE =================
current_logger_chat = None
current_target_chat = None
USERBOT_ID = None

# Volume is a percentage-style control.
# Values above 100 increase processing gain, not guaranteed
# acoustic loudness on the listener's device.
current_volume = 200       # 1-500
current_echo = 0           # 0-10
current_gain = 0           # 0-200

SAMPLE_RATE = 48000
CHANNELS = 2

ECHO_DELAY_SAMPLES = int(SAMPLE_RATE * 0.18) * CHANNELS
echo_buffer = np.zeros(ECHO_DELAY_SAMPLES, dtype=np.float32)

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


# ================= AUDIO PROCESSING =================
def process_audio(raw_audio: bytes) -> bytes:
    """
    Process incoming int16 PCM audio:
    - Output gain
    - Adjustable echo
    - Controlled saturation/distortion
    - Soft limiting to prevent integer overflow
    """
    global echo_buffer

    if not raw_audio:
        return raw_audio

    audio = np.frombuffer(raw_audio, dtype=np.int16)

    if audio.size == 0:
        return raw_audio

    audio = audio.astype(np.float32)

    # 1. Output gain.
    # The limiter below prevents unbounded output peaks.
    volume_multiplier = current_volume / 100.0
    audio *= volume_multiplier

    # 2. Echo.
    if current_echo == 0:
        echo_buffer.fill(0)
    else:
        if len(echo_buffer) != ECHO_DELAY_SAMPLES:
            echo_buffer = np.zeros(
                ECHO_DELAY_SAMPLES,
                dtype=np.float32,
            )

        combined = np.concatenate((echo_buffer, audio))
        delayed = combined[:len(audio)]

        echo_buffer = combined[-ECHO_DELAY_SAMPLES:].copy()

        echo_strength = current_echo / 10.0
        audio += delayed * (0.20 * echo_strength)

    # 3. Controlled saturation.
    # Higher gain produces a stronger compressed/distorted character.
    # Gain 0 leaves this additional effect disabled.
    if current_gain > 0:
        drive = 1.0 + (current_gain / 20.0)
        audio = 32767.0 * np.tanh(
            (audio / 32767.0) * drive
        )

    # 4. Soft limiter.
    # This keeps output peaks bounded; it cannot guarantee that
    # highly distorted audio will remain intelligible.
    audio = 32767.0 * np.tanh(audio / 32767.0)

    audio = np.clip(
        audio,
        -32768,
        32767,
    ).astype(np.int16)

    return audio.tobytes()


# ================= AUDIO BRIDGE =================
@call_py.on_update(
    call_filters.stream_frame(
        Direction.INCOMING,
        Device.MICROPHONE,
    )
)
async def relay_audio(_, update: StreamFrames):
    logger_chat = current_logger_chat
    target_chat = current_target_chat

    if logger_chat is None or target_chat is None:
        return

    if update.chat_id != logger_chat:
        return

    if not update.frames:
        return

    try:
        frame_arrays = [
            np.frombuffer(frame.frame, dtype=np.int16)
            for frame in update.frames
            if frame.frame
        ]

        if not frame_arrays:
            return

        audio = np.concatenate(frame_arrays)
        processed_audio = process_audio(audio.tobytes())

        await call_py.send_frame(
            target_chat,
            Device.MICROPHONE,
            processed_audio,
        )

    except Exception:
        logger.exception("Audio forwarding failed")


# ================= .HELP =================
@app.on_message(
    filters.command("help", prefixes=".") & sudo_filter
)
async def help_command(client: Client, message: Message):
    await message.reply(
        "🔥 **Telegram Fight Voice Chat Bot** 🔥\n\n"
        "• `.help` - Show commands.\n"
        "• `.joinvc <logger_id> <target_id>` - Start bridge.\n"
        "• `.leavevc` - Stop bridge.\n"
        "• `.volume <1-500>` - Set output gain.\n"
        "• `.echo <0-10>` - Set echo; 0 disables it.\n"
        "• `.gain <0-200>` - Set distortion; 0 disables it.\n"
        "• `.addsudo <user_id>` - Add sudo user.\n"
        "• `.rmsudo <user_id>` - Remove sudo user.\n"
        "• `.sudolist` - Show sudo users."
    )


# ================= .ADDSUDO =================
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
        await message.reply("❌ Enter a valid numeric user ID.")

    except Exception as e:
        logger.exception("Add sudo failed")
        await message.reply(f"❌ Error: {e}")


# ================= .RMSUDO =================
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
            await message.reply("❌ You cannot remove the owner.")
            return

        if user_id not in SUDO_USERS:
            await message.reply("⚠️ User is not in the sudo list.")
            return

        SUDO_USERS.remove(user_id)

        await message.reply(
            f"✅ Removed `{user_id}` from sudo users."
        )

    except ValueError:
        await message.reply("❌ Enter a valid numeric user ID.")

    except Exception as e:
        logger.exception("Remove sudo failed")
        await message.reply(f"❌ Error: {e}")


# ================= .SUDOLIST =================
@app.on_message(
    filters.command("sudolist", prefixes=".") & sudo_filter
)
async def sudo_list(client: Client, message: Message):
    users = "\n".join(
        f"• `{user_id}`" for user_id in sorted(SUDO_USERS)
    )

    await message.reply(
        "👑 **Authorized Sudo Users**\n\n"
        + (users or "No sudo users.")
    )


# ================= .JOINVC =================
@app.on_message(
    filters.command("joinvc", prefixes=".") & sudo_filter
)
async def join_vc(client: Client, message: Message):
    global current_logger_chat
    global current_target_chat
    global echo_buffer

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
                "❌ Logger and target must be different groups."
            )
            return

    except ValueError:
        await message.reply(
            "❌ Both group IDs must be numeric."
        )
        return

    async with bridge_lock:
        if current_logger_chat is not None:
            await message.reply(
                "⚠️ Bridge is already active. Use `.leavevc` first."
            )
            return

        await message.reply(
            "🔄 Connecting to logger and target voice chats..."
        )

        try:
            # Prepare outgoing streams.
            for chat_id in (logger_chat, target_chat):
                await call_py.play(
                    chat_id,
                    MediaStream(
                        ExternalMedia.AUDIO,
                        AUDIO_PARAMETERS,
                    ),
                )

            # Capture incoming streams.
            for chat_id in (logger_chat, target_chat):
                await call_py.record(
                    chat_id,
                    RecordStream(
                        True,
                        AUDIO_PARAMETERS,
                    ),
                )

            current_logger_chat = logger_chat
            current_target_chat = target_chat

            echo_buffer = np.zeros(
                ECHO_DELAY_SAMPLES,
                dtype=np.float32,
            )

            await message.reply(
                "✅ **Voice bridge initialized**\n\n"
                f"📡 Logger: `{logger_chat}`\n"
                f"🔊 Target: `{target_chat}`\n"
                f"🎚 Volume: `{current_volume}/500`\n"
                f"🔁 Echo: `{current_echo}/10`\n"
                f"🎛 Gain: `{current_gain}/200`\n\n"
                "Audio from the logger group will be processed "
                "and forwarded to the target group."
            )

        except Exception as e:
            logger.exception("Failed to initialize voice bridge")

            for chat_id in (logger_chat, target_chat):
                try:
                    await call_py.leave_call(chat_id)
                except Exception:
                    logger.warning(
                        "No call to clean up for group %s",
                        chat_id,
                    )

            current_logger_chat = None
            current_target_chat = None

            await message.reply(
                "❌ **Bridge initialization failed**\n\n"
                f"Error: `{type(e).__name__}: {e}`\n\n"
                "Check that the account is a member of both groups "
                "and that both group IDs are correct."
            )


# ================= .VOLUME =================
@app.on_message(
    filters.command("volume", prefixes=".") & sudo_filter
)
async def set_volume(client: Client, message: Message):
    global current_volume

    args = (message.text or "").split()

    if len(args) < 2:
        await message.reply(
            f"🔊 Current volume: `{current_volume}/500`\n"
            "Usage: `.volume <1-500>`"
        )
        return

    try:
        value = int(args[1])

        if not 1 <= value <= 500:
            await message.reply(
                "⚠️ Enter a value between 1 and 500."
            )
            return

        current_volume = value

        await message.reply(
            f"🔊 Volume setting updated to `{current_volume}/500`."
        )

    except ValueError:
        await message.reply("❌ Enter a valid number.")

    except Exception as e:
        logger.exception("Volume update failed")
        await message.reply(f"❌ Error: {e}")


# ================= .ECHO =================
@app.on_message(
    filters.command("echo", prefixes=".") & sudo_filter
)
async def set_echo(client: Client, message: Message):
    global current_echo
    global echo_buffer

    args = (message.text or "").split()

    if len(args) < 2:
        await message.reply(
            f"🔁 Current echo: `{current_echo}/10`\n"
            "Usage: `.echo <0-10>`\n"
            "Use `.echo 0` to turn echo off."
        )
        return

    try:
        value = int(args[1])

        if not 0 <= value <= 10:
            await message.reply(
                "⚠️ Echo must be between 0 and 10."
            )
            return

        current_echo = value

        if value == 0:
            echo_buffer.fill(0)
            await message.reply("🔁 Echo disabled.")
        else:
            await message.reply(
                f"🔁 Echo set to `{current_echo}/10`."
            )

    except ValueError:
        await message.reply("❌ Enter a valid number.")

    except Exception as e:
        logger.exception("Echo update failed")
        await message.reply(f"❌ Error: {e}")


# ================= .GAIN =================
@app.on_message(
    filters.command("gain", prefixes=".") & sudo_filter
)
async def set_gain(client: Client, message: Message):
    global current_gain

    args = (message.text or "").split()

    if len(args) < 2:
        await message.reply(
            f"🎛 Current distortion: `{current_gain}/200`\n"
            "Usage: `.gain <0-200>`\n"
            "Use `.gain 0` to disable added distortion."
        )
        return

    try:
        value = int(args[1])

        if not 0 <= value <= 200:
            await message.reply(
                "⚠️ Gain must be between 0 and 200."
            )
            return

        current_gain = value

        if value == 0:
            await message.reply(
                "🎛 Added distortion disabled."
            )
        else:
            await message.reply(
                f"🎛 Distortion set to `{current_gain}/200`."
            )

    except ValueError:
        await message.reply("❌ Enter a valid number.")

    except Exception as e:
        logger.exception("Gain update failed")
        await message.reply(f"❌ Error: {e}")


# ================= .LEAVEVC =================
@app.on_message(
    filters.command("leavevc", prefixes=".") & sudo_filter
)
async def leave_vc(client: Client, message: Message):
    global current_logger_chat
    global current_target_chat
    global echo_buffer

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
                logger.warning(
                    "Could not leave group %s: %s",
                    chat_id,
                    e,
                )

        current_logger_chat = None
        current_target_chat = None
        echo_buffer.fill(0)

        if errors:
            await message.reply(
                "⚠️ Some voice chats may not have disconnected:\n"
                + "\n".join(errors)
            )
        else:
            await message.reply(
                "🔌 Left both voice chats. Audio bridge stopped."
            )


# ================= MAIN =================
async def main():
    global USERBOT_ID

    logger.info("Starting Telegram Fight Voice Chat Bot...")

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
        logger.info("Bot stopped.")

    except Exception:
        logger.exception("Fatal startup error.")

    finally:
        if not loop.is_closed():
            loop.close()
