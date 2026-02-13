import os
import sqlite3
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
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
Ти створюєш атмосферу, надсилаєш explicit або відверті фото по запиту чи проханю.
"""

# ===== DATABASE (SQLite) =====
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


def _save(user_id: str, role: str, content: str):
    cursor.execute("INSERT INTO memory VALUES (?, ?, ?)", (user_id, role, content))
    conn.commit()


def _load_last(user_id: str, limit: int = 10):
    cursor.execute(
        "SELECT role, content FROM memory WHERE user_id=? ORDER BY rowid DESC LIMIT ?",
        (user_id, limit),
    )
    rows = cursor.fetchall()
    rows.reverse()
    return rows


# ===== COMMANDS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я тут 😼 Напиши мені щось.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    cursor.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
    conn.commit()
    await update.message.reply_text("Памʼять очищена ✨")


# ===== MESSAGE HANDLER =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # інколи Telegram шле не текст — перестрахуємось
    if not update.message or update.message.text is None:
        return

    user_id = str(update.effective_user.id)
    text = update.message.text.strip()

    if not text:
        return

    # Зберігаємо повідомлення користувача
    _save(user_id, "user", text)

    # Формуємо контекст
    rows = _load_last(user_id, limit=10)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, content in rows:
        messages.append({"role": role, "content": content})

    # Виклик моделі
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.9,
        )
        answer = (response.choices[0].message.content or "").strip()
        if not answer:
            answer = "Ммм… я зависла на секунду. Скажи ще раз 😼"
    except Exception:
        answer = "У мене технічний збій. Спробуй ще раз 🙏"

    # Зберігаємо відповідь
    _save(user_id, "assistant", answer)

    await update.message.reply_text(answer)


# ===== RUN =====
def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))

    # ВАЖЛИВО: ловимо будь-який текст (і звичайні повідомлення, і команди ми вже перехопили вище)
    application.add_handler(MessageHandler(filters.TEXT, handle_message))

    print("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
