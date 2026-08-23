import os
import asyncio
import random
import sqlite3
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile
)

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import inch

try:
    import libsql_client
    HAS_TURSO = True
except ImportError:
    HAS_TURSO = False

# ===============================
# 1. CONFIG & FLASK KEEP-ALIVE
# ===============================
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1004463199472"))
TURSO_URL = os.getenv("TURSO_DB_URL", "").strip()
TURSO_TOKEN = os.getenv("TURSO_DB_TOKEN", "").strip()
UPI_ID = "emiakura00@oksbi"

if not TOKEN:
    raise ValueError("BOT_TOKEN missing in environment variables")

app = Flask('')

@app.route('/')
def home():
    return "Paraweb Bot, Hosting & Gift System is Alive!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

keep_alive()

# ===============================
# 2. HYBRID DATABASE ENGINE
# ===============================
DB_FILE = "paraweb.db"

def get_turso_client():
    if HAS_TURSO and TURSO_URL and TURSO_TOKEN:
        try:
            url = TURSO_URL
            if not url.startswith(("libsql://", "https://", "http://", "file:")):
                url = f"https://{url}"
            url = url.replace("libsql://", "https://")
            return libsql_client.create_client_sync(url=url, auth_token=TURSO_TOKEN)
        except Exception as e:
            print(f"⚠️ Turso connection failed ({e}). Defaulting to SQLite.")
            return None
    return None

def init_db():
    client = get_turso_client()
    if client:
        try:
            client.execute("CREATE TABLE IF NOT EXISTS users (user_id INT PRIMARY KEY, username TEXT, first_name TEXT)")
            client.execute("CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, service TEXT, business TEXT, features TEXT, budget TEXT, requirement TEXT, contact TEXT, status TEXT DEFAULT 'NEW')")
            client.execute("CREATE TABLE IF NOT EXISTS hosted_bots (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, bot_name TEXT, days INT, start_date TEXT, expiry_date TEXT, status TEXT DEFAULT 'ACTIVE')")
            client.execute("CREATE TABLE IF NOT EXISTS gift_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, days INT, max_uses INT, times_used INT DEFAULT 0)")
            print("✅ Turso Database Connected with Gift System!")
            return
        except Exception as e:
            print(f"Turso Init Error: {e}")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, business TEXT, features TEXT, budget TEXT, requirement TEXT, contact TEXT, status TEXT DEFAULT 'NEW')")
    cursor.execute("CREATE TABLE IF NOT EXISTS hosted_bots (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, bot_name TEXT, days INTEGER, start_date TEXT, expiry_date TEXT, status TEXT DEFAULT 'ACTIVE')")
    cursor.execute("CREATE TABLE IF NOT EXISTS gift_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, days INTEGER, max_uses INTEGER, times_used INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()
    print("✅ Local SQLite Database Connected with Gift System!")

def save_user(user_id, username, first_name):
    client = get_turso_client()
    if client:
        try:
            client.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)", [user_id, username or "N/A", first_name or "N/A"])
            return
        except Exception as e:
            print(f"Turso save_user error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (user_id, username or "N/A", first_name or "N/A"))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"SQLite save_user error: {e}")

def save_lead(user_id, data):
    features_list = data.get('features', [])
    features_str = ", ".join(features_list) if isinstance(features_list, list) else str(features_list)
    client = get_turso_client()
    if client:
        try:
            client.execute(
                "INSERT INTO leads (user_id, service, business, features, budget, requirement, contact, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW')",
                [user_id, data.get('service', 'N/A'), data.get('business', 'N/A'), features_str, data.get('budget', 'N/A'), data.get('requirement', 'N/A'), data.get('contact', 'N/A')]
            )
            return
        except Exception as e:
            print(f"Turso save_lead error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO leads (user_id, service, business, features, budget, requirement, contact, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW')",
            (user_id, data.get('service', 'N/A'), data.get('business', 'N/A'), features_str, data.get('budget', 'N/A'), data.get('requirement', 'N/A'), data.get('contact', 'N/A'))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"SQLite save_lead error: {e}")

def get_users():
    client = get_turso_client()
    if client:
        try:
            return client.execute("SELECT user_id, username, first_name FROM users").rows
        except Exception as e:
            print(f"Turso get_users error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, first_name FROM users")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        return []

def get_leads():
    client = get_turso_client()
    if client:
        try:
            return client.execute("SELECT id, user_id, service, business, features, budget, requirement, contact, status FROM leads ORDER BY id DESC").rows
        except Exception as e:
            print(f"Turso get_leads error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, service, business, features, budget, requirement, contact, status FROM leads ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        return []

def get_user_leads(user_id):
    client = get_turso_client()
    if client:
        try:
            return client.execute("SELECT id, user_id, service, business, features, budget, requirement, contact, status FROM leads WHERE user_id=? ORDER BY id DESC", [user_id]).rows
        except Exception as e:
            print(f"Turso get_user_leads error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, service, business, features, budget, requirement, contact, status FROM leads WHERE user_id=? ORDER BY id DESC", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        return []

def update_status(lead_id, status):
    client = get_turso_client()
    if client:
        try:
            client.execute("UPDATE leads SET status=? WHERE id=?", [status, lead_id])
            return
        except Exception as e:
            print(f"Turso update_status error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE leads SET status=? WHERE id=?", (status, lead_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"SQLite update_status error: {e}")

# --- HOSTED BOTS DB FUNCTIONS ---
def add_hosted_bot(user_id, bot_name, days, start_date, expiry_date):
    client = get_turso_client()
    if client:
        try:
            client.execute(
                "INSERT INTO hosted_bots (user_id, bot_name, days, start_date, expiry_date, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
                [user_id, bot_name, days, start_date, expiry_date]
            )
            return
        except Exception as e:
            print(f"Turso add_hosted_bot error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO hosted_bots (user_id, bot_name, days, start_date, expiry_date, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
            (user_id, bot_name, days, start_date, expiry_date)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"SQLite add_hosted_bot error: {e}")

def get_hosted_bot_by_id(bot_id):
    client = get_turso_client()
    if client:
        try:
            rows = client.execute("SELECT id, user_id, bot_name, days, start_date, expiry_date, status FROM hosted_bots WHERE id=?", [bot_id]).rows
            return rows[0] if rows else None
        except Exception as e:
            print(f"Turso get_hosted_bot_by_id error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, bot_name, days, start_date, expiry_date, status FROM hosted_bots WHERE id=?", (bot_id,))
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception as e:
        return None

def extend_hosted_bot_days(bot_id, add_days):
    bot_data = get_hosted_bot_by_id(bot_id)
    if not bot_data:
        return None

    # bot_data: (id, user_id, bot_name, days, start_date, expiry_date, status)
    curr_expiry_str = bot_data[5]
    try:
        curr_expiry = datetime.strptime(curr_expiry_str, "%Y-%m-%d %H:%M")
        if curr_expiry < datetime.now():
            curr_expiry = datetime.now()
    except Exception:
        curr_expiry = datetime.now()

    new_expiry = curr_expiry + timedelta(days=add_days)
    new_expiry_str = new_expiry.strftime("%Y-%m-%d %H:%M")
    new_total_days = bot_data[3] + add_days

    client = get_turso_client()
    if client:
        try:
            client.execute("UPDATE hosted_bots SET days=?, expiry_date=?, status='ACTIVE' WHERE id=?", [new_total_days, new_expiry_str, bot_id])
            return bot_data[1], bot_data[2], new_total_days, new_expiry_str
        except Exception as e:
            print(f"Turso extend_hosted_bot_days error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE hosted_bots SET days=?, expiry_date=?, status='ACTIVE' WHERE id=?", (new_total_days, new_expiry_str, bot_id))
        conn.commit()
        conn.close()
        return bot_data[1], bot_data[2], new_total_days, new_expiry_str
    except Exception as e:
        print(f"SQLite extend_hosted_bot_days error: {e}")
        return None

def get_all_hosted_bots():
    client = get_turso_client()
    if client:
        try:
            return client.execute("SELECT id, user_id, bot_name, days, start_date, expiry_date, status FROM hosted_bots ORDER BY id DESC").rows
        except Exception as e:
            print(f"Turso get_all_hosted_bots error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, bot_name, days, start_date, expiry_date, status FROM hosted_bots ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        return []

def get_user_hosted_bots(user_id):
    client = get_turso_client()
    if client:
        try:
            return client.execute("SELECT id, user_id, bot_name, days, start_date, expiry_date, status FROM hosted_bots WHERE user_id=? ORDER BY id DESC", [user_id]).rows
        except Exception as e:
            print(f"Turso get_user_hosted_bots error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, bot_name, days, start_date, expiry_date, status FROM hosted_bots WHERE user_id=? ORDER BY id DESC", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        return []

def delete_hosted_bot(bot_id):
    client = get_turso_client()
    if client:
        try:
            client.execute("DELETE FROM hosted_bots WHERE id=?", [bot_id])
            return
        except Exception as e:
            print(f"Turso delete_hosted_bot error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM hosted_bots WHERE id=?", (bot_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"SQLite delete_hosted_bot error: {e}")

# --- GIFT CODE DB FUNCTIONS ---
def add_gift_code(code, days, max_uses):
    code_upper = code.upper().strip()
    client = get_turso_client()
    if client:
        try:
            client.execute("INSERT INTO gift_codes (code, days, max_uses, times_used) VALUES (?, ?, ?, 0)", [code_upper, days, max_uses])
            return True
        except Exception as e:
            print(f"Turso add_gift_code error: {e}")
            return False

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO gift_codes (code, days, max_uses, times_used) VALUES (?, ?, ?, 0)", (code_upper, days, max_uses))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"SQLite add_gift_code error: {e}")
        return False

def get_gift_code(code):
    code_upper = code.upper().strip()
    client = get_turso_client()
    if client:
        try:
            rows = client.execute("SELECT id, code, days, max_uses, times_used FROM gift_codes WHERE code=?", [code_upper]).rows
            return rows[0] if rows else None
        except Exception as e:
            print(f"Turso get_gift_code error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, days, max_uses, times_used FROM gift_codes WHERE code=?", (code_upper,))
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception as e:
        return None

def use_gift_code(code):
    gift = get_gift_code(code)
    if not gift:
        return False
    
    code_id, _, _, max_uses, times_used = gift
    if times_used >= max_uses:
        return False

    new_used = times_used + 1
    client = get_turso_client()
    if client:
        try:
            client.execute("UPDATE gift_codes SET times_used=? WHERE id=?", [new_used, code_id])
            return True
        except Exception as e:
            print(f"Turso use_gift_code error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE gift_codes SET times_used=? WHERE id=?", (new_used, code_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"SQLite use_gift_code error: {e}")
        return False

def get_all_gift_codes():
    client = get_turso_client()
    if client:
        try:
            return client.execute("SELECT id, code, days, max_uses, times_used FROM gift_codes ORDER BY id DESC").rows
        except Exception as e:
            print(f"Turso get_all_gift_codes error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, days, max_uses, times_used FROM gift_codes ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        return []

def delete_gift_code(code):
    code_upper = code.upper().strip()
    client = get_turso_client()
    if client:
        try:
            client.execute("DELETE FROM gift_codes WHERE code=?", [code_upper])
            return
        except Exception as e:
            print(f"Turso delete_gift_code error: {e}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM gift_codes WHERE code=?", (code_upper,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"SQLite delete_gift_code error: {e}")


# ===============================
# 3. REPORTLAB PDF & PAYMENT UTILS
# ===============================
def generate_pdf(data):
    os.makedirs("quotations", exist_ok=True)
    quotation_id = datetime.now().strftime("PW-%Y%m%d-%H%M%S")
    filename = f"quotations/{quotation_id}.pdf"

    doc = SimpleDocTemplate(filename)
    styles = getSampleStyleSheet()

    title = styles["Heading1"]
    title.alignment = TA_CENTER

    story = []

    logo_path = "assets/logo.png"
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=1.5 * inch, height=1.5 * inch)
        story.append(logo)

    story.append(Paragraph("PARAWEB PROJECT QUOTATION", title))
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"<b>Quotation ID:</b> {quotation_id}", styles["Normal"]))
    story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%d-%m-%Y %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 15))

    features = data.get("features", [])
    features_text = ", ".join(features) if isinstance(features, list) else str(features)

    fields = [
        ("Service", data.get("service")),
        ("Business", data.get("business")),
        ("Features", features_text),
        ("Budget", data.get("budget")),
        ("Requirement", data.get("requirement")),
        ("Contact", data.get("contact"))
    ]

    for title_text, value in fields:
        story.append(Paragraph(f"<b>{title_text}</b>", styles["Heading3"]))
        story.append(Paragraph(str(value), styles["Normal"]))
        story.append(Spacer(1, 10))

    story.append(Spacer(1, 20))
    story.append(Paragraph("<b>Thank you for choosing Paraweb.</b>", styles["Heading2"]))
    story.append(Paragraph("Our team will contact you soon.", styles["Normal"]))

    doc.build(story)
    return filename

def payment_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ I Have Paid", callback_data="payment_done")]]
    )

async def send_payment_to_user(target_user_id: int):
    text = f"""
💳 **ADVANCE PAYMENT REQUEST**

Your project request has been reviewed and approved! 
Please pay the advance amount to proceed.

**Google Pay UPI:**
`{UPI_ID}`

After payment, click the button below:
✅ **I Have Paid**
"""
    qr = "assets/gpay_qr.png"
    if os.path.exists(qr):
        await bot.send_photo(chat_id=target_user_id, photo=FSInputFile(qr), caption=text, reply_markup=payment_keyboard(), parse_mode="Markdown")
    else:
        await bot.send_message(chat_id=target_user_id, text=text, reply_markup=payment_keyboard(), parse_mode="Markdown")

# ===============================
# 4. BOT SETUP & KEYBOARDS
# ===============================
WELCOME_TEXT = """
🚀 *Welcome to Paraweb*

Where ideas become digital products.

We build:
🌐 Websites
📱 Mobile Apps
🤖 Telegram Bots

Ready to transform your idea into reality?
Choose an option below 👇
"""

bot = Bot(TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class ProjectForm(StatesGroup):
    service = State()
    business = State()
    features = State()
    budget = State()
    requirement = State()
    contact = State()

class ClaimGiftForm(StatesGroup):
    code = State()
    bot_identifier = State()

class AdminForm(StatesGroup):
    broadcast_message = State()

def main_menu_reply():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Start Project"), KeyboardButton(text="📊 My Project")],
            [KeyboardButton(text="🤖 My Hosted Bots"), KeyboardButton(text="🎁 Claim Gift")],
            [KeyboardButton(text="💡 Idea Generator"), KeyboardButton(text="🧠 AI Mode")],
            [KeyboardButton(text="📞 Contact Support")]
        ],
        resize_keyboard=True
    )

def service_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Website", callback_data="service_website"), InlineKeyboardButton(text="📱 App", callback_data="service_app")],
            [InlineKeyboardButton(text="🤖 Telegram Bot", callback_data="service_bot")]
        ]
    )

def business_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏪 Shop", callback_data="business_shop"), InlineKeyboardButton(text="🍔 Restaurant", callback_data="business_restaurant")],
            [InlineKeyboardButton(text="🎓 Education", callback_data="business_education"), InlineKeyboardButton(text="🏢 Company", callback_data="business_company")],
            [InlineKeyboardButton(text="💡 Startup", callback_data="business_startup")]
        ]
    )

def feature_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Payment Integration", callback_data="feature_payment"), InlineKeyboardButton(text="👥 Login System", callback_data="feature_login")],
            [InlineKeyboardButton(text="📊 Admin Dashboard", callback_data="feature_dashboard"), InlineKeyboardButton(text="📦 Product Catalog", callback_data="feature_product")],
            [InlineKeyboardButton(text="➡️ Continue", callback_data="feature_done")]
        ]
    )

def budget_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="₹5k - ₹10k", callback_data="budget_5k-10k")],
            [InlineKeyboardButton(text="₹10k - ₹25k", callback_data="budget_10k-25k")],
            [InlineKeyboardButton(text="₹25k+", callback_data="budget_25k+")],
            [InlineKeyboardButton(text="💬 Discuss", callback_data="budget_discuss")]
        ]
    )

def personality_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👨‍💻 Developer", callback_data="mode_developer")],
            [InlineKeyboardButton(text="💼 Business", callback_data="mode_business")],
            [InlineKeyboardButton(text="🎨 Creative", callback_data="mode_creative")]
        ]
    )

def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 View All Leads", callback_data="admin_leads")],
            [InlineKeyboardButton(text="🤖 Hosted Bots List", callback_data="admin_allbots")],
            [InlineKeyboardButton(text="🎁 Active Gift Codes", callback_data="admin_allgifts")],
            [InlineKeyboardButton(text="👥 Users Count", callback_data="admin_users")],
            [InlineKeyboardButton(text="📢 Broadcast Message", callback_data="broadcast")]
        ]
    )

def admin_approval_keyboard(user_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 Approve & Send Payment QR", callback_data=f"approve_qr_{user_id}")]]
    )

def status_keyboard(lead_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📞 Contacted", callback_data=f"status_contacted_{lead_id}")],
            [InlineKeyboardButton(text="⚙️ Working", callback_data=f"status_working_{lead_id}")],
            [InlineKeyboardButton(text="✅ Done", callback_data=f"status_done_{lead_id}")]
        ]
    )

async def typing(message):
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        await asyncio.sleep(random.uniform(0.3, 0.8))
    except Exception:
        pass

def is_admin(user_id):
    return user_id == ADMIN_ID

# ===============================
# 5. FLOW & USER HANDLERS
# ===============================

@dp.message(CommandStart())
async def start(message: Message):
    await typing(message)
    save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_reply(), parse_mode="Markdown")

    try:
        user = message.from_user
        username = f"@{user.username}" if user.username else "None"
        log_text = f"🆕 **New User Started the Bot!**\n\n👤 Name: {user.first_name}\n🆔 User ID: `{user.id}`\n🌐 Username: {username}"
        await bot.send_message(chat_id=LOG_CHANNEL_ID, text=log_text, parse_mode="Markdown")
    except Exception as e:
        print(f"Log channel error: {e}")

@dp.message(F.text == "🚀 Start Project")
async def start_project_btn(message: Message):
    await typing(message)
    await message.answer("🔥 *Project Assistant Activated*\n\nChoose what you want to build:", reply_markup=service_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("service_"))
async def service_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    service = call.data.replace("service_", "")
    names = {"website": "🌐 Website Development", "app": "📱 Mobile App Development", "bot": "🤖 Telegram Bot Development"}
    await state.update_data(service=names.get(service, service))
    await state.set_state(ProjectForm.business)
    await call.message.edit_text(f"✅ Selected: *{names.get(service, service)}*\n\nNow, choose your business category 👇", reply_markup=business_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("business_"))
async def business_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    business = call.data.replace("business_", "").capitalize()
    await state.update_data(business=business, features=[])
    await state.set_state(ProjectForm.features)
    await call.message.edit_text(f"⚙️ Business: *{business}*\n\nWhat features do you need? Select below 👇", reply_markup=feature_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("feature_"))
async def feature_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    feature = call.data.replace("feature_", "")
    if feature == "done":
        await state.set_state(ProjectForm.budget)
        await call.message.edit_text("💰 What is your approximate budget requirement?", reply_markup=budget_keyboard())
        return

    data = await state.get_data()
    features = data.get("features", [])
    if feature not in features:
        features.append(feature)
        await state.update_data(features=features)
        await call.message.answer(f"✅ Feature Added: {feature.capitalize()}")

@dp.callback_query(F.data.startswith("budget_"))
async def budget_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    budget = call.data.replace("budget_", "")
    await state.update_data(budget=budget)
    await state.set_state(ProjectForm.requirement)
    await call.message.edit_text("📝 **Project Description**\n\nPlease send us a message describing your requirement:")

@dp.message(ProjectForm.requirement)
async def requirement_save(message: Message, state: FSMContext):
    await state.update_data(requirement=message.text)
    await state.set_state(ProjectForm.contact)
    await message.answer("📞 **Almost Done!**\n\nPlease share your Contact Number or Telegram Username:")

@dp.message(ProjectForm.contact)
async def contact_save(message: Message, state: FSMContext):
    await state.update_data(contact=message.text)
    data = await state.get_data()

    summary = f"""
🚀 *PROJECT SUMMARY*

🌐 *Service:* {data.get('service')}
🏢 *Business:* {data.get('business')}
⚙️ *Features:* {', '.join(data.get('features', []))}
💰 *Budget:* {data.get('budget')}
📝 *Requirement:* {data.get('requirement')}
📞 *Contact:* {data.get('contact')}

✅ **Your request has been submitted to the Admin!**
"""
    await message.answer(summary, parse_mode="Markdown", reply_markup=main_menu_reply())
    pdf_path = generate_pdf(data)
    await message.answer_document(FSInputFile(pdf_path), caption="📄 Your Official Project Quotation")
    save_lead(message.from_user.id, data)
    await notify_admin(data, message.from_user)
    await state.clear()

async def notify_admin(data, user):
    text = f"🔥 **NEW PAYMENT APPROVAL REQUEST**\n\n👤 Name: {user.first_name}\n🆔 User ID: `{user.id}`\n🌐 Service: {data.get('service')}\n🏢 Business: {data.get('business')}\n⚙️ Features: {', '.join(data.get('features', []))}\n💰 Budget: {data.get('budget')}\n📝 Requirement: {data.get('requirement')}\n📞 Contact: {data.get('contact')}"
    try:
        await bot.send_message(ADMIN_ID, text, reply_markup=admin_approval_keyboard(user.id), parse_mode="Markdown")
    except Exception as e:
        print(f"Admin notify error: {e}")

@dp.callback_query(F.data.startswith("approve_qr_"))
async def approve_and_send_qr(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    target_user_id = int(call.data.replace("approve_qr_", ""))
    try:
        await send_payment_to_user(target_user_id)
        await call.answer("Payment QR Sent to User! ✅")
        await call.message.edit_text(f"{call.message.text}\n\n✅ **APPROVED & PAYMENT QR SENT TO USER (`{target_user_id}`)!**", parse_mode="Markdown")
    except Exception as e:
        await call.answer(f"Failed to send: {e}", show_alert=True)

@dp.callback_query(F.data == "payment_done")
async def payment_done(call: CallbackQuery):
    await call.answer()
    await call.message.answer("✅ Payment acknowledgment received! Our team will verify and connect with you shortly ❤️")

# ===============================
# 6. EXTEND & GIFT VOUCHER CONTROLS
# ===============================

@dp.message(Command("claim"))
@dp.message(F.text == "🎁 Claim Gift")
async def claim_gift_start(message: Message, state: FSMContext):
    args = message.text.split()[1:]
    if len(args) >= 2:
        code = args[0]
        bot_identifier = args[1]
        await process_gift_claim(message, code, bot_identifier)
        return

    await state.set_state(ClaimGiftForm.code)
    await message.answer("🎁 **CLAIM GIFT / VOUCHER**\n\nPlease enter your Gift Code / Promo Code:")

@dp.message(ClaimGiftForm.code)
async def process_gift_code_input(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    gift = get_gift_code(code)

    if not gift:
        await message.answer("❌ **Invalid Gift Code!** Please check and try again.", reply_markup=main_menu_reply())
        await state.clear()
        return

    _, _, days, max_uses, times_used = gift
    if times_used >= max_uses:
        await message.answer("⚠️ **This Gift Code has reached its maximum usage limit!**", reply_markup=main_menu_reply())
        await state.clear()
        return

    await state.update_data(code=code, days=days)
    await state.set_state(ClaimGiftForm.bot_identifier)
    await message.answer(f"🎉 **Valid Code Found! (+{days} Days Hosting)**\n\nNow enter your **Bot Name** or **Hosted Bot ID** (If extending an existing bot):")

@dp.message(ClaimGiftForm.bot_identifier)
async def process_gift_bot_input(message: Message, state: FSMContext):
    data = await state.get_data()
    code = data.get("code")
    bot_identifier = message.text.strip()
    await process_gift_claim(message, code, bot_identifier)
    await state.clear()

async def process_gift_claim(message: Message, code: str, bot_identifier: str):
    gift = get_gift_code(code)
    if not gift:
        await message.answer("❌ **Invalid Gift Code!**")
        return

    _, _, days, max_uses, times_used = gift
    if times_used >= max_uses:
        await message.answer("⚠️ **This Gift Code has expired or reached max limit!**")
        return

    user_id = message.from_user.id
    extended = False

    # Check if bot_identifier is an integer ID for extending
    if bot_identifier.isdigit():
        bot_id = int(bot_identifier)
        res = extend_hosted_bot_days(bot_id, days)
        if res:
            extended = True
            _, bot_name, new_days, new_expiry = res
            use_gift_code(code)
            await message.answer(
                f"🎉 **GIFT CLAIMED SUCCESSFULLY!**\n\n"
                f"🤖 Bot Name: `{bot_name}` (ID: `{bot_id}`)\n"
                f"➕ Extended By: `{days}` Days\n"
                f"📅 New Expiry Date: `{new_expiry}`",
                parse_mode="Markdown",
                reply_markup=main_menu_reply()
            )

    if not extended:
        # Create a new hosting slot for this user
        start_dt = datetime.now()
        expiry_dt = start_dt + timedelta(days=days)
        start_str = start_dt.strftime("%Y-%m-%d %H:%M")
        expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M")

        add_hosted_bot(user_id, bot_identifier, days, start_str, expiry_str)
        use_gift_code(code)

        await message.answer(
            f"🎉 **GIFT CODE CLAIMED SUCCESSFULLY!**\n\n"
            f"🤖 New Hosted Bot: `{bot_identifier}`\n"
            f"⏳ Validity: `{days}` Days\n"
            f"📅 Expiry Date: `{expiry_str}`",
            parse_mode="Markdown",
            reply_markup=main_menu_reply()
        )

# ===============================
# 7. EXTRA FEATURES & COMMANDS
# ===============================

@dp.message(Command("mybots"))
@dp.message(F.text == "🤖 My Hosted Bots")
async def user_hosted_bots_cmd(message: Message):
    bots = get_user_hosted_bots(message.from_user.id)
    if not bots:
        await message.answer("📂 You have no active hosted bots.\nContact admin to host your bot with Paraweb!", reply_markup=main_menu_reply())
        return

    text = "🤖 **YOUR HOSTED BOTS**\n\n"
    for b in bots:
        try:
            exp_date = datetime.strptime(b[5], "%Y-%m-%d %H:%M")
            rem_days = (exp_date - datetime.now()).days
            status_str = f"🟢 Active ({rem_days} Days Remaining)" if rem_days >= 0 else "🔴 Expired"
        except Exception:
            status_str = "🟢 Active"

        text += f"🆔 **Bot ID:** `{b[0]}` | **Name:** `{b[2]}`\n"
        text += f"📅 **Expires On:** `{b[5]}`\n"
        text += f"📌 **Status:** {status_str}\n"
        text += "----------------------------------\n"

    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💡 Idea Generator")
async def idea_generator(message: Message):
    await typing(message)
    await message.answer("💡 *Idea Generator*\n\nTell us your business type and we will craft a digital strategy for you!", parse_mode="Markdown")

@dp.message(F.text == "🧠 AI Mode")
async def choose_mode_msg(message: Message):
    await message.answer("🧠 Choose your Paraweb Assistant personality:", reply_markup=personality_keyboard())

@dp.callback_query(F.data.startswith("mode_"))
async def mode_select(call: CallbackQuery):
    await call.answer()
    mode = call.data.replace("mode_", "")
    modes = {
        "developer": "👨‍💻 **Developer Mode Activated**",
        "business": "💼 **Business Mode Activated**",
        "creative": "🎨 **Creative Mode Activated**"
    }
    await call.message.edit_text(modes.get(mode, "Mode updated!"), parse_mode="Markdown")

@dp.message(F.text == "📊 My Project")
async def my_project_btn(message: Message):
    leads = get_user_leads(message.from_user.id)
    if not leads:
        await message.answer("📂 No active project found.\nStart your first project with Paraweb 🚀", reply_markup=main_menu_reply())
        return

    lead = leads[0]
    await message.answer(f"🚀 **Paraweb Project Tracker**\n\nService: {lead[2]}\nCurrent Stage: `{lead[8]}`", parse_mode="Markdown")

@dp.message(F.text == "📞 Contact Support")
async def support_info(message: Message):
    await message.answer("📞 **Paraweb Support**\n\nTelegram: @ParawebAdmin", parse_mode="Markdown")

# ===============================
# 8. MASTER ADMIN CONTROLS
# ===============================

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "👑 **Paraweb Master Admin Panel**\n\n"
        "**Bot Hosting Commands:**\n"
        "• `/addbot <user_id> <bot_name> <days>`\n"
        "• `/extendbot <bot_id> <add_days>`\n"
        "• `/delbot <hosted_bot_id>`\n"
        "• `/allbots` - List all active hosting slots\n\n"
        "**Gift Voucher Commands:**\n"
        "• `/creategift <code_name> <days> <max_uses>`\n"
        "• `/allgifts` - View generated vouchers\n"
        "• `/delgift <code>` - Delete voucher\n",
        reply_markup=admin_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(Command("addbot"))
async def add_bot_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    args = message.text.split()[1:]
    if len(args) < 3:
        await message.answer("⚠️ **Usage:** `/addbot <user_id> <bot_name> <days>`", parse_mode="Markdown")
        return

    try:
        target_user_id = int(args[0])
        bot_name = args[1]
        days = int(args[2])

        start_dt = datetime.now()
        expiry_dt = start_dt + timedelta(days=days)
        start_str = start_dt.strftime("%Y-%m-%d %H:%M")
        expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M")

        add_hosted_bot(target_user_id, bot_name, days, start_str, expiry_str)
        await message.answer(f"✅ **Hosted Bot Added!** User: `{target_user_id}` | Bot: `{bot_name}` | Days: `{days}`", parse_mode="Markdown")
        
        try:
            await bot.send_message(target_user_id, f"🎉 **Your Bot Hosting Is Active!**\n\n🤖 Bot Name: `{bot_name}`\n⏳ Duration: `{days}` Days\n📅 Valid Until: `{expiry_str}`", parse_mode="Markdown")
        except Exception:
            pass
    except ValueError:
        await message.answer("❌ Invalid input format.")

@dp.message(Command("extendbot"))
async def extend_bot_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()[1:]
    if len(args) < 2:
        await message.answer("⚠️ **Usage:** `/extendbot <bot_id> <add_days>`\nExample: `/extendbot 1 30`", parse_mode="Markdown")
        return

    try:
        bot_id = int(args[0])
        add_days = int(args[1])

        res = extend_hosted_bot_days(bot_id, add_days)
        if not res:
            await message.answer("❌ Bot ID not found!")
            return

        user_id, bot_name, total_days, new_expiry = res
        await message.answer(
            f"✅ **Bot Hosting Extended!**\n\n"
            f"🆔 Bot ID: `{bot_id}`\n"
            f"🤖 Bot Name: `{bot_name}`\n"
            f"➕ Added Days: `{add_days}`\n"
            f"📅 New Expiry: `{new_expiry}`",
            parse_mode="Markdown"
        )

        try:
            await bot.send_message(
                user_id,
                f"🎉 **Hosting Extended By Admin!**\n\n🤖 Bot: `{bot_name}`\n➕ Extra Days: `{add_days}`\n📅 New Expiry: `{new_expiry}`",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    except ValueError:
        await message.answer("❌ Bot ID and Days must be valid numbers.")

@dp.message(Command("creategift"))
async def create_gift_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()[1:]
    if len(args) < 2:
        await message.answer("⚠️ **Usage:** `/creategift <code_name> <days> <max_uses>`\nExample: `/creategift FREE30 30 10`", parse_mode="Markdown")
        return

    code = args[0].strip().upper()
    try:
        days = int(args[1])
        max_uses = int(args[2]) if len(args) >= 3 else 1

        if add_gift_code(code, days, max_uses):
            await message.answer(
                f"🎁 **GIFT VOUCHER CREATED!**\n\n"
                f"🏷 Code: `{code}`\n"
                f"⏳ Duration: `{days}` Days\n"
                f"👥 Max Uses: `{max_uses}` Times\n\n"
                f"Users can redeem via `/claim {code} <bot_name>`",
                parse_mode="Markdown"
            )
        else:
            await message.answer("❌ Failed to create code. Code name might already exist!")
    except ValueError:
        await message.answer("❌ Days and Max Uses must be numbers.")

@dp.message(Command("delgift"))
async def del_gift_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()[1:]
    if not args:
        await message.answer("⚠️ **Usage:** `/delgift <code>`", parse_mode="Markdown")
        return

    delete_gift_code(args[0])
    await message.answer(f"✅ Gift Code `{args[0].upper()}` deleted.", parse_mode="Markdown")

@dp.message(Command("allgifts"))
@dp.callback_query(F.data == "admin_allgifts")
async def all_gifts_cmd(event: Message | CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    target_msg = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await event.answer()

    gifts = get_all_gift_codes()
    if not gifts:
        await target_msg.answer("📭 No active gift vouchers in system.")
        return

    text = "🎁 **ALL GIFT VOUCHERS**\n\n"
    for g in gifts:
        # g: (id, code, days, max_uses, times_used)
        text += f"🏷 **Code:** `{g[1]}`\n"
        text += f"⏳ **Duration:** `{g[2]}` Days\n"
        text += f"📊 **Usage:** `{g[4]}/{g[3]}` Used\n"
        text += "----------------------------------\n"

    await target_msg.answer(text, parse_mode="Markdown")

@dp.message(Command("delbot"))
async def del_bot_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()[1:]
    if not args:
        await message.answer("⚠️ **Usage:** `/delbot <hosted_bot_id>`", parse_mode="Markdown")
        return

    try:
        delete_hosted_bot(int(args[0]))
        await message.answer(f"✅ Hosted Bot ID `{args[0]}` deleted.", parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Invalid Bot ID.")

@dp.message(Command("allbots"))
@dp.callback_query(F.data == "admin_allbots")
async def all_bots_cmd(event: Message | CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    target_msg = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await event.answer()

    bots = get_all_hosted_bots()
    if not bots:
        await target_msg.answer("📭 No active hosted bots in system.")
        return

    text = "🤖 **ALL HOSTED BOTS**\n\n"
    for b in bots:
        try:
            exp_date = datetime.strptime(b[5], "%Y-%m-%d %H:%M")
            rem_days = (exp_date - datetime.now()).days
            status_emoji = "🟢" if rem_days >= 0 else "🔴"
        except Exception:
            rem_days = 0
            status_emoji = "🟡"

        text += f"🆔 **ID:** `{b[0]}` | User: `{b[1]}`\n"
        text += f"🤖 Bot: **{b[2]}**\n"
        text += f"⏳ Status: {status_emoji} `{rem_days} days left` (Expires: {b[5]})\n"
        text += "----------------------------------\n"

    await target_msg.answer(text, parse_mode="Markdown")

@dp.message(Command("stats"))
@dp.callback_query(F.data == "admin_users")
async def users_count(event: Message | CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return
    users = get_users()
    leads = get_leads()
    bots = get_all_hosted_bots()
    gifts = get_all_gift_codes()
    text = f"📊 **Paraweb System Stats**\n\n👥 Users: `{len(users)}` \n📩 Leads: `{len(leads)}` \n🤖 Hosted Bots: `{len(bots)}` \n🎁 Gift Codes: `{len(gifts)}`"
    
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.edit_text(text, parse_mode="Markdown")
    else:
        await event.answer(text, parse_mode="Markdown")

@dp.message(Command("leads"))
@dp.callback_query(F.data == "admin_leads")
async def show_leads(event: Message | CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    target_msg = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await event.answer()

    leads = get_leads()
    if not leads:
        await target_msg.answer("📭 No leads found in the system.")
        return

    for lead in leads[:10]:
        text = f"🔥 **LEAD #{lead[0]}**\n👤 User ID: `{lead[1]}`\n🌐 Service: {lead[2]}\n🏢 Business: {lead[3]}\n⚙️ Features: {lead[4]}\n💰 Budget: {lead[5]}\n📝 Requirement: {lead[6]}\n📞 Contact: {lead[7]}\n📌 Status: `{lead[8]}`"
        await target_msg.answer(text, reply_markup=status_keyboard(lead[0]), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("status_"))
async def change_status(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split("_")
    status = parts[1].upper()
    lead_id = parts[2]

    update_status(lead_id, status)
    await call.answer(f"Status Updated to {status} ✅")
    await call.message.edit_text(f"{call.message.text}\n\n✅ **Updated Status to:** `{status}`", parse_mode="Markdown")

@dp.message(Command("broadcast"))
@dp.callback_query(F.data == "broadcast")
async def broadcast_start(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    msg = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await event.answer()

    await state.set_state(AdminForm.broadcast_message)
    await msg.answer("📢 **Broadcast Mode Active**\n\nSend the message you want to broadcast to all registered users:")

@dp.message(AdminForm.broadcast_message)
async def send_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    users = get_users()
    sent = 0
    failed = 0
    
    for u in users:
        try:
            await bot.send_message(u[0], message.text)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(f"✅ **Broadcast Execution Complete**\n\n🟢 Sent: `{sent}`\n🔴 Failed: `{failed}`", parse_mode="Markdown")
    await state.clear()

@dp.message()
async def unknown(message: Message):
    await message.answer("🤖 I am Paraweb Assistant.\nPlease use the menu options below 🚀", reply_markup=main_menu_reply())

# ===============================
# 9. BOT RUNNER
# ===============================
async def main():
    init_db()
    print("🚀 Paraweb Bot with Gift & Extension System Running Successfully!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
