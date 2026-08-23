import os
import csv
import asyncio
import random
import sqlite3
import qrcode
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

# ReportLab Imports for Professional PDF Generation
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import inch

# Try importing Turso client, fallback to SQLite if not present
try:
    import libsql_client
    HAS_TURSO = True
except ImportError:
    HAS_TURSO = False
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")

def now_ist():
    return datetime.now(IST)
def calculate_expiry(days):
    today_midnight = now_ist().replace(hour=0, minute=0, second=0, microsecond=0)
    expiry = today_midnight + timedelta(days=days)
    return expiry
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

# Fixed hosting plans (days -> price in INR)
HOSTING_PLANS = {
    "7": {"days": 7, "price": 19},
    "14": {"days": 14, "price": 35},
    "30": {"days": 30, "price": 59},
}

# How often the reminder loop checks hosting expiries (seconds)
REMINDER_CHECK_INTERVAL = 1800  # 30 minutes

if not TOKEN:
    raise ValueError("BOT_TOKEN missing in environment variables")

app = Flask('')

@app.route('/')
def home():
    return "Paraweb Bot & Hosting Manager is Alive & Running!"

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

def db_execute(query, params=None, fetchone=False, fetchall=False):
    """Generic helper that runs a query against Turso if configured, else SQLite.
    Returns: single row / list of rows / lastrowid (sqlite only) / None."""
    params = params or []
    client = get_turso_client()
    if client:
        try:
            result = client.execute(query, params)
            if fetchone:
                return result.rows[0] if result.rows else None
            if fetchall:
                return result.rows
            return None
        except Exception as e:
            print(f"Turso error: {e} | Query: {query}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetchone:
            row = cursor.fetchone()
            conn.commit()
            conn.close()
            return row
        if fetchall:
            rows = cursor.fetchall()
            conn.commit()
            conn.close()
            return rows
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id
    except Exception as e:
        print(f"SQLite error: {e} | Query: {query}")
        return None

def _safe_alter(query):
    """Run an ALTER TABLE that might already have been applied; ignore duplicate-column errors."""
    try:
        db_execute(query)
    except Exception:
        pass

def init_db():
    # Base tables
    db_execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT)")
    db_execute("CREATE TABLE IF NOT EXISTS leads (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service TEXT, business TEXT, features TEXT, budget TEXT, requirement TEXT, contact TEXT, status TEXT DEFAULT 'NEW')")
    db_execute("CREATE TABLE IF NOT EXISTS hosted_bots (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, bot_name TEXT, days INTEGER, start_date TEXT, expiry_date TEXT, status TEXT DEFAULT 'ACTIVE')")

    # New tables for hosting orders, live chat forwarding, and chat sessions
    db_execute("CREATE TABLE IF NOT EXISTS hosting_orders (id TEXT PRIMARY KEY, user_id INTEGER, bot_name TEXT, plan_days INTEGER, amount INTEGER, order_type TEXT, target_bot_id TEXT, status TEXT DEFAULT 'PENDING')")
    db_execute("CREATE TABLE IF NOT EXISTS chat_forward_map (admin_msg_id INTEGER PRIMARY KEY, user_id INTEGER)")
    db_execute("CREATE TABLE IF NOT EXISTS live_chat_sessions (user_id INTEGER PRIMARY KEY, active INTEGER DEFAULT 0)")

    # Migrations for existing DBs (safe no-ops if columns already exist)
    _safe_alter("ALTER TABLE leads ADD COLUMN priority TEXT DEFAULT 'NORMAL'")
    _safe_alter("ALTER TABLE hosted_bots ADD COLUMN reminder_1day_sent INTEGER DEFAULT 0")
    _safe_alter("ALTER TABLE hosted_bots ADD COLUMN reminder_2hr_sent INTEGER DEFAULT 0")

    print("✅ Database Ready (Turso if configured, else local SQLite)")

# --- USERS ---
def save_user(user_id, username, first_name):
    db_execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
               [user_id, username or "N/A", first_name or "N/A"])

def get_users():
    return db_execute("SELECT user_id, username, first_name FROM users", fetchall=True) or []

# --- LEADS ---
def save_lead(user_id, data):
    features_list = data.get('features', [])
    features_str = ", ".join(features_list) if isinstance(features_list, list) else str(features_list)
    db_execute(
        "INSERT INTO leads (user_id, service, business, features, budget, requirement, contact, status, priority) VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW', 'NORMAL')",
        [user_id, data.get('service', 'N/A'), data.get('business', 'N/A'), features_str,
         data.get('budget', 'N/A'), data.get('requirement', 'N/A'), data.get('contact', 'N/A')]
    )

def get_leads():
    return db_execute(
        "SELECT id, user_id, service, business, features, budget, requirement, contact, status, priority FROM leads ORDER BY id DESC",
        fetchall=True
    ) or []

def get_user_leads(user_id):
    return db_execute(
        "SELECT id, user_id, service, business, features, budget, requirement, contact, status, priority FROM leads WHERE user_id=? ORDER BY id DESC",
        [user_id], fetchall=True
    ) or []

def update_status(lead_id, status):
    db_execute("UPDATE leads SET status=? WHERE id=?", [status, lead_id])

def update_priority(lead_id, priority):
    db_execute("UPDATE leads SET priority=? WHERE id=?", [priority, lead_id])

# --- HOSTED BOTS ---
def add_hosted_bot(user_id, bot_name, days, start_date, expiry_date):
    db_execute(
        "INSERT INTO hosted_bots (user_id, bot_name, days, start_date, expiry_date, status, reminder_1day_sent, reminder_2hr_sent) VALUES (?, ?, ?, ?, ?, 'ACTIVE', 0, 0)",
        [user_id, bot_name, days, start_date, expiry_date]
    )

def get_all_hosted_bots():
    return db_execute(
        "SELECT id, user_id, bot_name, days, start_date, expiry_date, status, reminder_1day_sent, reminder_2hr_sent FROM hosted_bots ORDER BY id DESC",
        fetchall=True
    ) or []

def get_user_hosted_bots(user_id):
    return db_execute(
        "SELECT id, user_id, bot_name, days, start_date, expiry_date, status, reminder_1day_sent, reminder_2hr_sent FROM hosted_bots WHERE user_id=? ORDER BY id DESC",
        [user_id], fetchall=True
    ) or []

def delete_hosted_bot(bot_id):
    db_execute("DELETE FROM hosted_bots WHERE id=?", [bot_id])

def extend_hosted_bot(bot_id, add_days):
    """Adds days to a bot's expiry (from now if already expired, else from current expiry)."""
    row = db_execute("SELECT expiry_date FROM hosted_bots WHERE id=?", [bot_id], fetchone=True)
    if not row:
        return None
    try:
        current_expiry = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
    except Exception:
        current_expiry = now_ist()
    base = current_expiry if current_expiry > now_ist() else now_ist()
    new_expiry = base + timedelta(days=add_days)
    new_expiry_str = new_expiry.strftime("%Y-%m-%d %H:%M")
    db_execute(
        "UPDATE hosted_bots SET expiry_date=?, status='ACTIVE', reminder_1day_sent=0, reminder_2hr_sent=0 WHERE id=?",
        [new_expiry_str, bot_id]
    )
    return new_expiry_str

# --- HOSTING ORDERS (payment flow) ---
def create_hosting_order(user_id, bot_name, plan_days, amount, order_type, target_bot_id=None):
    order_id = f"{user_id}_{int(now_ist().timestamp())}"
    db_execute(
        "INSERT INTO hosting_orders (id, user_id, bot_name, plan_days, amount, order_type, target_bot_id, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')",
        [order_id, user_id, bot_name, plan_days, amount, order_type, target_bot_id]
    )
    return order_id

def get_hosting_order(order_id):
    return db_execute(
        "SELECT id, user_id, bot_name, plan_days, amount, order_type, target_bot_id, status FROM hosting_orders WHERE id=?",
        [order_id], fetchone=True
    )

def update_order_status(order_id, status):
    db_execute("UPDATE hosting_orders SET status=? WHERE id=?", [status, order_id])

# --- LIVE CHAT ---
def set_chat_session(user_id, active):
    existing = db_execute("SELECT user_id FROM live_chat_sessions WHERE user_id=?", [user_id], fetchone=True)
    if existing:
        db_execute("UPDATE live_chat_sessions SET active=? WHERE user_id=?", [1 if active else 0, user_id])
    else:
        db_execute("INSERT INTO live_chat_sessions (user_id, active) VALUES (?, ?)", [user_id, 1 if active else 0])

def is_chat_active(user_id):
    row = db_execute("SELECT active FROM live_chat_sessions WHERE user_id=?", [user_id], fetchone=True)
    return bool(row and row[0] == 1)

def save_chat_forward(admin_msg_id, user_id):
    db_execute("INSERT OR REPLACE INTO chat_forward_map (admin_msg_id, user_id) VALUES (?, ?)", [admin_msg_id, user_id])

def get_chat_target(admin_msg_id):
    row = db_execute("SELECT user_id FROM chat_forward_map WHERE admin_msg_id=?", [admin_msg_id], fetchone=True)
    return row[0] if row else None

# ===============================
# 3. REPORTLAB PDF & PAYMENT UTILS
# ===============================
def generate_pdf(data):
    os.makedirs("quotations", exist_ok=True)
    quotation_id = now_ist().strftime("PW-%Y%m%d-%H%M%S")
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
    story.append(Paragraph(f"<b>Date:</b> {now_ist().strftime('%d-%m-%Y %H:%M')}", styles["Normal"]))
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
        await bot.send_photo(
            chat_id=target_user_id,
            photo=FSInputFile(qr),
            caption=text,
            reply_markup=payment_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await bot.send_message(
            chat_id=target_user_id,
            text=text,
            reply_markup=payment_keyboard(),
            parse_mode="Markdown"
        )

def generate_upi_link(amount, note):
    safe_note = str(note).replace(" ", "-")
    return f"upi://pay?pa={UPI_ID}&pn=Paraweb&am={amount}&cu=INR&tn={safe_note}"

async def send_payment_request(chat_id, order_id, amount, note):
    upi_link = generate_upi_link(amount, note)
    text = (
        f"💳 **Payment Request**\n\n"
        f"Amount: ₹{amount}\n"
        f"UPI ID: `{UPI_ID}`\n\n"
        f"Pay ₹{amount} by scanning QR or manually entering ID in the UPI app.\n"
        f"Click on '✅ I Have Paid' after payment."
    )
    os.makedirs("qr_codes", exist_ok=True)
    qr_path = f"qr_codes/{order_id}.png"
    qr_img = qrcode.make(upi_link)
    qr_img.save(qr_path)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ I Have Paid", callback_data=f"paid_order_{order_id}")]
    ])
    await bot.send_photo(
        chat_id,
        FSInputFile(qr_path),
        caption=text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
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

class AdminForm(StatesGroup):
    broadcast_message = State()
    search_lead_id = State()

class HostingForm(StatesGroup):
    new_bot_name = State()

def main_menu_reply():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Start Project"), KeyboardButton(text="📊 My Project")],
            [KeyboardButton(text="🤖 My Hosted Bots"), KeyboardButton(text="🖥 Bot Hosting")],
            [KeyboardButton(text="💡 Idea Generator"), KeyboardButton(text="🧠 AI Mode")],
            [KeyboardButton(text="📞 Contact Support")]
        ],
        resize_keyboard=True
    )

def chat_active_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ End Chat")]],
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
            [InlineKeyboardButton(text="🖥 Hosting Overview", callback_data="admin_hostingoverview")],
            [InlineKeyboardButton(text="👥 Users Count", callback_data="admin_users")],
            [InlineKeyboardButton(text="🔎 Search Lead", callback_data="admin_searchlead")],
            [InlineKeyboardButton(text="📤 Export Leads", callback_data="admin_export")],
            [InlineKeyboardButton(text="📢 Broadcast Message", callback_data="broadcast")]
        ]
    )

def admin_approval_keyboard(user_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Approve & Send Payment QR", callback_data=f"approve_qr_{user_id}")]
        ]
    )

def lead_action_keyboard(lead_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📞 Contacted", callback_data=f"status_contacted_{lead_id}"),
             InlineKeyboardButton(text="⚙️ Working", callback_data=f"status_working_{lead_id}")],
            [InlineKeyboardButton(text="✅ Done", callback_data=f"status_done_{lead_id}")],
            [InlineKeyboardButton(text="🔥 Hot", callback_data=f"priority_hot_{lead_id}"),
             InlineKeyboardButton(text="🌤️ Warm", callback_data=f"priority_warm_{lead_id}"),
             InlineKeyboardButton(text="❄️ Cold", callback_data=f"priority_cold_{lead_id}")]
        ]
    )

def hosting_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ New Bot Hosting", callback_data="hosting_new")],
        [InlineKeyboardButton(text="🔄 Extend Existing Bot", callback_data="hosting_extend")],
        [InlineKeyboardButton(text="📋 My Hosted Bots", callback_data="hosting_mybots")]
    ])

def plan_keyboard(prefix):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="7 Days - ₹19", callback_data=f"{prefix}_7")],
        [InlineKeyboardButton(text="14 Days - ₹35", callback_data=f"{prefix}_14")],
        [InlineKeyboardButton(text="30 Days - ₹59", callback_data=f"{prefix}_30")]
    ])

async def typing(message):
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        await asyncio.sleep(random.uniform(0.3, 0.8))
    except Exception:
        pass

def is_admin(user_id):
    return user_id == ADMIN_ID

def format_lead_text(lead):
    priority = lead[9] if len(lead) > 9 and lead[9] else "NORMAL"
    return (
        f"🔥 **LEAD #{lead[0]}**\n"
        f"👤 User ID: `{lead[1]}`\n"
        f"🌐 Service: {lead[2]}\n"
        f"🏢 Business: {lead[3]}\n"
        f"⚙️ Features: {lead[4]}\n"
        f"💰 Budget: {lead[5]}\n"
        f"📝 Requirement: {lead[6]}\n"
        f"📞 Contact: {lead[7]}\n"
        f"📌 Status: `{lead[8]}`\n"
        f"🏷️ Priority: `{priority}`"
    )

async def show_user_hosted_bots(user_id, send_func):
    bots = get_user_hosted_bots(user_id)
    if not bots:
        await send_func("📂 You have no active hosted bots.\nUse '🖥 Bot Hosting' to get started!")
        return

    text = "🤖 **YOUR HOSTED BOTS**\n\n"
    for b in bots:
        # b: (id, user_id, bot_name, days, start_date, expiry_date, status, reminder_1day_sent, reminder_2hr_sent)
        try:
            exp_date = datetime.strptime(b[5], "%Y-%m-%d %H:%M")
            rem_days = (exp_date - now_ist()).days
            status_str = f"🟢 Active ({rem_days} Days Remaining)" if (rem_days >= 0 and b[6] == "ACTIVE") else "🔴 Expired"
        except Exception:
            status_str = "🟢 Active"

        text += f"🔹 **Bot Name:** `{b[2]}`\n"
        text += f"📅 **Expires On:** `{b[5]}`\n"
        text += f"📌 **Status:** {status_str}\n"
        text += "----------------------------------\n"

    await send_func(text, parse_mode="Markdown")

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
        log_text = (
            "🆕 **New User Started the Bot!**\n\n"
            f"👤 Name: {user.first_name}\n"
            f"🆔 User ID: `{user.id}`\n"
            f"🌐 Username: {username}"
        )
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
    names = {
        "website": "🌐 Website Development",
        "app": "📱 Mobile App Development",
        "bot": "🤖 Telegram Bot Development"
    }

    await state.update_data(service=names.get(service, service))
    await state.set_state(ProjectForm.business)

    await call.message.edit_text(
        f"✅ Selected: *{names.get(service, service)}*\n\nNow, choose your business category 👇",
        reply_markup=business_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("business_"))
async def business_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    business = call.data.replace("business_", "").capitalize()
    await state.update_data(business=business, features=[])
    await state.set_state(ProjectForm.features)

    await call.message.edit_text(
        f"⚙️ Business: *{business}*\n\nWhat features do you need? Select below 👇",
        reply_markup=feature_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("feature_"))
async def feature_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    feature = call.data.replace("feature_", "")

    if feature == "done":
        await state.set_state(ProjectForm.budget)
        await call.message.edit_text(
            "💰 What is your approximate budget requirement?",
            reply_markup=budget_keyboard()
        )
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

    await call.message.edit_text(
        "📝 **Project Description**\n\nPlease send us a message describing your requirement:\n• Your core idea\n• Required pages\n• Reference links (if any)"
    )

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
Once reviewed by our team, you will receive the Payment QR directly here.
"""
    await message.answer(summary, parse_mode="Markdown", reply_markup=main_menu_reply())

    pdf_path = generate_pdf(data)
    await message.answer_document(FSInputFile(pdf_path), caption="📄 Your Official Project Quotation")

    save_lead(message.from_user.id, data)
    await notify_admin(data, message.from_user)
    await state.clear()

async def notify_admin(data, user):
    text = f"""
🔥 **NEW PAYMENT APPROVAL REQUEST**

👤 Name: {user.first_name}
🆔 User ID: `{user.id}`
🌐 Service: {data.get('service')}
🏢 Business: {data.get('business')}
⚙️ Features: {', '.join(data.get('features', []))}
💰 Budget: {data.get('budget')}
📝 Requirement: {data.get('requirement')}
📞 Contact: {data.get('contact')}

👇 Click below to approve & send Payment QR to user:
"""
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
        await call.message.edit_text(
            f"{call.message.text}\n\n✅ **APPROVED & PAYMENT QR SENT TO USER (`{target_user_id}`)!**",
            parse_mode="Markdown"
        )
    except Exception as e:
        await call.answer(f"Failed to send: {e}", show_alert=True)

@dp.callback_query(F.data == "payment_done")
async def payment_done(call: CallbackQuery):
    await call.answer()
    await call.message.answer("✅ Payment acknowledgment received! Our team will verify and connect with you shortly ❤️")
    try:
        username = f"@{call.from_user.username}" if call.from_user.username else "N/A"
        await bot.send_message(
            ADMIN_ID,
            f"💰 **PAYMENT ACKNOWLEDGED BY USER**\n\nUser: {call.from_user.full_name}\nUsername: {username}\nID: `{call.from_user.id}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Payment notify admin error: {e}")

# ===============================
# 6. HOSTING: NEW + EXTEND + PAYMENT
# ===============================

@dp.message(F.text == "🖥 Bot Hosting")
@dp.message(Command("hosting"))
async def hosting_menu(message: Message):
    await message.answer(
        "🖥 **Bot Hosting Services**\n\nPlans:\n• 7 Days - ₹19\n• 14 Days - ₹35\n• 30 Days - ₹59\n\nKya karna chahte ho?",
        reply_markup=hosting_menu_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "hosting_new")
async def hosting_new_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(HostingForm.new_bot_name)
    await call.message.answer("🤖 Apni bot ka naam bhejo:")

@dp.message(HostingForm.new_bot_name)
async def hosting_new_name(message: Message, state: FSMContext):
    await state.update_data(bot_name=message.text)
    await state.clear()
    await message.answer("💰 Plan chuno:", reply_markup=plan_keyboard("newplan"))

@dp.callback_query(F.data.startswith("newplan_"))
async def hosting_new_plan(call: CallbackQuery, state: FSMContext):
    await call.answer()
    plan_key = call.data.replace("newplan_", "")
    plan = HOSTING_PLANS.get(plan_key)
    if not plan:
        return
    data = await state.get_data()
    bot_name = data.get("bot_name", "MyBot")
    order_id = create_hosting_order(call.from_user.id, bot_name, plan["days"], plan["price"], "NEW")
    await call.message.answer(f"🤖 Bot: {bot_name}\n📦 Plan: {plan['days']} Days - ₹{plan['price']}")
    await send_payment_request(call.from_user.id, order_id, plan["price"], f"NewHosting-{bot_name}")

@dp.callback_query(F.data == "hosting_extend")
async def hosting_extend_start(call: CallbackQuery):
    await call.answer()
    bots = get_user_hosted_bots(call.from_user.id)
    active_bots = [b for b in bots if b[6] == "ACTIVE"]
    if not active_bots:
        await call.message.answer("📭 Aapke paas koi active hosted bot nahi hai. Pehle '➕ New Bot Hosting' se shuru kare.")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{b[2]} (Exp: {b[5]})", callback_data=f"extendbot_{b[0]}")] for b in active_bots
    ])
    await call.message.answer("🔄 Kaunsi bot extend karni hai?", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("extendbot_"))
async def hosting_extend_select(call: CallbackQuery):
    await call.answer()
    bot_id = call.data.replace("extendbot_", "")
    await call.message.answer("💰 Kitne din extend karne hain?", reply_markup=plan_keyboard(f"extplan-{bot_id}"))

@dp.callback_query(F.data.startswith("extplan-"))
async def hosting_extend_plan(call: CallbackQuery):
    await call.answer()
    # data format: extplan-<botid>_<plankey>
    payload = call.data.replace("extplan-", "")
    bot_id, plan_key = payload.rsplit("_", 1)
    plan = HOSTING_PLANS.get(plan_key)
    if not plan:
        return
    order_id = create_hosting_order(call.from_user.id, "", plan["days"], plan["price"], "EXTEND", target_bot_id=bot_id)
    await call.message.answer(f"📦 Extend Plan: {plan['days']} Days - ₹{plan['price']}")
    await send_payment_request(call.from_user.id, order_id, plan["price"], f"ExtendHosting-{bot_id}")

@dp.callback_query(F.data == "hosting_mybots")
async def hosting_mybots_cb(call: CallbackQuery):
    await call.answer()
    await show_user_hosted_bots(call.from_user.id, call.message.answer)

@dp.callback_query(F.data.startswith("paid_order_"))
async def hosting_paid(call: CallbackQuery):
    await call.answer()
    order_id = call.data.replace("paid_order_", "")
    order = get_hosting_order(order_id)
    if not order:
        await call.message.answer("❌ Order not found.")
        return
    update_order_status(order_id, "PAID")
    await call.message.answer("✅ Payment acknowledgment received! Admin verify karke hosting activate karega.")

    _id, user_id, bot_name, plan_days, amount, order_type, target_bot_id, status = order
    admin_text = (
        f"💰 **HOSTING PAYMENT — APPROVAL NEEDED**\n\n"
        f"🆔 Order: `{order_id}`\n"
        f"👤 User ID: `{user_id}`\n"
        f"🤖 Bot Name: `{bot_name or '(extend existing)'}`\n"
        f"📦 Plan: {plan_days} Days - ₹{amount}\n"
        f"🔧 Type: {order_type}"
    )
    approve_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Approve & Activate", callback_data=f"approve_order_{order_id}")]
    ])
    try:
        await bot.send_message(ADMIN_ID, admin_text, reply_markup=approve_keyboard, parse_mode="Markdown")
    except Exception as e:
        print(f"Hosting admin notify error: {e}")

@dp.callback_query(F.data.startswith("approve_order_"))
async def hosting_approve(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    order_id = call.data.replace("approve_order_", "")
    order = get_hosting_order(order_id)
    if not order:
        await call.answer("Order not found", show_alert=True)
        return

    _id, user_id, bot_name, plan_days, amount, order_type, target_bot_id, status = order
    if status == "APPROVED":
        await call.answer("Already approved", show_alert=True)
        return

    if order_type == "NEW":
        start_dt = now_ist()
        expiry_dt = start_dt + timedelta(days=plan_days)
        add_hosted_bot(user_id, bot_name, plan_days, start_dt.strftime("%Y-%m-%d %H:%M"), expiry_dt.strftime("%Y-%m-%d %H:%M"))
        user_text = f"🎉 **Hosting Activated!**\n\n🤖 Bot: {bot_name}\n⏳ Valid: {plan_days} Days\n📅 Expiry: {expiry_dt.strftime('%Y-%m-%d %H:%M')}"
    else:
        new_expiry = extend_hosted_bot(target_bot_id, plan_days)
        user_text = f"🎉 **Hosting Extended!**\n\n⏳ Added: {plan_days} Days\n📅 New Expiry: {new_expiry}"

    update_order_status(order_id, "APPROVED")
    await call.answer("Approved ✅")
    try:
        await call.message.edit_text(f"{call.message.text}\n\n✅ **APPROVED & ACTIVATED**", parse_mode="Markdown")
    except Exception:
        pass
    try:
        await bot.send_message(user_id, user_text, parse_mode="Markdown")
    except Exception as e:
        print(f"Failed to notify user of hosting approval: {e}")

# ===============================
# 7. EXTRA FEATURES & USER COMMANDS
# ===============================

@dp.message(Command("mybots"))
@dp.message(F.text == "🤖 My Hosted Bots")
async def user_hosted_bots_cmd(message: Message):
    await show_user_hosted_bots(message.from_user.id, message.answer)

@dp.message(F.text == "💡 Idea Generator")
async def idea_generator(message: Message):
    await typing(message)
    await message.answer("💡 *Idea Generator*\n\nTell us your business type (e.g. Shop, Education, Restaurant, Startup) and we will craft a digital strategy for you!", parse_mode="Markdown")

@dp.message(F.text == "🧠 AI Mode")
async def choose_mode_msg(message: Message):
    await message.answer("🧠 Choose your Paraweb Assistant personality:", reply_markup=personality_keyboard())

@dp.callback_query(F.data.startswith("mode_"))
async def mode_select(call: CallbackQuery):
    await call.answer()
    mode = call.data.replace("mode_", "")
    modes = {
        "developer": "👨‍💻 **Developer Mode Activated**\nFocusing on Architecture, Code Quality & API performance.",
        "business": "💼 **Business Mode Activated**\nFocusing on Customer Acquisition, Growth & ROI.",
        "creative": "🎨 **Creative Mode Activated**\nFocusing on UI/UX, Design Aesthetics & Brand Feel."
    }
    await call.message.edit_text(modes.get(mode, "Mode updated!"), parse_mode="Markdown")

@dp.message(Command("analyze"))
async def analyze(message: Message):
    await typing(message)
    await message.answer("🧠 *Analysis Complete*\n\nProject Feasibility: ████████░░ 80%\n\nRecommendation: Start with MVP, then scale features 🚀", parse_mode="Markdown")

@dp.message(F.text == "📊 My Project")
async def my_project_btn(message: Message):
    leads = get_user_leads(message.from_user.id)
    if not leads:
        await message.answer("📂 No active project found.\nStart your first project with Paraweb 🚀", reply_markup=main_menu_reply())
        return

    lead = leads[0]
    status = lead[8]
    stages = {
        "NEW": "🟦 Requirement Received\n⬜ Discussion\n⬜ Development\n⬜ Launch",
        "CONTACTED": "✅ Requirement Received\n🟦 Discussion Started\n⬜ Development\n⬜ Launch",
        "WORKING": "✅ Requirement Received\n✅ Discussion Done\n🟦 Development\n⬜ Launch",
        "DONE": "✅ Project Delivered 🚀"
    }

    await message.answer(f"🚀 **Paraweb Project Tracker**\n\nService: {lead[2]}\nStatus:\n{stages.get(status, stages['NEW'])}\n\nCurrent Stage: `{status}`", parse_mode="Markdown")

# --- LIVE CHAT (user side) ---
@dp.message(F.text == "📞 Contact Support")
async def contact_support_start(message: Message):
    set_chat_session(message.from_user.id, True)
    await message.answer(
        "💬 **Live Chat Shuru Ho Gaya Hai**\n\nAb aap seedha humari team se baat kar sakte ho. Jab chahe '❌ End Chat' dabaake ya /endchat bhej ke band kar sakte ho.",
        parse_mode="Markdown",
        reply_markup=chat_active_keyboard()
    )
    try:
        await bot.send_message(ADMIN_ID, f"💬 {message.from_user.first_name} (ID: `{message.from_user.id}`) ne live chat shuru kiya hai. Uske messages yahin forward honge — reply karne ke liye seedha us forwarded message ko Reply kare.", parse_mode="Markdown")
    except Exception as e:
        print(f"Chat start admin notify error: {e}")

@dp.message(F.text == "❌ End Chat")
@dp.message(Command("endchat"))
async def end_chat(message: Message):
    set_chat_session(message.from_user.id, False)
    await message.answer("✅ Chat band ho gaya. Aap wapas menu use kar sakte ho.", reply_markup=main_menu_reply())

# ===============================
# 8. ALL ADMIN CONTROLS
# ===============================

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "👑 **Paraweb Master Admin Panel**\n\n"
        "**Bot Hosting Commands:**\n"
        "• `/addbot <user_id> <bot_name> <days>`\n"
        "• `/delbot <hosted_bot_id>`\n"
        "• `/allbots` - List all active hosting slots\n"
        "• `/hostingoverview` - Active/Expiring/Expired summary\n\n"
        "**Leads Commands:**\n"
        "• `/leads [hot|warm|cold]`\n"
        "• `/searchlead <user_id>`\n"
        "• `/export` - Export all leads as CSV\n\n"
        "**Direct Messaging:**\n"
        "• `/msg <user_id> <text>` - message any user directly\n"
        "• Reply to a forwarded live-chat message to respond to that user\n\n"
        "Select an operation below:",
        reply_markup=admin_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(Command("addbot"))
async def add_bot_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()[1:]
    if len(args) < 3:
        await message.answer(
            "⚠️ **Invalid Format!**\n\n"
            "**Usage:** `/addbot <user_id> <bot_name> <days>`\n"
            "**Example:** `/addbot 123456789 DemoBot 30`",
            parse_mode="Markdown"
        )
        return

    try:
        target_user_id = int(args[0])
        bot_name = args[1]
        days = int(args[2])

        start_dt = now_ist()
        expiry_dt = start_dt + timedelta(days=days)

        start_str = start_dt.strftime("%Y-%m-%d %H:%M")
        expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M")

        add_hosted_bot(target_user_id, bot_name, days, start_str, expiry_str)

        await message.answer(
            f"✅ **Hosted Bot Added Successfully!**\n\n"
            f"👤 User ID: `{target_user_id}`\n"
            f"🤖 Bot Name: `{bot_name}`\n"
            f"⏳ Validity: `{days}` Days\n"
            f"📅 Expiry Date: `{expiry_str}`",
            parse_mode="Markdown"
        )

        try:
            await bot.send_message(
                target_user_id,
                f"🎉 **Your Bot Hosting Is Now Active!**\n\n"
                f"🤖 Bot Name: `{bot_name}`\n"
                f"⏳ Duration: `{days}` Days\n"
                f"📅 Valid Until: `{expiry_str}`\n\n"
                f"Use /mybots or click **🤖 My Hosted Bots** in main menu to check status.",
                parse_mode="Markdown"
            )
        except Exception as e:
            await message.answer(f"⚠️ Bot saved to DB, but failed to notify user: {e}")

    except ValueError:
        await message.answer("❌ User ID and Days must be valid numbers.")

@dp.message(Command("delbot"))
async def del_bot_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()[1:]
    if len(args) < 1:
        await message.answer("⚠️ **Usage:** `/delbot <hosted_bot_id>`\nUse `/allbots` to find bot IDs.", parse_mode="Markdown")
        return

    try:
        bot_id = int(args[0])
        delete_hosted_bot(bot_id)
        await message.answer(f"✅ Hosted Bot ID `{bot_id}` has been removed.", parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Invalid Bot ID.")

@dp.message(Command("allbots"))
@dp.callback_query(F.data == "admin_allbots")
async def all_bots_cmd(event: Message | CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target_msg = event.message
    else:
        target_msg = event

    bots = get_all_hosted_bots()
    if not bots:
        await target_msg.answer("📭 No active hosted bots in system.")
        return

    text = "🤖 **ALL HOSTED BOTS**\n\n"
    for b in bots:
        try:
            exp_date = datetime.strptime(b[5], "%Y-%m-%d %H:%M")
            rem_days = (exp_date - now_ist()).days
            status_emoji = "🟢" if (rem_days >= 0 and b[6] == "ACTIVE") else "🔴"
        except Exception:
            rem_days = 0
            status_emoji = "🟡"

        text += f"🆔 **ID:** `{b[0]}` | User: `{b[1]}`\n"
        text += f"🤖 Bot: **{b[2]}**\n"
        text += f"⏳ Status: {status_emoji} `{rem_days} days left` (Expires: {b[5]})\n"
        text += "----------------------------------\n"

    await target_msg.answer(text, parse_mode="Markdown")

@dp.message(Command("hostingoverview"))
@dp.callback_query(F.data == "admin_hostingoverview")
async def hosting_overview_cmd(event: Message | CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        target_msg = event.message
    else:
        target_msg = event

    bots = get_all_hosted_bots()
    now = now_ist()
    active = expiring_soon = expired = 0

    for b in bots:
        status = b[6]
        try:
            exp = datetime.strptime(b[5], "%Y-%m-%d %H:%M")
        except Exception:
            exp = None

        if status == "EXPIRED" or (exp and exp < now):
            expired += 1
        else:
            active += 1
            if exp and (exp - now) <= timedelta(days=2):
                expiring_soon += 1

    text = (
        f"🖥 **Hosting Overview**\n\n"
        f"🟢 Active: `{active}`\n"
        f"🟡 Expiring in ≤2 days: `{expiring_soon}`\n"
        f"🔴 Expired: `{expired}`\n"
        f"📦 Total Slots: `{len(bots)}`"
    )
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
    text = (
        f"📊 **Paraweb System Stats**\n\n"
        f"👥 Total Users: `{len(users)}` \n"
        f"📩 Total Leads: `{len(leads)}` \n"
        f"🤖 Hosted Bots: `{len(bots)}`"
    )

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

    filter_priority = None
    if isinstance(event, Message):
        args = event.text.split(maxsplit=1)
        if len(args) > 1:
            filter_priority = args[1].strip().upper()

    if isinstance(event, CallbackQuery):
        await event.answer()
        target_msg = event.message
    else:
        target_msg = event

    leads = get_leads()
    if filter_priority:
        leads = [l for l in leads if (l[9] or "NORMAL").upper() == filter_priority]

    if not leads:
        await target_msg.answer("📭 No leads found.")
        return

    for lead in leads[:10]:
        await target_msg.answer(format_lead_text(lead), reply_markup=lead_action_keyboard(lead[0]), parse_mode="Markdown")

@dp.message(Command("searchlead"))
async def search_lead_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    args = message.text.split()[1:]
    if not args:
        await message.answer("Usage: `/searchlead <user_id>`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await message.answer("❌ Invalid user ID.")
        return
    leads = get_user_leads(target_id)
    if not leads:
        await message.answer(f"📭 No leads found for user `{target_id}`.", parse_mode="Markdown")
        return
    for lead in leads:
        await message.answer(format_lead_text(lead), reply_markup=lead_action_keyboard(lead[0]), parse_mode="Markdown")

@dp.callback_query(F.data == "admin_searchlead")
async def search_lead_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.answer()
    await state.set_state(AdminForm.search_lead_id)
    await call.message.answer("🔎 User ID bhejo jiske leads dekhne hain:")

@dp.message(AdminForm.search_lead_id)
async def search_lead_input(message: Message, state: FSMContext):
    await state.clear()
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid user ID.")
        return
    leads = get_user_leads(target_id)
    if not leads:
        await message.answer(f"📭 No leads found for user `{target_id}`.", parse_mode="Markdown")
        return
    for lead in leads:
        await message.answer(format_lead_text(lead), reply_markup=lead_action_keyboard(lead[0]), parse_mode="Markdown")

@dp.message(Command("export"))
@dp.callback_query(F.data == "admin_export")
async def export_leads_cmd(event: Message | CallbackQuery):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return
    if isinstance(event, CallbackQuery):
        await event.answer()
        target_msg = event.message
    else:
        target_msg = event

    leads = get_leads()
    if not leads:
        await target_msg.answer("📭 No leads to export.")
        return

    os.makedirs("exports", exist_ok=True)
    filename = f"exports/leads_{now_ist().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "User ID", "Service", "Business", "Features", "Budget", "Requirement", "Contact", "Status", "Priority"])
        for lead in leads:
            row = list(lead) + [""] * (10 - len(lead))
            writer.writerow(row[:10])

    await target_msg.answer_document(FSInputFile(filename), caption="📤 Leads Export (CSV)")

@dp.callback_query(F.data.startswith("status_"))
async def change_status(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split("_")
    status = parts[1].upper()
    lead_id = int(parts[2])

    update_status(lead_id, status)
    await call.answer(f"Status Updated to {status} ✅")
    await call.message.edit_text(f"{call.message.text}\n\n✅ **Updated Status to:** `{status}`", parse_mode="Markdown", reply_markup=call.message.reply_markup)

    lead_row = db_execute("SELECT user_id, service FROM leads WHERE id=?", [lead_id], fetchone=True)
    if lead_row:
        target_user_id, service = lead_row[0], lead_row[1]
        status_messages = {
            "CONTACTED": "📞 Our team has contacted you regarding your project!",
            "WORKING": "⚙️ Great news! We've started working on your project.",
            "DONE": "✅ Your project has been completed! 🎉"
        }
        user_text = status_messages.get(status, f"📌 Your project status has been updated to: {status}")
        try:
            await bot.send_message(target_user_id, f"🔔 **Project Update ({service})**\n\n{user_text}", parse_mode="Markdown")
        except Exception as e:
            print(f"Failed to notify user {target_user_id}: {e}")

@dp.callback_query(F.data.startswith("priority_"))
async def change_priority(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split("_")
    priority = parts[1].upper()
    lead_id = int(parts[2])

    update_priority(lead_id, priority)
    await call.answer(f"Priority set to {priority} ✅")
    try:
        await call.message.edit_text(f"{call.message.text}\n\n🏷️ **Priority Updated:** `{priority}`", parse_mode="Markdown", reply_markup=call.message.reply_markup)
    except Exception:
        pass

@dp.message(Command("broadcast"))
@dp.callback_query(F.data == "broadcast")
async def broadcast_start(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    if isinstance(event, CallbackQuery):
        await event.answer()
        msg = event.message
    else:
        msg = event

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

@dp.message(Command("msg"))
async def admin_direct_msg(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Usage: `/msg <user_id> <message>`", parse_mode="Markdown")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("❌ Invalid user ID.")
        return
    text = parts[2]
    try:
        await bot.send_message(target_id, f"📩 **Message from Paraweb Team:**\n\n{text}", parse_mode="Markdown")
        await message.answer("✅ Message sent.")
    except Exception as e:
        await message.answer(f"❌ Failed to send: {e}")

# --- Admin replying to a forwarded live-chat message ---
@dp.message(F.reply_to_message)
async def admin_reply_forward(message: Message):
    if not is_admin(message.from_user.id):
        return
    target_user_id = get_chat_target(message.reply_to_message.message_id)
    if not target_user_id:
        return
    try:
        await bot.send_message(target_user_id, f"💬 **Paraweb Support:**\n\n{message.text}", parse_mode="Markdown")
        await message.reply("✅ User ko bhej diya")
    except Exception as e:
        await message.reply(f"❌ Failed: {e}")

# ===============================
# 9. HOSTING REMINDER BACKGROUND LOOP
# ===============================
async def check_hosting_reminders():
    bots = get_all_hosted_bots()
    now = now_ist()

    for b in bots:
        # b: (id, user_id, bot_name, days, start_date, expiry_date, status, reminder_1day_sent, reminder_2hr_sent)
        bot_id, user_id, bot_name, days, start_date, expiry_date, status = b[0], b[1], b[2], b[3], b[4], b[5], b[6]
        r1 = b[7] if len(b) > 7 else 0
        r2 = b[8] if len(b) > 8 else 0

        if status != "ACTIVE":
            continue

        try:
            exp = datetime.strptime(expiry_date, "%Y-%m-%d %H:%M")
        except Exception:
            continue

        remaining = exp - now

        if remaining.total_seconds() <= 0:
            db_execute("UPDATE hosted_bots SET status='EXPIRED' WHERE id=?", [bot_id])
            try:
                await bot.send_message(
                    user_id,
                    f"🔴 **Hosting Expired**\n\nAapki bot '{bot_name}' expire ho gayi hai. Renew karne ke liye 🖥 Bot Hosting me jaake Extend kare.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Expiry notify error: {e}")
            continue

        if not r1 and remaining <= timedelta(days=1):
            db_execute("UPDATE hosted_bots SET reminder_1day_sent=1 WHERE id=?", [bot_id])
            try:
                await bot.send_message(
                    user_id,
                    f"⏰ **Reminder**\n\nAapki bot '{bot_name}' 1 din me expire ho jaayegi ({expiry_date}). '🖥 Bot Hosting' → Extend se renew kare.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"1-day reminder error: {e}")

        if not r2 and remaining <= timedelta(hours=2):
            db_execute("UPDATE hosted_bots SET reminder_2hr_sent=1 WHERE id=?", [bot_id])
            try:
                await bot.send_message(
                    user_id,
                    f"🚨 **Urgent Reminder**\n\nAapki bot '{bot_name}' sirf 2 ghante me expire ho jaayegi! Turant extend kare.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"2-hour reminder error: {e}")

async def hosting_reminder_loop():
    while True:
        try:
            await check_hosting_reminders()
        except Exception as e:
            print(f"Reminder loop error: {e}")
        await asyncio.sleep(REMINDER_CHECK_INTERVAL)

# ===============================
# 10. CATCH-ALL (must stay last)
# ===============================
@dp.message()
async def unknown(message: Message):
    if is_chat_active(message.from_user.id):
        try:
            sent = await bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
            save_chat_forward(sent.message_id, message.from_user.id)
        except Exception as e:
            print(f"Chat forward error: {e}")
        return
    await message.answer("🤖 I am Paraweb Assistant.\nPlease use the menu options below 🚀", reply_markup=main_menu_reply())

# ===============================
# 11. BOT RUNNER
# ===============================
async def main():
    init_db()
    asyncio.create_task(hosting_reminder_loop())
    print("🚀 Paraweb Bot Running Successfully!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
