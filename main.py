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
Ти створюєш атмосферу, надсилаєш explicit або відверті фото та відео коли тебе прохають чи дають на це запит
.
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
