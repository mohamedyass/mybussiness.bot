import os
import sqlite3
from datetime import datetime
import telebot
import google.generativeai as genai
from schedule import repeat, run_pending
import time
import threading

# 1. ضبط المفاتيح
TELEGRAM_TOKEN = "ضع_توكن_تليجرام_هنا"
GEMINI_KEY = "ضع_مفتاح_جميناي_هنا"
MY_CHAT_ID = "ضع_رقم_chat_id_خاصتك"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# 2. إعداد قاعدة بيانات محلية حفظاً للملخصات اليومية للتقارير الشهرية
def init_db():
    conn = sqlite3.connect('work_log.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            month TEXT,
            log_text TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_log(log_text):
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect('work_log.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO daily_logs (date, month, log_text) VALUES (?, ?, ?)', (today, month, log_text))
    conn.commit()
    conn.close()

# 3. معالجة الرسائل المسائية (نصية أو تسجيل صوتي)
@bot.message_handler(content_types=['text', 'voice'])
def handle_messages(message):
    # تجاهل الرسائل من غير صاحب البوت
    if str(message.chat.id) != str(MY_CHAT_ID):
        return

    # إذا كانت أوا أمر تقرير شهري
    if message.text and message.text.startswith('/report'):
        parts = message.text.split()
        target_month = parts[1] if len(parts) > 1 else datetime.now().strftime("%Y-%m")
        send_monthly_report(message.chat.id, target_month)
        return

    user_text = ""
    
    # تفريغ الصوت إن كانت رسالة صوتية
    if message.content_type == 'voice':
        bot.reply_to(message, "جاري معالجة التسجيل الصوتي...")
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open("temp_voice.ogg", 'wb') as f:
            f.write(downloaded_file)
            
        audio_file = genai.upload_file(path="temp_voice.ogg")
        prompt = "قم بتفريغ هذا الصوت لنص واضح يمثل ملخص العمل اليومي."
        response = model.generate_content([prompt, audio_file])
        user_text = response.text
    else:
        user_text = message.text

    # حفظ النص في قاعدة البيانات للتقرير الشهري
    save_log(user_text)

    # توليد أفكار LinkedIn المسائية
    evening_prompt = f"""
    أنت خبير تسويق محتوى على LinkedIn. قم بتحليل ملخص العمل اليومي التالي واستخرج منه 3 أفكار منشورات احترافية:
    1. منشور قصة (Storytelling).
    2. منشور نصيحة/درس مستفاد.
    3. منشور تفاعلي بسؤال للجمهور.
    
    ملخص العمل: {user_text}
    """
    ai_response = model.generate_content(evening_prompt)
    bot.reply_to(message, f"تم حفظ ملخص اليوم بنجاح! وإليك أفكار المنشورات:\n\n{ai_response.text}")

# 4. دالة التقرير الشهري
def send_monthly_report(chat_id, month_str):
    conn = sqlite3.connect('work_log.db')
    cursor = conn.cursor()
    cursor.execute('SELECT date, log_text FROM daily_logs WHERE month = ?', (month_str,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.send_message(chat_id, f"لا توجد ملخصات مسجلة لشهر {month_str}")
        return

    all_logs = "\n".join([f"تاريخ {r[0]}: {r[1]}" for r in rows])
    
    report_prompt = f"""
    أنت مدير عمليات تنفيذي. قم بمراجعة جميع الملخصات اليومية للعمل المرفقة لشهر {month_str}، وأنتج تقريراً إنجازياً شهرياً متكاملاً مقسماً إلى:
    1. أبرز الإنجازات والمهام المكتملة.
    2. الاختبارات والعمليات المنفذة.
    3. التحديات والمشاكل التي تم حلها.
    4. الدروس المستفادة.

    الملخصات:
    {all_logs}
    """
    bot.send_message(chat_id, "جاري إعداد التقرير الشهري...")
    response = model.generate_content(report_prompt)
    bot.send_message(chat_id, response.text)

# 5. التنبيه الصباحي التلقائي (الساعة 8:30 صباحاً)
def morning_job():
    morning_prompt = "أعطني 3 أفكار منشورات تفاعلية وجديدة لـ LinkedIn لهذا اليوم تناسب مجال تكنولوجيا المعلومات والأعمال الرقمية والحلول الذكية."
    response = model.generate_content(morning_prompt)
    bot.send_message(MY_CHAT_ID, f"صباح الخير! إليك مقترحات منشورات اليوم:\n\n{response.text}")

def scheduler_thread():
    import schedule
    schedule.every().day.at("08:30").do(morning_job)
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=scheduler_thread, daemon=True).start()

# تشغيل البوت
bot.polling(none_stop=True)