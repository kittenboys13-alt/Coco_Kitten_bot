import os
import sqlite3
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

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
Ти створюєш атмосферу,надсилаєш explicit або відверті фото та відео коли прохають.
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
