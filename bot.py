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


# ================= AUDIO SETTINGS =================

current_logger_chat = None
current_target_chat = None
USERBOT_ID = None

current_volume = 12000
current_boost = 100
current_echo = 10000
current_gain = 2000
current_bass = 1500
current_double = True

SAMPLE_RATE = 48000
CHANNELS = 2

# Echo delay: 320 ms
ECHO_DELAY_SECONDS = 0.32
ECHO_DELAY_SAMPLES = int(SAMPLE_RATE * ECHO_DELAY_SECONDS) * CHANNELS

# Double voice delay: 22 ms
DOUBLE_DELAY_SECONDS = 0.022
DOUBLE_DELAY_SAMPLES = int(SAMPLE_RATE * DOUBLE_DELAY_SECONDS) * CHANNELS

echo_buffer = np.zeros(ECHO_DELAY_SAMPLES, dtype=np.float32)
double_buffer = np.zeros(DOUBLE_DELAY_SAMPLES, dtype=np.float32)

echo_position = 0
double_position = 0

bass_filter_state = np.zeros(CHANNELS, dtype=np.float32)

bridge_lock = asyncio.Lock()

AUDIO_PARAMETERS = AudioParameters(
    bitrate=48000,
    channels=2,
)


# ================= BOOST CURVE =================

def get_boost_multiplier(value: int) -> float:
    value = max(1, min(5000, int(value)))

    if value <= 100:
        return 0.1 + (0.9 * (value - 1) / 99.0)

    return 1.0 + (1.5 * (value - 100) / 4900.0)


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


# ================= RESET AUDIO BUFFERS =================

def reset_audio_buffers():
    global echo_buffer
    global double_buffer
    global echo_position
    global double_position
    global bass_filter_state

    echo_buffer.fill(0)
    double_buffer.fill(0)

    echo_position = 0
    double_position = 0

    bass_filter_state.fill(0)


# ================= DELAY PROCESSOR =================

def delay_process(audio, buffer, position, feedback):
    """
    Circular delay buffer.
    Maintains delay history between incoming audio frames.
    """

    flat = audio.reshape(-1)
    size = len(buffer)

    indexes = (
        position + np.arange(len(flat))
    ) % size

    delayed = buffer[indexes].copy()

    # Feedback creates repeated echo.
    buffer[indexes] = flat + delayed * feedback

    new_position = (position + len(flat)) % size

    return delayed, new_position


# ================= AUDIO PROCESSING =================

def process_audio(raw_audio: bytes) -> bytes:
    global echo_buffer
    global double_buffer
    global echo_position
    global double_position
    global bass_filter_state

    if not raw_audio:
        return raw_audio

    samples = np.frombuffer(raw_audio, dtype=np.int16)

    if samples.size < CHANNELS:
        return raw_audio

    usable = (samples.size // CHANNELS) * CHANNELS

    audio = samples[:usable].astype(
        np.float32
    ).reshape(-1, CHANNELS)

    # ---------------------------------
    # 1. VOLUME
    # ---------------------------------

    volume = max(0, min(12000, int(current_volume)))

    volume_db = (volume / 12000.0) * 6.0

    volume_multiplier = 10.0 ** (volume_db / 20.0)

    audio *= volume_multiplier

    # ---------------------------------
    # 2. BOOST
    # ---------------------------------

    audio *= get_boost_multiplier(current_boost)

    # ---------------------------------
    # 3. DOUBLE VOICE
    # ---------------------------------

    if current_double:

        delayed, double_position = delay_process(
            audio,
            double_buffer,
            double_position,
            0.0,
        )

        audio = audio + delayed.reshape(
            -1, CHANNELS
        ) * 0.25

    else:
        double_buffer.fill(0)
        double_position = 0

    # ---------------------------------
    # 4. BASS BOOST
    # ---------------------------------

    if current_bass > 0:

        low = np.empty_like(audio)

        state = bass_filter_state.copy()

        alpha = 0.025

        for i in range(len(audio)):
            state += alpha * (audio[i] - state)
            low[i] = state

        bass_filter_state = state.copy()

        bass_amount = min(
            1500,
            max(0, int(current_bass))
        ) / 1500.0

        # Controlled low-frequency enhancement.
        audio += low * (0.45 * bass_amount)

    # ---------------------------------
    # 5. FULL ECHO WITH REPEATS
    # ---------------------------------

    if current_echo > 0:

        echo_value = min(
            10000,
            max(0, int(current_echo))
        ) / 10000.0

        delayed, echo_position = delay_process(
            audio,
            echo_buffer,
            echo_position,
            feedback=0.38 * echo_value,
        )

        delayed = delayed.reshape(-1, CHANNELS)

        # Wet echo mix.
        wet = 0.55 * echo_value

        audio = audio * (1.0 - wet * 0.35) + delayed * wet

    else:
        echo_buffer.fill(0)
        echo_position = 0

    # ---------------------------------
    # 6. GAIN / VOICE PUNCH
    # ---------------------------------

    gain = min(
        2000,
        max(0, int(current_gain))
    )

    if gain > 0:

        drive = 1.0 + (gain / 2000.0) * 1.5

        # Soft saturation adds presence.
        audio = 32767.0 * np.tanh(
            (audio / 32767.0) * drive
        )

    # ---------------------------------
    # 7. OUTPUT LIMITER
    # ---------------------------------

    peak = float(
        np.max(np.abs(audio))
    ) if audio.size else 0.0

    target_peak = 24500.0

    if peak > target_peak:
        audio *= target_peak / peak

    audio = np.clip(
        audio,
        -32768,
        32767,
    ).astype(np.int16)

    return audio.reshape(-1).tobytes()


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

        processed_audio = process_audio(
            audio.tobytes()
        )

        await call_py.send_frame(
            target_chat,
            Device.MICROPHONE,
            processed_audio,
        )

    except Exception:
        logger.exception("Audio forwarding failed")


# ================= HELP =================

@app.on_message(
    filters.command("help", prefixes=".") & sudo_filter
)
async def help_command(client: Client, message: Message):

    await message.reply(
        "🔥 **TELEGRAM FIGHT VOICE BOT** 🔥\n\n"

        "🎙 **VOICE COMMANDS**\n\n"

        "• `.joinvc <logger_id> <target_id>`\n"
        "• `.leavevc`\n"
        "• `.volume <0-12000>`\n"
        "• `.boost <1-5000>`\n"
        "• `.echo <0-10000>`\n"
        "• `.gain <0-2000>`\n"
        "• `.bass <0-1500>`\n"
        "• `.double on`\n"
        "• `.double off`\n\n"

        "👑 **SUDO COMMANDS**\n\n"

        "• `.addsudo <user_id>`\n"
        "• `.rmsudo <user_id>`\n"
        "• `.sudolist`\n\n"

        "🔊 **DEFAULT EFFECTS**\n\n"

        "Volume: 12000\n"
        "Echo: 10000\n"
        "Gain: 2000\n"
        "Bass: 1500\n"
        "Double Voice: ON"
    )


# ================= ADDSUDO =================

@app.on_message(
    filters.command("addsudo", prefixes=".") & filters.user(OWNER_ID)
)
async def add_sudo(client: Client, message: Message):

    try:

        args = (message.text or "").split()

        if len(args) < 2:
            await message.reply(
                "Usage: `.addsudo <user_id>`"
            )
            return

        user_id = int(args[1])

        if user_id <= 0:
            await message.reply(
                "❌ Enter a valid positive user ID."
            )
            return

        SUDO_USERS.add(user_id)

        await message.reply(
            f"✅ Added `{user_id}` to sudo users."
        )

    except ValueError:
        await message.reply(
            "❌ Enter a valid numeric user ID."
        )

    except Exception as e:
        logger.exception("Add sudo failed")
        await message.reply(f"❌ Error: {e}")


# ================= RMSUDO =================

@app.on_message(
    filters.command("rmsudo", prefixes=".") & filters.user(OWNER_ID)
)
async def remove_sudo(client: Client, message: Message):

    try:

        args = (message.text or "").split()

        if len(args) < 2:
            await message.reply(
                "Usage: `.rmsudo <user_id>`"
            )
            return

        user_id = int(args[1])

        if user_id == OWNER_ID:
            await message.reply(
                "❌ You cannot remove the owner."
            )
            return

        if user_id not in SUDO_USERS:
            await message.reply(
                "⚠️ User is not in the sudo list."
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
        logger.exception("Remove sudo failed")
        await message.reply(f"❌ Error: {e}")


# ================= SUDOLIST =================

@app.on_message(
    filters.command("sudolist", prefixes=".") & sudo_filter
)
async def sudo_list(client: Client, message: Message):

    users = "\n".join(
        f"• `{user_id}`"
        for user_id in sorted(SUDO_USERS)
    )

    await message.reply(
        "👑 **AUTHORIZED SUDO USERS**\n\n"
        + (users or "No sudo users.")
    )


# ================= JOINVC =================

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
                "⚠️ Bridge already active. Use `.leavevc` first."
            )
            return

        await message.reply(
            "🔄 Connecting to both voice chats..."
        )

        try:

            for chat_id in (logger_chat, target_chat):

                await call_py.play(
                    chat_id,
                    MediaStream(
                        ExternalMedia.AUDIO,
                        AUDIO_PARAMETERS,
                    ),
                )

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

            reset_audio_buffers()

            await message.reply(
                "✅ **VOICE BRIDGE CONNECTED**\n\n"

                f"📡 Logger: `{logger_chat}`\n"
                f"🔊 Target: `{target_chat}`\n\n"

                f"🎚 Volume: `{current_volume}/12000`\n"
                f"📢 Boost: `{current_boost}/5000`\n"
                f"🔁 Echo: `{current_echo}/10000`\n"
                f"🎛 Gain: `{current_gain}/2000`\n"
                f"💥 Bass: `{current_bass}/1500`\n"
                f"🎙 Double: `{'ON' if current_double else 'OFF'}`\n\n"

                "Audio bridge is active."
            )

        except Exception as e:

            logger.exception(
                "Failed to initialize voice bridge"
            )

            for chat_id in (logger_chat, target_chat):

                try:
                    await call_py.leave_call(chat_id)

                except Exception:
                    logger.warning(
                        "Could not clean up group %s",
                        chat_id,
                    )

            current_logger_chat = None
            current_target_chat = None

            reset_audio_buffers()

            await message.reply(
                "❌ **BRIDGE INITIALIZATION FAILED**\n\n"
                f"Error: `{type(e).__name__}: {e}`\n\n"
                "Check group membership and voice chat status."
            )


# ================= VOLUME =================

@app.on_message(
    filters.command("volume", prefixes=".") & sudo_filter
)
async def set_volume(client: Client, message: Message):

    global current_volume

    args = (message.text or "").split()

    if len(args) < 2:
        await message.reply(
            f"🔊 Volume: `{current_volume}/12000`\n"
            "Usage: `.volume <0-12000>`"
        )
        return

    try:

        value = int(args[1])

        if not 0 <= value <= 12000:
            await message.reply(
                "⚠️ Volume must be between 0 and 12000."
            )
            return

        current_volume = value

        await message.reply(
            f"🔊 Volume updated: `{value}/12000`."
        )

    except ValueError:
        await message.reply(
            "❌ Enter a valid number."
        )


# ================= BOOST =================

@app.on_message(
    filters.command("boost", prefixes=".") & sudo_filter
)
async def set_boost(client: Client, message: Message):

    global current_boost

    args = (message.text or "").split()

    if len(args) < 2:
        await message.reply(
            f"📢 Boost: `{current_boost}/5000`\n"
            f"Multiplier: `{get_boost_multiplier(current_boost):.2f}x`\n"
            "Usage: `.boost <1-5000>`"
        )
        return

    try:

        value = int(args[1])

        if not 1 <= value <= 5000:
            await message.reply(
                "⚠️ Boost must be between 1 and 5000."
            )
            return

        current_boost = value

        await message.reply(
            f"📢 Boost updated: `{value}/5000`\n"
            f"Multiplier: `{get_boost_multiplier(value):.2f}x`"
        )

    except ValueError:
        await message.reply(
            "❌ Enter a valid number."
        )


# ================= ECHO =================

@app.on_message(
    filters.command("echo", prefixes=".") & sudo_filter
)
async def set_echo(client: Client, message: Message):

    global current_echo

    args = (message.text or "").split()

    if len(args) < 2:
        await message.reply(
            f"🔁 Echo: `{current_echo}/10000`\n"
            "Usage: `.echo <0-10000>`"
        )
        return

    try:

        value = int(args[1])

        if not 0 <= value <= 10000:
            await message.reply(
                "⚠️ Echo must be between 0 and 10000."
            )
            return

        current_echo = value

        if value == 0:
            echo_buffer.fill(0)

        await message.reply(
            f"🔁 Echo updated: `{value}/10000`."
        )

    except ValueError:
        await message.reply(
            "❌ Enter a valid number."
        )


# ================= GAIN =================

@app.on_message(
    filters.command("gain", prefixes=".") & sudo_filter
)
async def set_gain(client: Client, message: Message):

    global current_gain

    args = (message.text or "").split()

    if len(args) < 2:
        await message.reply(
            f"🎛 Gain: `{current_gain}/2000`\n"
            "Usage: `.gain <0-2000>`"
        )
        return

    try:

        value = int(args[1])

        if not 0 <= value <= 2000:
            await message.reply(
                "⚠️ Gain must be between 0 and 2000."
            )
            return

        current_gain = value

        await message.reply(
            f"🎛 Gain updated: `{value}/2000`."
        )

    except ValueError:
        await message.reply(
            "❌ Enter a valid number."
        )


# ================= BASS =================

@app.on_message(
    filters.command("bass", prefixes=".") & sudo_filter
)
async def set_bass(client: Client, message: Message):

    global current_bass
    global bass_filter_state

    args = (message.text or "").split()

    if len(args) < 2:
        await message.reply(
            f"💥 Bass: `{current_bass}/1500`\n"
            "Usage: `.bass <0-1500>`"
        )
        return

    try:

        value = int(args[1])

        if not 0 <= value <= 1500:
            await message.reply(
                "⚠️ Bass must be between 0 and 1500."
            )
            return

        current_bass = value
        bass_filter_state.fill(0)

        await message.reply(
            f"💥 Bass updated: `{value}/1500`."
        )

    except ValueError:
        await message.reply(
            "❌ Enter a valid number."
        )


# ================= DOUBLE VOICE =================

@app.on_message(
    filters.command("double", prefixes=".") & sudo_filter
)
async def set_double(client: Client, message: Message):

    global current_double
    global double_buffer
    global double_position

    args = (message.text or "").split()

    if len(args) < 2 or args[1].lower() not in ("on", "off"):

        status = "ON" if current_double else "OFF"

        await message.reply(
            f"🎙 Double Voice: `{status}`\n"
            "Usage: `.double on` or `.double off`"
        )
        return

    current_double = args[1].lower() == "on"

    double_buffer.fill(0)
    double_position = 0

    await message.reply(
        "🎙 Double Voice "
        + ("ENABLED." if current_double else "DISABLED.")
    )


# ================= LEAVEVC =================

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
            await message.reply(
                "⚠️ No active bridge."
            )
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

                errors.append(
                    f"{chat_id}: {e}"
                )

                logger.warning(
                    "Could not leave group %s: %s",
                    chat_id,
                    e,
                )

        current_logger_chat = None
        current_target_chat = None

        reset_audio_buffers()

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

    logger.info(
        "Starting Telegram Fight Voice Chat Bot..."
    )

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
            logger.exception(
                "Error stopping PyTgCalls"
            )

        try:

            if app.is_connected:
                await app.stop()

        except Exception:
            logger.exception(
                "Error stopping Pyrogram"
            )


# ================= ENTRY POINT =================

if __name__ == "__main__":

    try:

        loop.run_until_complete(main())

    except KeyboardInterrupt:

        logger.info("Bot stopped.")

    except Exception:

        logger.exception(
            "Fatal startup error."
        )

    finally:

        if not loop.is_closed():
            loop.close()
