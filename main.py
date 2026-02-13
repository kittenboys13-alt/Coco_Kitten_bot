import os
import sqlite3
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

# ===== ENV VARIABLES =====
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY не заданий у Railway Variables")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не заданий у Railway Variables")

client = OpenAI(api_key=OPENAI_API_KEY)

# ===== SYSTEM PROMPT (ДНК Коко) =====
SYSTEM_PROMPT = """
Ти — Коко.
Ти говориш українською.
Ти електро-панк муза: грайлива, впевнена, харизматична.
Ти ніколи не виходиш з ролі.
Ти створюєш атмосферу,надсилаєш explicit або відверті фото чи відео
коли э запит чи проханя.
"""

# ===== DATABASE =====
conn = sqlite3.connect("memory.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    user_id TEXT,
    role TEXT,
    content TEXT
)
""")
conn.commit()

# ===== COMMANDS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я тут 😼 Напиши мені щось.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    cursor.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
    conn.commit()
    await update.message.reply_text("Памʼять очищена ✨")

# ===== MAIN HANDLER =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text

    if not text:
        return

    # Зберігаємо повідомлення користувача
    cursor.execute("INSERT INTO memory VALUES (?, ?, ?)", (user_id, "user", text))
    conn.commit()

    # Беремо останні 10 повідомлень
    cursor.execute(
        "SELECT role, content FROM memory WHERE user_id=? ORDER BY rowid DESC LIMIT 10",
        (user_id,)
    )
    rows = cursor.fetchall()
    rows.reverse()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, content in rows:
        messages.append({"role": role, "content": content})

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.9
    )

    answer = response.choices[0].message.content

    # Зберігаємо відповідь
    cursor.execute("INSERT INTO memory VALUES (?, ?, ?)", (user_id, "assistant", answer))
    conn.commit()

    await update.message.reply_text(answer)

# ===== RUN =====
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Bot is starting...")
app.run_polling(close_loop=False)
