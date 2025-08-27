import os
import sqlite3
import asyncio
from uuid import uuid4
from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler, ContextTypes
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

DB_PATH = "db.sqlite3"

# --- База данных ---
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        user_id INTEGER UNIQUE,
        code TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_id INTEGER,
        to_id INTEGER,
        question TEXT,
        message_id INTEGER
    )""")
    conn.commit()
    conn.close()

def get_or_create_user(user_id: int):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row is None:
        code = str(uuid4().hex[:8])
        c.execute("INSERT INTO users (user_id, code) VALUES (?,?)", (user_id, code))
        conn.commit()
        conn.close()
        return user_id, code
    else:
        conn.close()
        return row[1], row[2]

def get_user_by_code(code: str):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE code=?", (code,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def save_question(from_id, to_id, question, message_id):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT INTO questions (from_id,to_id,question,message_id) VALUES (?,?,?,?)",
              (from_id, to_id, question, message_id))
    conn.commit()
    conn.close()

def get_question_by_message(to_id, message_id):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT id,from_id,question FROM questions WHERE to_id=? AND message_id=?",
              (to_id, message_id))
    row = c.fetchone()
    conn.close()
    return row

# --- Хендлеры ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, code = get_or_create_user(update.effective_user.id)
    if update.effective_user.id == ADMIN_ID:
        keyboard = [["Получить ссылку"], ["Админ-панель"]]
    else:
        keyboard = [["Получить ссылку"]]
    await update.message.reply_text(
        "👋 Привет! Это анонимный бот вопросов.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_start_with_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) > 0 and args[0].startswith("ask_"):
        code = args[0][4:]
        to_id = get_user_by_code(code)
        if to_id:
            context.user_data["asking_to"] = to_id
            await update.message.reply_text("✍️ Напиши свой анонимный вопрос этому пользователю.")
        else:
            await update.message.reply_text("❌ Неверная ссылка.")
    else:
        await start(update, context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # --- Админ кнопки ---
    if user_id == ADMIN_ID:
        if text == "Админ-панель":
            await show_admin_panel(update, context)
            return

    # --- Получить ссылку ---
    if text == "Получить ссылку":
        _, code = get_or_create_user(user_id)
        bot_username = (await context.bot.get_me()).username
        await update.message.reply_text(
            f"🔗 Твоя ссылка:
https://t.me/{bot_username}?start=ask_{code}"
        )
        return

    # --- Проверка на вопрос ---
    if "asking_to" in context.user_data:
        to_id = context.user_data.pop("asking_to")
        question = text
        sent = await context.bot.send_message(
            chat_id=to_id,
            text=f"❓ Анонимный вопрос:

{question}

_Свайпни для ответа_",
            parse_mode="Markdown"
        )
        save_question(user_id, to_id, question, sent.message_id)
        await update.message.reply_text("✅ Вопрос отправлен анонимно!")
        return

    # --- Проверка на ответ через reply ---
    if update.message.reply_to_message:
        replied_id = update.message.reply_to_message.message_id
        q = get_question_by_message(user_id, replied_id)
        if q:
            qid, from_id, question = q
            answer = text
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("❓ Задать ещё вопрос", callback_data=f"askmore_{user_id}")]]
            )
            await context.bot.send_message(
                chat_id=from_id,
                text=f"📩 На ваш вопрос:
{question}

💬 Ответ:
{answer}",
                reply_markup=keyboard
            )
            await update.message.reply_text("✅ Ответ отправлен анонимно!")
            return

# --- Callback ---
async def ask_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    to_id = int(query.data.split("_")[1])
    context.user_data["asking_to"] = to_id
    await query.message.reply_text("✍️ Напиши ещё один анонимный вопрос этому пользователю.")

# --- Админка ---
async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Пользователи", callback_data="users")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="broadcast")]
    ]
    await update.message.reply_text("⚙️ Админ-панель", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "users":
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total = c.fetchone()[0]
        conn.close()
        await query.message.reply_text(f"👥 Всего пользователей: {total}")
    elif query.data == "broadcast":
        context.user_data["broadcast"] = True
        await update.message.reply_text("📢 Введите текст рассылки:")

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("broadcast") and update.effective_user.id == ADMIN_ID:
        text = update.message.text
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = [row[0] for row in c.fetchall()]
        conn.close()
        sent_count = 0
        for uid in users:
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 {text}")
                sent_count += 1
                await asyncio.sleep(0.1)
            except:
                pass
        context.user_data["broadcast"] = False
        await update.message.reply_text(f"✅ Рассылка отправлена {sent_count} пользователям.")

# --- Запуск ---
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_start_with_code))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(ask_more, pattern="^askmore_"))
    app.add_handler(CallbackQueryHandler(admin_callbacks))
    app.run_polling()

if __name__ == "__main__":
    main()
