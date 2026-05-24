# Telegram Quiz Bot - Special Education

بوت تجريبي لكويزات مادة مقدمة في التربية الخاصة.

## التشغيل محليًا
1. ثبت المتطلبات:
```bash
pip install -r requirements.txt
```

2. ضع توكن البوت:
```bash
export BOT_TOKEN="YOUR_TOKEN"
```

في Windows:
```bash
set BOT_TOKEN=YOUR_TOKEN
```

3. شغل البوت:
```bash
python bot.py
```

## التشغيل على Railway
1. ارفع الملفات على GitHub.
2. افتح Railway.
3. New Project > Deploy from GitHub.
4. أضف Variable:
```text
BOT_TOKEN=توكن البوت من BotFather
```
5. Start Command:
```bash
python bot.py
```

## الملفات
- `bot.py`: كود البوت
- `requirements.txt`: مكتبات Python
- `questions/special_education_ch1_ch2_ch3.json`: بنك الأسئلة
