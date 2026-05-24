import os
import json
import random
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
QUESTIONS_FILE = Path("questions/special_education_ch1_ch2_ch3.json")
QUIZ_LENGTH = 10


def load_data():
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


DATA = load_data()


def get_chapters():
    return DATA.get("chapters", [])


def build_chapter_keyboard():
    buttons = []
    for i, chapter in enumerate(get_chapters()):
        buttons.append([
            InlineKeyboardButton(chapter["chapter"], callback_data=f"chapter:{i}")
        ])
    return InlineKeyboardMarkup(buttons)


def get_questions_for_chapter(chapter_index):
    chapter = get_chapters()[chapter_index]
    questions = []
    questions.extend(chapter.get("mcq_questions", []))
    questions.extend(chapter.get("true_false_questions", []))
    return questions


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "أهلًا 👋\nاختر الفصل لبدء كويز تجريبي:",
        reply_markup=build_chapter_keyboard()
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("chapter:"):
        chapter_index = int(data.split(":")[1])
        questions = get_questions_for_chapter(chapter_index)
        random.shuffle(questions)

        selected_questions = questions[:QUIZ_LENGTH]

        context.user_data["chapter_index"] = chapter_index
        context.user_data["questions"] = selected_questions
        context.user_data["current"] = 0
        context.user_data["score"] = 0
        context.user_data["wrong"] = []

        await query.edit_message_text("بدأ الاختبار ✅")
        await send_question(query, context)
        return

    if data.startswith("answer:"):
        selected_index = int(data.split(":")[1])
        current = context.user_data.get("current", 0)
        questions = context.user_data.get("questions", [])

        if current >= len(questions):
            return

        q = questions[current]
        correct_answer = q["correct_answer"]
        selected_answer = context.user_data["current_options"][selected_index]

        if selected_answer == correct_answer:
            context.user_data["score"] += 1
            feedback = "✅ إجابة صحيحة"
        else:
            context.user_data["wrong"].append({
                "question": q["question"],
                "your_answer": selected_answer,
                "correct_answer": correct_answer
            })
            feedback = f"❌ إجابة خطأ\nالإجابة الصحيحة: {correct_answer}"

        context.user_data["current"] = current + 1
        await query.edit_message_text(feedback)
        await send_question(query, context)
        return

    if data == "restart":
        context.user_data.clear()
        await query.edit_message_text(
            "اختر الفصل لبدء كويز جديد:",
            reply_markup=build_chapter_keyboard()
        )


async def send_question(query, context: ContextTypes.DEFAULT_TYPE):
    current = context.user_data.get("current", 0)
    questions = context.user_data.get("questions", [])

    if current >= len(questions):
        score = context.user_data.get("score", 0)
        total = len(questions)
        wrong = context.user_data.get("wrong", [])

        msg = f"🎯 انتهى الاختبار\n\nالنتيجة: {score}/{total}\nالنسبة: {round(score/total*100)}%"

        if wrong:
            msg += "\n\nأبرز الأخطاء:"
            for i, item in enumerate(wrong[:5], start=1):
                msg += (
                    f"\n\n{i}) {item['question']}"
                    f"\nإجابتك: {item['your_answer']}"
                    f"\nالصحيح: {item['correct_answer']}"
                )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("إعادة الاختبار", callback_data="restart")]
        ])

        await query.message.reply_text(msg, reply_markup=keyboard)
        return

    q = questions[current]
    question_text = f"سؤال {current + 1}/{len(questions)}\n\n{q['question']}"

    if q["type"] == "mcq":
        options = q["options"].copy()
    else:
        options = ["صح", "خطأ"]

    random.shuffle(options)
    context.user_data["current_options"] = options

    keyboard = []
    for i, option in enumerate(options):
        keyboard.append([InlineKeyboardButton(option, callback_data=f"answer:{i}")])

    await query.message.reply_text(
        question_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add it in Railway Variables.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()