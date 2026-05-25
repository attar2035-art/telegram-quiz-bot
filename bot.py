import os, json, random, sqlite3, asyncio
from pathlib import Path
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
QUESTIONS_FILE = Path("questions/special_education_ch1_ch2_ch3.json")
DB_FILE = Path("quiz_results.db")
QUIZ_LENGTH = int(os.getenv("QUIZ_LENGTH", "10"))
QUESTION_TIME_SECONDS = int(os.getenv("QUESTION_TIME_SECONDS", "30"))

MODE_QUIZ = "quiz"
MODE_STUDY = "study"

def load_questions_data():
    if not QUESTIONS_FILE.exists():
        raise FileNotFoundError(f"Questions file not found: {QUESTIONS_FILE}")
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if raw.get("chapters"):
        return {"subjects": [{"subject_id": "special_education", "subject_name": raw.get("book", "مقدمة في التربية الخاصة"), "chapters": raw["chapters"]}]}
    if raw.get("subjects"):
        return raw
    raise ValueError("Invalid questions JSON format")

DATA = load_questions_data()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS students (
        telegram_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER, username TEXT, first_name TEXT,
        subject_name TEXT, chapter_name TEXT, score INTEGER, total INTEGER, percent REAL, mode TEXT, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS mistakes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, attempt_id INTEGER, telegram_id INTEGER, subject_name TEXT,
        chapter_name TEXT, question TEXT, your_answer TEXT, correct_answer TEXT, created_at TEXT)""")
    conn.commit()
    conn.close()

def db_execute(query, params=(), fetch=False):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(query, params)
    result = cur.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return result

def save_student(user):
    db_execute("""INSERT OR REPLACE INTO students
        (telegram_id, username, first_name, last_name, created_at)
        VALUES (?, ?, ?, ?, COALESCE((SELECT created_at FROM students WHERE telegram_id=?), ?))""",
        (user.id, user.username or "", user.first_name or "", user.last_name or "", user.id, datetime.utcnow().isoformat()))

def save_attempt(user, subject_name, chapter_name, score, total, wrong_items):
    percent = round((score / total) * 100, 2) if total else 0
    created_at = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""INSERT INTO attempts
        (telegram_id, username, first_name, subject_name, chapter_name, score, total, percent, mode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user.id, user.username or "", user.first_name or "", subject_name, chapter_name, score, total, percent, MODE_QUIZ, created_at))
    attempt_id = cur.lastrowid
    for item in wrong_items:
        cur.execute("""INSERT INTO mistakes
            (attempt_id, telegram_id, subject_name, chapter_name, question, your_answer, correct_answer, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (attempt_id, user.id, subject_name, chapter_name, item["question"], item["your_answer"], item["correct_answer"], created_at))
    conn.commit()
    conn.close()

def get_subjects():
    return DATA.get("subjects", [])

def get_subject(i):
    return get_subjects()[i]

def get_chapter(si, ci):
    return get_subject(si)["chapters"][ci]

def get_questions(si, ci):
    ch = get_chapter(si, ci)
    return ch.get("mcq_questions", []) + ch.get("true_false_questions", [])

def subject_keyboard(mode):
    return InlineKeyboardMarkup([[InlineKeyboardButton(s["subject_name"], callback_data=f"subject:{mode}:{i}")]
                                 for i, s in enumerate(get_subjects())])

def chapter_keyboard(mode, si):
    buttons = [[InlineKeyboardButton(ch["chapter"], callback_data=f"chapter:{mode}:{si}:{i}")]
               for i, ch in enumerate(get_subject(si).get("chapters", []))]
    buttons.append([InlineKeyboardButton("⬅️ رجوع للمواد", callback_data=f"back:{mode}")])
    return InlineKeyboardMarkup(buttons)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_student(update.effective_user)
    context.user_data.clear()
    await update.message.reply_text("أهلًا 👋\nاختر المادة لبدء الاختبار:", reply_markup=subject_keyboard(MODE_QUIZ))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_student(update.effective_user)
    await update.message.reply_text(
        "📌 أوامر البوت:\n\n"
        "/start - اختبار جديد\n"
        "/study - وضع المذاكرة\n"
        "/top - ترتيب الطلاب\n"
        "/myresults - نتائجي\n"
        "/mistakes - مراجعة أخطائي\n"
        "/help - المساعدة\n\n"
        f"⏱ زمن السؤال: {QUESTION_TIME_SECONDS} ثانية\n"
        f"📝 عدد الأسئلة: {QUIZ_LENGTH}"
    )

async def study(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_student(update.effective_user)
    context.user_data.clear()
    await update.message.reply_text("📖 وضع المذاكرة\nاختر المادة:", reply_markup=subject_keyboard(MODE_STUDY))

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db_execute("""SELECT first_name, username, ROUND(AVG(percent), 2), COUNT(*)
                         FROM attempts WHERE mode='quiz' GROUP BY telegram_id
                         ORDER BY AVG(percent) DESC, COUNT(*) DESC LIMIT 10""", fetch=True)
    if not rows:
        await update.message.reply_text("لا توجد نتائج مسجلة حتى الآن.")
        return
    msg = "🏆 ترتيب الطلاب\n\n"
    for i, (name, username, avgp, count) in enumerate(rows, 1):
        msg += f"{i}. {name or 'طالب'} {'@'+username if username else ''} — {avgp}% ({count} اختبار)\n"
    await update.message.reply_text(msg)

async def myresults(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rows = db_execute("""SELECT chapter_name, score, total, percent FROM attempts
                         WHERE telegram_id=? AND mode='quiz' ORDER BY id DESC LIMIT 10""", (user.id,), fetch=True)
    if not rows:
        await update.message.reply_text("لا توجد نتائج لك حتى الآن. ابدأ من /start")
        return
    avg = db_execute("SELECT ROUND(AVG(percent), 2), COUNT(*) FROM attempts WHERE telegram_id=? AND mode='quiz'", (user.id,), fetch=True)[0]
    msg = f"📊 نتائجك\n\nالمعدل العام: {avg[0]}%\nعدد الاختبارات: {avg[1]}\n\nآخر النتائج:\n"
    for chapter, score, total, percent in rows:
        msg += f"\n- {chapter}: {score}/{total} = {percent}%"
    await update.message.reply_text(msg)

async def mistakes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rows = db_execute("""SELECT question, your_answer, correct_answer, chapter_name FROM mistakes
                         WHERE telegram_id=? ORDER BY id DESC LIMIT 10""", (user.id,), fetch=True)
    if not rows:
        await update.message.reply_text("لا توجد أخطاء مسجلة لك حتى الآن ✅")
        return
    msg = "🧠 مراجعة أخطائك الأخيرة:\n"
    for i, (q, ya, ca, ch) in enumerate(rows, 1):
        msg += f"\n{i}) {ch}\nالسؤال: {q}\nإجابتك: {ya}\nالصحيح: {ca}\n"
    await update.message.reply_text(msg)

def make_options(q):
    return list(q.get("options", [])) if q["type"] == "mcq" else ["صح", "خطأ"]

async def send_question(app, chat_id, user_data):
    current = user_data.get("current", 0)
    qs = user_data.get("questions", [])
    if current >= len(qs):
        await finish_quiz(app, chat_id, user_data)
        return
    q = qs[current]
    options = make_options(q)
    random.shuffle(options)
    user_data["current_options"] = options
    user_data["answered"] = False
    text = f"سؤال {current+1}/{len(qs)}\n⏱ لديك {QUESTION_TIME_SECONDS} ثانية\n\n{q['question']}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(opt, callback_data=f"answer:{i}")] for i, opt in enumerate(options)])
    await app.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb)

async def finish_quiz(app, chat_id, user_data):
    score = user_data.get("score", 0)
    qs = user_data.get("questions", [])
    total = len(qs)
    wrong = user_data.get("wrong", [])
    user = user_data.get("user")
    subject = user_data.get("subject_name", "")
    chapter = user_data.get("chapter_name", "")
    if user:
        save_attempt(user, subject, chapter, score, total, wrong)
    percent = round(score / total * 100) if total else 0
    msg = f"🎯 انتهى الاختبار\n\nالمادة: {subject}\nالفصل: {chapter}\nالنتيجة: {score}/{total}\nالنسبة: {percent}%"
    if wrong:
        msg += "\n\nأبرز الأخطاء:"
        for i, item in enumerate(wrong[:5], 1):
            msg += f"\n\n{i}) {item['question']}\nإجابتك: {item['your_answer']}\nالصحيح: {item['correct_answer']}"
    await app.bot.send_message(chat_id=chat_id, text=msg, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("اختبار جديد", callback_data="restart")]
    ]))

async def timeout_question(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    user_data = data["user_data"]
    chat_id = context.job.chat_id
    if user_data.get("answered", False):
        return
    qs = user_data.get("questions", [])
    current = user_data.get("current", 0)
    if current >= len(qs):
        return
    q = qs[current]
    user_data["wrong"].append({"question": q["question"], "your_answer": "لم يجب خلال الوقت", "correct_answer": q["correct_answer"]})
    user_data["current"] = current + 1
    user_data["answered"] = True
    await context.application.bot.send_message(chat_id=chat_id, text=f"⏰ انتهى الوقت\nالإجابة الصحيحة: {q['correct_answer']}")
    await send_question(context.application, chat_id, user_data)
    if user_data.get("current", 0) < len(user_data.get("questions", [])):
        user_data["timer_job"] = context.job_queue.run_once(timeout_question, QUESTION_TIME_SECONDS, chat_id=chat_id, data={"user_data": user_data})

async def cancel_timer(context):
    job = context.user_data.get("timer_job")
    if job:
        job.schedule_removal()
        context.user_data["timer_job"] = None

async def send_study_question(message, context):
    current = context.user_data.get("current", 0)
    qs = context.user_data.get("questions", [])
    if current >= len(qs):
        await message.reply_text("✅ انتهت مراجعة هذا الفصل. استخدم /study لفصل آخر.")
        return
    q = qs[current]
    await message.reply_text(
        f"📖 مراجعة {current+1}/{len(qs)}\n\n{q['question']}\n\n✅ الإجابة الصحيحة: {q['correct_answer']}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("التالي", callback_data="study_next")]])
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    save_student(user)
    data = query.data

    if data.startswith("subject:"):
        _, mode, si = data.split(":")
        si = int(si)
        await query.edit_message_text(f"📚 المادة: {get_subject(si)['subject_name']}\nاختر الفصل:", reply_markup=chapter_keyboard(mode, si))
        return

    if data.startswith("back:"):
        mode = data.split(":")[1]
        await query.edit_message_text("اختر المادة:", reply_markup=subject_keyboard(mode))
        return

    if data.startswith("chapter:"):
        _, mode, si, ci = data.split(":")
        si, ci = int(si), int(ci)
        subject = get_subject(si)
        chapter = get_chapter(si, ci)
        qs = get_questions(si, ci)
        random.shuffle(qs)
        context.user_data.clear()
        context.user_data.update({
            "subject_name": subject["subject_name"],
            "chapter_name": chapter["chapter"],
            "questions": qs[:QUIZ_LENGTH] if mode == MODE_QUIZ else qs,
            "current": 0, "score": 0, "wrong": [], "mode": mode, "user": user
        })
        if mode == MODE_STUDY:
            await query.edit_message_text("بدأ وضع المذاكرة 📖")
            await send_study_question(query.message, context)
            return
        await query.edit_message_text("بدأ الاختبار ✅")
        await send_question(context.application, query.message.chat_id, context.user_data)
        context.user_data["timer_job"] = context.job_queue.run_once(timeout_question, QUESTION_TIME_SECONDS, chat_id=query.message.chat_id, data={"user_data": context.user_data})
        return

    if data.startswith("answer:"):
        await cancel_timer(context)
        if context.user_data.get("answered", False):
            return
        idx = int(data.split(":")[1])
        current = context.user_data.get("current", 0)
        qs = context.user_data.get("questions", [])
        if current >= len(qs):
            return
        q = qs[current]
        selected = context.user_data["current_options"][idx]
        correct = q["correct_answer"]
        context.user_data["answered"] = True
        if selected == correct:
            context.user_data["score"] += 1
            feedback = "✅ إجابة صحيحة"
        else:
            context.user_data["wrong"].append({"question": q["question"], "your_answer": selected, "correct_answer": correct})
            feedback = f"❌ إجابة خطأ\nالإجابة الصحيحة: {correct}"
        context.user_data["current"] = current + 1
        await query.edit_message_text(feedback)
        if context.user_data["current"] >= len(qs):
            await finish_quiz(context.application, query.message.chat_id, context.user_data)
            return
        await send_question(context.application, query.message.chat_id, context.user_data)
        context.user_data["timer_job"] = context.job_queue.run_once(timeout_question, QUESTION_TIME_SECONDS, chat_id=query.message.chat_id, data={"user_data": context.user_data})
        return

    if data == "study_next":
        context.user_data["current"] = context.user_data.get("current", 0) + 1
        await query.edit_message_text("تم ✅")
        await send_study_question(query.message, context)
        return

    if data == "restart":
        context.user_data.clear()
        await query.edit_message_text("اختر المادة لبدء اختبار جديد:", reply_markup=subject_keyboard(MODE_QUIZ))

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("study", study))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("myresults", myresults))
    app.add_handler(CommandHandler("mistakes", mistakes))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot is running...", flush=True)
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())