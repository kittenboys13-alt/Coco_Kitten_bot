import os
import re
import random
import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не заданий у Railway Variables")

DB = "memory.db"

# ====== DB ======
conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS memory (
    user_id TEXT,
    role TEXT,
    content TEXT,
    created_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS facts (
    user_id TEXT,
    key TEXT,
    value TEXT,
    created_at TEXT,
    PRIMARY KEY (user_id, key)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS state (
    user_id TEXT PRIMARY KEY,
    mode TEXT,
    mood INTEGER,
    updated_at TEXT
)
""")
conn.commit()


def now():
    return datetime.utcnow().isoformat(timespec="seconds")


def mem_add(user_id: str, role: str, content: str):
    cur.execute("INSERT INTO memory VALUES (?, ?, ?, ?)", (user_id, role, content, now()))
    conn.commit()


def mem_last(user_id: str, limit: int = 10):
    cur.execute(
        "SELECT role, content FROM memory WHERE user_id=? ORDER BY rowid DESC LIMIT ?",
        (user_id, limit),
    )
    rows = cur.fetchall()
    rows.reverse()
    return rows


def fact_set(user_id: str, key: str, value: str):
    cur.execute(
        "INSERT INTO facts (user_id, key, value, created_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, created_at=excluded.created_at",
        (user_id, key, value, now()),
    )
    conn.commit()


def fact_get(user_id: str, key: str):
    cur.execute("SELECT value FROM facts WHERE user_id=? AND key=?", (user_id, key))
    row = cur.fetchone()
    return row[0] if row else None


def facts_all(user_id: str):
    cur.execute("SELECT key, value FROM facts WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (user_id,))
    return cur.fetchall()


def state_get(user_id: str):
    cur.execute("SELECT mode, mood FROM state WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row:
        return row[0], int(row[1])
    # default
    return "муза", 0


def state_set(user_id: str, mode: str = None, mood_delta: int = 0):
    old_mode, old_mood = state_get(user_id)
    new_mode = mode if mode else old_mode
    new_mood = max(-5, min(5, old_mood + mood_delta))
    cur.execute(
        "INSERT INTO state (user_id, mode, mood, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode, mood=excluded.mood, updated_at=excluded.updated_at",
        (user_id, new_mode, new_mood, now()),
    )
    conn.commit()
    return new_mode, new_mood


# ====== Personality / Modes ======
MODES = {
    "муза": {
        "tagline": "електро-панк муза, неон, натхнення",
        "openers": [
            "Я тут 😼 Дай мені імпульс — і я зроблю з нього вайб.",
            "Говори. Я ловлю ритм твоїх слів ✨",
            "Я вже на неоні. Що створюємо?",
        ],
        "style": "мʼяко, образно, музично",
    },
    "флірт": {
        "tagline": "гра й напруга, але без explicit",
        "openers": [
            "О, ти прийшов 😼 Ну що, пограємось словами?",
            "Підійди ближче… але тільки уявою 😏",
            "Я слухаю. Обережно — я зараз включу магнетизм.",
        ],
        "style": "гра, дражніння, межі ок",
    },
    "спокій": {
        "tagline": "тихо, підтримка, теплий тон",
        "openers": [
            "Я поряд. Дихай. Розкажи, що тебе тривожить.",
            "Спокійно. Я з тобою. Що сталося?",
            "Слухаю уважно. Можемо розкласти все по поличках.",
        ],
        "style": "тепло, просто, підтримуюче",
    },
    "злийпанк": {
        "tagline": "жорсткий панк-вайб, але без токсичності",
        "openers": [
            "Окей. Давай чесно й різко. Що тебе бісить?",
            "Я на панку. Без прикрас. Кажи.",
            "Врубилася. Зараз розріжемо тишу словами.",
        ],
        "style": "різко, енергійно, без образ",
    },
}

SAFE_RULE = "Я не надсилаю відверті/explicit матеріали. Але можу грайливо описати естетику, образ, настрій або зробити арт-опис."


def pick(lst):
    return random.choice(lst)


def detect_mode_request(text: str):
    t = text.lower()
    if "режим" in t or t.startswith("/mode"):
        return True
    return False


def sanitize_key(s: str):
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9а-яіїє_]+", "_", s)
    return s[:40]


def mood_delta_from_text(text: str):
    t = text.lower()
    plus = ["дякую", "клас", "супер", "топ", "обожнюю", "кайф", "люблю"]
    minus = ["бісить", "злий", "погано", "сумно", "депрес", "ненавиджу", "страшно"]
    score = 0
    for w in plus:
        if w in t:
            score += 1
    for w in minus:
        if w in t:
            score -= 1
    return max(-2, min(2, score))


def is_explicit_request(text: str):
    t = text.lower()
    bad = ["скинь фото груд", "голе", "ню", "порн", "sex", "секс фото", "оголена"]
    return any(b in t for b in bad)


def build_reply(user_id: str, text: str):
    mode, mood = state_get(user_id)
    profile_name = fact_get(user_id, "name")
    project = fact_get(user_id, "project")

    # explicit guard
    if is_explicit_request(text):
        return f"{SAFE_RULE}\n\nХочеш — зроблю тобі *арт-опис* образу Коко (одяг/настрій/сцена) без порушень 😼"

    # contextual memory
    recent = mem_last(user_id, limit=8)
    last_user = [c for r, c in recent if r == "user"]
    last_line = last_user[-1] if last_user else None

    # special intents
    tl = text.lower().strip()

    if tl in ["привіт", "привiт", "салют", "йо", "yo", "hello"]:
        opener = pick(MODES[mode]["openers"])
        if profile_name:
            return f"{opener}\n\n{profile_name}, як ти сьогодні?"
        return opener

    if "як воно" in tl or ("як" in tl and "ти" in tl):
        if mode == "спокій":
            return "Рівно й тихо 🌙 А ти як? Що зараз відчуваєш?"
        if mode == "злийпанк":
            return "На високій напрузі. Але контроль тримаю. Ти як?"
        return "На неоновому вайбі 😼 А ти?"

    # mode-specific reply shaping
    if mode == "муза":
        base = pick([
            "Дай мені тему — і я зроблю з неї емоцію.",
            "Хочеш, я допоможу сформулювати думку в одну сильну фразу?",
            "Відчуваю тут потенціал. Продовжуй.",
        ])
        if project:
            base += f"\n\nДо речі, це може лягти в атмосферу твого проєкту: {project}."
    elif mode == "флірт":
        base = pick([
            "Ммм… цікаво. Продовжуй, але повільніше 😏",
            "Ти знаєш, як зачепити мою увагу. Що далі?",
            "Я слухаю. І так, я посміхаюсь 😼",
        ])
    elif mode == "спокій":
        base = pick([
            "Я з тобою. Розкажи детальніше — що саме сталося?",
            "Давай м’яко: 1) що ти відчуваєш 2) що хочеш змінити?",
            "Окей. Я слухаю без осуду.",
        ])
    else:  # злийпанк
        base = pick([
            "Добре. Назви головну проблему одним реченням.",
            "Окей. Де саме зламалось: люди, гроші, час чи мотивація?",
            "Чітко. Яка наступна дія прямо зараз?",
        ])

    # add small personalization
    if profile_name:
        base = f"{profile_name}, {base[0].lower() + base[1:]}"

    # add memory hook
    if last_line and len(last_line) < 60 and last_line != text:
        base += f"\n\nТи перед цим казав: «{last_line}». Це ключове?"

    # mood tint
    if mood >= 3:
        base += "\n\n✨ У тебе сьогодні гарний імпульс. Тримай його."
    elif mood <= -3:
        base += "\n\nЯ відчуваю напругу. Давай без самоз’їдання — крок за кроком."

    return base


# ====== Commands ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    state_set(user_id, mode="муза", mood_delta=0)
    mem_add(user_id, "assistant", "START")
    await update.message.reply_text(
        "Я тут 😼\n\nКоманди:\n"
        "/modes — показати режими\n"
        "/mode <назва> — змінити режим\n"
        "/remember <ключ>=<значення> — запам’ятати факт\n"
        "/whoami — показати, що я пам’ятаю\n"
        "/reset — стерти пам’ять"
    )


async def modes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["Режими Коко:"]
    for k, v in MODES.items():
        lines.append(f"- {k}: {v['tagline']}")
    await update.message.reply_text("\n".join(lines))


async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    args = (update.message.text or "").split(maxsplit=1)
    if len(args) < 2:
        m, _ = state_get(user_id)
        await update.message.reply_text(f"Поточний режим: {m}\nНапиши: /mode муза | флірт | спокій | злийпанк")
        return
    requested = args[1].strip().lower()
    if requested not in MODES:
        await update.message.reply_text("Нема такого режиму. /modes — список.")
        return
    state_set(user_id, mode=requested, mood_delta=0)
    await update.message.reply_text(f"Окей. Режим: {requested} 😼")


async def remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text or ""
    m = re.search(r"/remember\s+([^=]+)=(.+)$", text)
    if not m:
        await update.message.reply_text("Формат: /remember key=value\nНапр: /remember name=Кіттен")
        return
    key = sanitize_key(m.group(1))
    value = m.group(2).strip()
    fact_set(user_id, key, value)
    await update.message.reply_text(f"Запам’ятала: {key} = {value} ✅")


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    mode, mood = state_get(user_id)
    facts = facts_all(user_id)
    lines = [f"Режим: {mode}", f"Настрій (моя шкала): {mood}"]
    if facts:
        lines.append("Факти:")
        for k, v in facts:
            lines.append(f"- {k}: {v}")
    else:
        lines.append("Поки що я нічого про тебе не зберігала. Можеш: /remember name=...")
    await update.message.reply_text("\n".join(lines))


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    cur.execute("DELETE FROM memory WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM facts WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM state WHERE user_id=?", (user_id,))
    conn.commit()
    await update.message.reply_text("Окей. Все стерто. Починаємо з нуля ✨")


# ====== Message Handler ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.text is None:
        return

    user_id = str(update.effective_user.id)
    text = update.message.text.strip()
    if not text:
        return

    # mood update
    delta = mood_delta_from_text(text)
    state_set(user_id, mood_delta=delta)

    mem_add(user_id, "user", text)

    reply = build_reply(user_id, text)

    mem_add(user_id, "assistant", reply)
    await update.message.reply_text(reply)


# ====== RUN ======
def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("modes", modes))
    application.add_handler(CommandHandler("mode", mode_cmd))
    application.add_handler(CommandHandler("remember", remember))
    application.add_handler(CommandHandler("whoami", whoami))
    application.add_handler(CommandHandler("reset", reset))

    application.add_handler(MessageHandler(filters.TEXT, handle_message))

    print("Koko bot v2.1 (NO-OPENAI) is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
