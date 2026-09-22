import os
import sqlite3
from datetime import datetime
import telebot
import google.generativeai as genai
import schedule
import time
import threading

# 1. ضبط المفاتيح (تأكد من كتابة مفاتيحك الصحيحة هنا)
TELEGRAM_TOKEN = "PUT_TELEGRAM_TOKEN_HERE"
GEMINI_KEY = "PUT_GEMINI_KEY_HERE"
MY_CHAT_ID = "PUT_CHAT_ID_HERE"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# 2. إعداد قاعدة البيانات للذاكرة الدائمة والملخصات
def init_db():
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    # جدول سجل العمل اليومي
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            month TEXT,
            log_text TEXT
        )
    ''')
    # جدول المصادر والحسابات المفضلة
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_url TEXT
        )
    ''')
    # جدول الملف الشخصي وأسلوب الكتابة
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profile (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- وظائف إدارة الذاكرة الدائمة ---

def get_context():
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    
    # جلب البروفايل
    cursor.execute('SELECT value FROM user_profile WHERE key = "profile"')
    profile_row = cursor.fetchone()
    profile = profile_row[0] if profile_row else "لم يتم تحديد بروفايل بعد."
    
    # جلب المصادر
    cursor.execute('SELECT source_url FROM sources')
    sources_rows = cursor.fetchall()
    sources = "\n".join([r[0] for r in sources_rows]) if sources_rows else "لا توجد مصادر محددة."
    
    conn.close()
    
    context_str = f"""
    === معلومات المستخدم الشخصية وأسلوبه ===
    {profile}

    === المصادر والحسابات والمدونات المعتمدة للاستلهام ===
    {sources}
    """
    return context_str

# --- أوامر التليجرام لإضافة وتحديث البيانات ---

@bot.message_handler(commands=['setprofile'])
def set_profile_cmd(message):
    text = message.text.replace('/setprofile', '').strip()
    if not text:
        bot.reply_to(message, "يرجى كتابة معلوماتك بعد الأمر.\nمثال:\n`/setprofile أنا أعمل في إدارة المنتجات الرقمية، وأفضل أسلوب كتابة مباشر ومختصر.`", parse_mode="Markdown")
        return
    
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO user_profile (key, value) VALUES ("profile", ?)', (text,))
    conn.commit()
    conn.close()
    bot.reply_to(message, "✅ تم حفظ وتحديث ملفك الشخصي وأسلوب الكتابة بنجاح!")

@bot.message_handler(commands=['addsource'])
def add_source_cmd(message):
    url = message.text.replace('/addsource', '').strip()
    if not url:
        bot.reply_to(message, "يرجى إرفاق رابط المصدر أو اسم الحساب بعد الأمر.\nمثال:\n`/addsource https://x.com/username`", parse_mode="Markdown")
        return
    
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO sources (source_url) VALUES (?)', (url,))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ تم إضافة المصدر بنجاح:\n{url}")

@bot.message_handler(commands=['sources'])
def list_sources_cmd(message):
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    cursor.execute('SELECT source_url FROM sources')
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        bot.reply_to(message, "لا توجد مصادر مخزنة حتى الآن. استخدم `/addsource` لإضافة مصدر.", parse_mode="Markdown")
    else:
        sources_list = "\n".join([f"• {r[0]}" for r in rows])
        bot.reply_to(message, f"📚 **المصادر المخزنة حالياً:**\n\n{sources_list}", parse_mode="Markdown")

@bot.message_handler(commands=['report'])
def report_cmd(message):
    parts = message.text.split()
    target_month = parts[1] if len(parts) > 1 else datetime.now().strftime("%Y-%m")
    
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    cursor.execute('SELECT date, log_text FROM daily_logs WHERE month = ?', (target_month,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.reply_to(message, f"لا توجد ملخصات يومية مسجلة لشهر {target_month}")
        return

    all_logs = "\n".join([f"تاريخ {r[0]}: {r[1]}" for r in rows])
    user_context = get_context()
    
    report_prompt = f"""
    أنت مدير عمليات تنفيذي.
    {user_context}
    
    قم بمراجعة جميع الملخصات اليومية المرفقة لشهر {target_month}، وأنتج تقريراً إنجازياً شهرياً متكاملاً مقسماً إلى:
    1. أبرز الإنجازات والمهام المكتملة.
    2. الاختبارات والعمليات المنفذة.
    3. التحديات والمشاكل التي تم حلها.
    4. الدروس المستفادة.

    الملخصات:
    {all_logs}
    """
    bot.reply_to(message, "جاري معالجة البيانات وتوليد التقرير الشهري...")
    response = model.generate_content(report_prompt)
    bot.send_message(message.chat.id, response.text)

# --- معالجة الملخصات والرسائل المسائية ---

@bot.message_handler(content_types=['text', 'voice'])
def handle_daily_inputs(message):
    if str(message.chat.id) != str(MY_CHAT_ID):
        return

    user_text = ""
    
    # تفريغ التسجيل الصوتي
    if message.content_type == 'voice':
        bot.reply_to(message, "🎙️ جاري تفريغ الصوت وتحليله...")
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

    # حفظ الإنجاز اليومي في قاعدة البيانات
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    conn = sqlite3.connect('knowledge_base.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO daily_logs (date, month, log_text) VALUES (?, ?, ?)', (today, month, user_text))
    conn.commit()
    conn.close()

    # توليد أفكار LinkedIn المسائية بناءً على السياق الدائم والمصادر
    user_context = get_context()
    evening_prompt = f"""
    أنت خبير تسويق محتوى على LinkedIn.
    {user_context}
    
    بناءً على ملف المستخدم والمصادر المعتمدة وبناءً على ملخص العمل اليومي التالي، استخرج 3 أفكار منشورات احترافية تلائم أسلوب المستخدم:
    1. منشور بأسلوب قصة (Storytelling).
    2. منشور بأسلوب نصيحة/درس مستفاد.
    3. منشور تفاعلي بسؤال موجه للجمهور.
    
    ملخص عمل اليوم:
    {user_text}
    """
    ai_response = model.generate_content(evening_prompt)
    bot.reply_to(message, f"✅ تم حفظ ملخص اليوم في الأرشيف!\n\n💡 **أفكار المنشورات المقترحة:**\n\n{ai_response.text}")

# --- التنبيه الصباحي التلقائي (8:30 صباحاً) ---

def morning_job():
    user_context = get_context()
    morning_prompt = f"""
    أنت مستشار صناعة المحتوى على LinkedIn.
    {user_context}
    
    بناءً على المصادر والحسابات المعتمدة والبروفايل المرفق، ابحث أو استخرج 3 أفكار منشورات جديدة ومبتكرة لهذا اليوم مع كتابة Hook (افتتاحية مشوقة) وزاوية طرح لكل فكرة.
    """
    response = model.generate_content(morning_prompt)
    bot.send_message(MY_CHAT_ID, f"☀️ **صباح الخير! إليك مقترحات منشورات اليوم:**\n\n{response.text}")

def scheduler_thread():
    schedule.every().day.at("08:30").do(morning_job)
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=scheduler_thread, daemon=True).start()

# تشغيل البوت
bot.polling(none_stop=True)
