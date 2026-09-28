import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import User
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import (
    TG_API_ID, TG_API_HASH, TG_PHONE, SESSION_NAME,
    BOT_TOKEN, ADMIN_ID, TARGET_CHAT_IDS,
    MAX_DAILY_REPLIES_PER_CHAT, MIN_HOURS_BETWEEN_REPLIES, TYPING_DELAY_SECONDS
)
from db import init_db, is_already_processed, save_candidate, update_status, can_send_reply
from ai_engine import has_trigger_keywords, evaluate_and_generate_reply

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("pvz_assistant")

# Initialize Telethon (Userbot)
telethon_client = TelegramClient(SESSION_NAME, TG_API_ID, TG_API_HASH)

# Initialize Aiogram (Control Bot)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Memory state for custom reply editing: admin_id -> (chat_id, msg_id)
waiting_custom_reply = {}

def get_control_keyboard(chat_id: int, msg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Отправить в чат", callback_data=f"send:{chat_id}:{msg_id}"),
            InlineKeyboardButton(text="✏️ Свой текст", callback_data=f"edit:{chat_id}:{msg_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Пропустить", callback_data=f"skip:{chat_id}:{msg_id}")
        ]
    ])

# ----------------- Aiogram Handlers (Control Bot) -----------------

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "👋 **Пульт управления партизанским ассистентом ПВЗ активен!**\n\n"
        "Я буду присылать сюда найденные в чатах вопросы по смене, зарплате и учету с готовым вариантом ответа от ИИ.\n"
        "Отправка в чат происходит только по вашему подтверждению!",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("send:"))
async def on_send_callback(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Доступ запрещен", show_alert=True)
        return

    _, chat_id_str, msg_id_str = call.data.split(":")
    chat_id = int(chat_id_str)
    msg_id = int(msg_id_str)

    # Check daily limits before actual sending
    if not can_send_reply(chat_id, MAX_DAILY_REPLIES_PER_CHAT, MIN_HOURS_BETWEEN_REPLIES):
        await call.answer("⚠️ Превышен дневной лимит или интервал между сообщениями в этот чат!", show_alert=True)
        return

    # Extract proposed reply from the message text or DB
    card_text = call.message.text
    separator = "🤖 Предложенный ответ ИИ:\n"
    if separator in card_text:
        reply_text = card_text.split(separator)[-1].strip()
    else:
        reply_text = card_text

    await call.answer("Отправляю...")
    await call.message.edit_reply_markup(reply_markup=None)

    try:
        # Simulate typing in the target chat
        async with telethon_client.action(chat_id, 'typing'):
            await asyncio.sleep(TYPING_DELAY_SECONDS)

        # Send reply from user's personal Telegram account
        await telethon_client.send_message(
            entity=chat_id,
            message=reply_text,
            reply_to=msg_id
        )

        update_status(chat_id, msg_id, status="sent", final_reply=reply_text)
        await call.message.reply(f"✅ **Успешно отправлено от вашего имени в чат!**\n\n_{reply_text}_", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        await call.message.reply(f"❌ Ошибка отправки: {e}")

@dp.callback_query(F.data.startswith("skip:"))
async def on_skip_callback(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    _, chat_id_str, msg_id_str = call.data.split(":")
    chat_id = int(chat_id_str)
    msg_id = int(msg_id_str)

    update_status(chat_id, msg_id, status="skipped")
    await call.answer("Пропущено")
    await call.message.edit_text(f"{call.message.text}\n\n*— Пропущено владельцем ❌*", parse_mode="Markdown")

@dp.callback_query(F.data.startswith("edit:"))
async def on_edit_callback(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    _, chat_id_str, msg_id_str = call.data.split(":")
    chat_id = int(chat_id_str)
    msg_id = int(msg_id_str)

    waiting_custom_reply[call.from_user.id] = (chat_id, msg_id, call.message.message_id)
    await call.answer("Жду ваш текст")
    await call.message.reply("✍️ **Отправьте в ответ сообщением ваш текст**, который хотите отправить в чат от своего имени:")

@dp.message()
async def on_admin_text_message(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    if message.from_user.id in waiting_custom_reply:
        chat_id, msg_id, orig_bot_msg_id = waiting_custom_reply.pop(message.from_user.id)
        custom_text = message.text.strip()

        try:
            # Simulate typing
            async with telethon_client.action(chat_id, 'typing'):
                await asyncio.sleep(TYPING_DELAY_SECONDS)

            # Send custom reply
            await telethon_client.send_message(
                entity=chat_id,
                message=custom_text,
                reply_to=msg_id
            )

            update_status(chat_id, msg_id, status="sent", final_reply=custom_text)
            await message.reply(f"✅ **Ваш текст отправлен в чат от вашего имени!**\n\n_{custom_text}_", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send custom message: {e}")
            await message.reply(f"❌ Ошибка отправки: {e}")

# ----------------- Telethon Listener (Userbot) -----------------

@telethon_client.on(events.NewMessage(chats=TARGET_CHAT_IDS))
async def handle_target_chat_message(event):
    # Ignore own outgoing messages
    if event.out:
        return

    sender = await event.get_sender()
    if isinstance(sender, User) and sender.bot:
        return

    text = event.raw_text or ""
    if len(text.strip()) < 15:
        return

    chat_id = event.chat_id
    msg_id = event.id

    if is_already_processed(chat_id, msg_id):
        return

    # 1. Fast regex pre-filter
    if not has_trigger_keywords(text):
        return

    author_name = "Участник"
    if sender:
        author_name = getattr(sender, "first_name", "") or getattr(sender, "title", "Участник")
        if getattr(sender, "username", None):
            author_name += f" (@{sender.username})"

    chat = await event.get_chat()
    chat_title = getattr(chat, "title", f"Чат {chat_id}")

    logger.info(f"Trigger matched in '{chat_title}' from '{author_name}': {text[:60]}...")

    # 2. Deep evaluation via OpenRouter AI
    ai_result = await evaluate_and_generate_reply(text, author_name)
    if not ai_result.get("should_reply"):
        logger.info(f"AI decided NOT to reply: {ai_result.get('reason')}")
        return

    proposed_reply = ai_result.get("proposed_reply", "")
    reason = ai_result.get("reason", "")

    # Save candidate to DB
    save_candidate(chat_id, msg_id, author_name, text, proposed_reply)

    # Format notification message for admin
    msg_link = f"https://t.me/c/{str(chat_id).replace('-100', '')}/{msg_id}"
    notification_text = (
        f"🔔 **Новый вопрос в чате: {chat_title}**\n\n"
        f"👤 **Автор:** {author_name}\n"
        f"❓ **Вопрос:**\n\"{text}\"\n\n"
        f"💡 **Почему стоит ответить:** _{reason}_\n\n"
        f"🔗 [Перейти к сообщению]({msg_link})\n\n"
        f"🤖 **Предложенный ответ ИИ:**\n{proposed_reply}"
    )

    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=notification_text,
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=get_control_keyboard(chat_id, msg_id)
        )
    except Exception as e:
        logger.error(f"Failed to send notification to admin: {e}")

# ----------------- Service Entrypoint -----------------

async def start_services():
    init_db()
    logger.info("Database initialized.")

    logger.info("Connecting Telethon client...")
    await telethon_client.start(phone=TG_PHONE)
    me = await telethon_client.get_me()
    logger.info(f"Userbot logged in as: {me.first_name} (@{me.username}) [ID: {me.id}]")

    logger.info("Starting Aiogram control bot...")
    await asyncio.gather(
        dp.start_polling(bot),
        telethon_client.run_until_disconnected()
    )

if __name__ == "__main__":
    try:
        asyncio.run(start_services())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down assistant.")
