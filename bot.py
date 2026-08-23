import os
import asyncio
import random
import sqlite3
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
    FSInputFile
)
from aiogram.exceptions import TelegramBadRequest

# ===============================
# 1. ENV & KEEP ALIVE (FLASK)
# ===============================
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1004463199472"))

if not TOKEN:
    raise ValueError("BOT_TOKEN missing in .env")

app = Flask('')

@app.route('/')
def home():
    return "Paraweb Bot is Alive!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

keep_alive()

# ===============================
# 2. EMBEDDED DATABASE ENGINE
# ===============================
DB_FILE = "paraweb.db"

def connect():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service TEXT,
            business TEXT,
            features TEXT,
            budget TEXT,
            requirement TEXT,
            contact TEXT,
            status TEXT DEFAULT 'NEW'
        )
    """)
    conn.commit()
    conn.close()

def save_user(user_id, username, first_name):
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username or "N/A", first_name or "N/A")
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"save_user error: {e}")

def save_lead(user_id, data):
    try:
        conn = connect()
        cursor = conn.cursor()
        features_list = data.get('features', [])
        features_str = ", ".join(features_list) if isinstance(features_list, list) else str(features_list)
        
        cursor.execute("""
            INSERT INTO leads (user_id, service, business, features, budget, requirement, contact, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW')
        """, (
            user_id,
            data.get('service', 'N/A'),
            data.get('business', 'N/A'),
            features_str,
            data.get('budget', 'N/A'),
            data.get('requirement', 'N/A'),
            data.get('contact', 'N/A')
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"save_lead error: {e}")

def get_users():
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, first_name FROM users")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"get_users error: {e}")
        return []

def get_leads():
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, service, business, features, budget, requirement, contact, status FROM leads ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"get_leads error: {e}")
        return []

def get_user_leads(user_id):
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_id, service, business, features, budget, requirement, contact, status FROM leads WHERE user_id=? ORDER BY id DESC", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"get_user_leads error: {e}")
        return []

def update_status(lead_id, status):
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("UPDATE leads SET status=? WHERE id=?", (status, lead_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"update_status error: {e}")

# ===============================
# 3. PDF & PAYMENT UTILS
# ===============================
def generate_pdf(data):
    filename = f"Quotation_{data.get('contact', 'client')}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("=== PARAWEB PROJECT QUOTATION ===\n\n")
        f.write(f"Service: {data.get('service')}\n")
        f.write(f"Business: {data.get('business')}\n")
        f.write(f"Features: {data.get('features')}\n")
        f.write(f"Budget: {data.get('budget')}\n")
        f.write(f"Requirement: {data.get('requirement')}\n")
        f.write(f"Contact: {data.get('contact')}\n\n")
        f.write("Thank you for choosing Paraweb!\n")
    return filename

async def send_payment(message: Message):
    pay_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Payment Sent / Acknowledged", callback_data="payment_done")]
        ]
    )
    await message.answer(
        "💳 **Project Confirmation & Advance Payment**\n\n"
        "To confirm your order, our executive will connect with payment details. Click below once discussed:",
        parse_mode="Markdown",
        reply_markup=pay_keyboard
    )

# ===============================
# 4. CONFIG & KEYBOARDS
# ===============================
BRAND = "Paraweb"

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

def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Start Project", callback_data="project_start")],
            [
                InlineKeyboardButton(text="🌐 Website", callback_data="service_website"),
                InlineKeyboardButton(text="📱 App", callback_data="service_app")
            ],
            [InlineKeyboardButton(text="🤖 Telegram Bot", callback_data="service_bot")],
            [InlineKeyboardButton(text="📊 My Project", callback_data="my_project")]
        ]
    )

def back_button():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back", callback_data="back")]]
    )

def business_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏪 Shop", callback_data="business_shop"),
                InlineKeyboardButton(text="🍔 Restaurant", callback_data="business_restaurant")
            ],
            [
                InlineKeyboardButton(text="🎓 Education", callback_data="business_education"),
                InlineKeyboardButton(text="🏢 Company", callback_data="business_company")
            ],
            [InlineKeyboardButton(text="💡 Startup", callback_data="business_startup")]
        ]
    )

def feature_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Payment Integration", callback_data="feature_payment"),
                InlineKeyboardButton(text="👥 Login System", callback_data="feature_login")
            ],
            [
                InlineKeyboardButton(text="📊 Admin Dashboard", callback_data="feature_dashboard"),
                InlineKeyboardButton(text="📦 Product Catalog", callback_data="feature_product")
            ],
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
            [InlineKeyboardButton(text="📩 View Leads", callback_data="admin_leads")],
            [InlineKeyboardButton(text="👥 Users Count", callback_data="admin_users")],
            [InlineKeyboardButton(text="📢 Broadcast", callback_data="broadcast")]
        ]
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
        await asyncio.sleep(random.uniform(0.5, 1.2))
    except Exception:
        pass

def is_admin(user_id):
    return user_id == ADMIN_ID

# ===============================
# 5. HANDLERS
# ===============================

@dp.message(CommandStart())
async def start(message: Message):
    await typing(message)
    save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    await message.answer(WELCOME_TEXT, reply_markup=main_menu(), parse_mode="Markdown")

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

@dp.callback_query(F.data == "project_start")
async def project_start(call: CallbackQuery):
    await call.answer()
    text = "🔥 *Project Assistant Activated*\n\nI will help you plan your project.\nFirst choose what you want to build:"
    try:
        await call.message.edit_text(text, reply_markup=main_menu(), parse_mode="Markdown")
    except TelegramBadRequest:
        pass

@dp.callback_query(F.data.startswith("service_"))
async def service_select(call: CallbackQuery):
    await call.answer()
    service = call.data.replace("service_", "")
    names = {
        "website": "🌐 Website Development",
        "app": "📱 Mobile App Development",
        "bot": "🤖 Telegram Bot Development"
    }

    text = f"✅ Selected:\n\n*{names.get(service, service.capitalize())}*\n\nGreat choice 🚀\nNow we will understand your requirements."
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Continue", callback_data=f"continue_{service}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back")]
        ]
    )
    await call.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("continue_"))
async def continue_project(call: CallbackQuery, state: FSMContext):
    await call.answer()
    service = call.data.replace("continue_", "")
    await state.update_data(service=service)
    await state.set_state(ProjectForm.business)

    await call.message.edit_text(
        "🔥 Great!\n\nTell us about your business.\nChoose category 👇",
        reply_markup=business_keyboard()
    )

@dp.callback_query(F.data.startswith("business_"))
async def business_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    business = call.data.replace("business_", "")
    await state.update_data(business=business, features=[])
    await state.set_state(ProjectForm.features)

    await call.message.edit_text(
        "⚙️ What features do you need?\n\nSelect your requirements 👇",
        reply_markup=feature_keyboard()
    )

@dp.callback_query(F.data.startswith("feature_"))
async def feature_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    feature = call.data.replace("feature_", "")

    if feature == "done":
        await state.set_state(ProjectForm.budget)
        await call.message.edit_text(
            "💰 What is your approximate budget?",
            reply_markup=budget_keyboard()
        )
        return

    data = await state.get_data()
    features = data.get("features", [])
    if feature not in features:
        features.append(feature)
        await state.update_data(features=features)
        await call.message.answer(f"✅ Added feature: {feature}")

@dp.callback_query(F.data.startswith("budget_"))
async def budget_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    budget = call.data.replace("budget_", "")
    await state.update_data(budget=budget)
    await state.set_state(ProjectForm.requirement)

    await call.message.edit_text(
        "📝 Now describe your project.\n\nTell us:\n• Your idea\n• Required pages/features\n• Any reference link/details"
    )

@dp.message(ProjectForm.requirement)
async def requirement_save(message: Message, state: FSMContext):
    await state.update_data(requirement=message.text)
    await state.set_state(ProjectForm.contact)

    await message.answer("📞 Almost done!\n\nPlease share your contact number or Telegram handle:")

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

✅ Your request has been received.
Paraweb team will contact you soon 🔥
"""
    await message.answer(summary, parse_mode="Markdown")

    pdf = generate_pdf(data)
    await message.answer_document(FSInputFile(pdf), caption="📄 Your Project Quotation")
    await send_payment(message)

    save_lead(message.from_user.id, data)
    await notify_admin(data, message.from_user)
    await state.clear()

async def notify_admin(data, user):
    text = f"""
🔥 **NEW PARAWEB LEAD**

👤 Name: {user.first_name}
🌐 Service: {data.get('service')}
🏢 Business: {data.get('business')}
⚙️ Features: {', '.join(data.get('features', []))}
💰 Budget: {data.get('budget')}
📝 Requirement: {data.get('requirement')}
📞 Contact: {data.get('contact')}
"""
    try:
        await bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
    except Exception as e:
        print(f"Failed to notify admin: {e}")

@dp.callback_query(F.data == "payment_done")
async def payment_done(call: CallbackQuery):
    await call.answer()
    await call.message.answer("✅ Payment acknowledgment received. Our team will verify and connect shortly ❤️")
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💰 **PAYMENT ACKNOWLEDGED**\n\nUser: {call.from_user.full_name}\nUsername: @{call.from_user.username}\nID: {call.from_user.id}"
        )
    except Exception:
        pass

# ===============================
# 6. EXTRAS & ADMIN FUNCTIONS
# ===============================

@dp.callback_query(F.data == "back")
async def back(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(WELCOME_TEXT, reply_markup=main_menu(), parse_mode="Markdown")

@dp.message(Command("analyze"))
async def analyze(message: Message):
    await message.answer("🔍 *Analyzing your requirements...*\n\n████████░░ 80%\n\nRecommendation: Start with MVP, then expand features 🚀", parse_mode="Markdown")

@dp.callback_query(F.data == "my_project")
async def my_project(call: CallbackQuery):
    await call.answer()
    leads = get_user_leads(call.from_user.id)
    if not leads:
        await call.message.edit_text("📂 No project found.\n\nStart your first project with Paraweb 🚀", reply_markup=main_menu())
        return

    lead = leads[0]
    status = lead[8]
    stages = {
        "NEW": "🟦 Requirement Received\n⬜ Planning\n⬜ Development\n⬜ Launch",
        "CONTACTED": "✅ Requirement Received\n🟦 Discussion Started\n⬜ Development\n⬜ Launch",
        "WORKING": "✅ Requirement Received\n✅ Planning\n🟦 Development\n⬜ Launch",
        "DONE": "✅ Project Delivered 🚀"
    }

    await call.message.edit_text(
        f"🚀 **Paraweb Project Tracker**\n\nService: {lead[2]}\nStatus:\n{stages.get(status, stages['NEW'])}\n\nCurrent Stage: {status}",
        parse_mode="Markdown"
    )

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("👑 **Paraweb Admin Panel**\n\nChoose option:", reply_markup=admin_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "admin_users")
async def users_count(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    users = get_users()
    await call.answer()
    await call.message.edit_text(f"👥 **Total Users:** {len(users)}", parse_mode="Markdown")

@dp.callback_query(F.data == "admin_leads")
async def show_leads(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    leads = get_leads()
    await call.answer()
    if not leads:
        await call.message.edit_text("📭 No leads found.")
        return

    for lead in leads[:5]:
        text = f"🔥 **LEAD #{lead[0]}**\n👤 User ID: `{lead[1]}`\n🌐 Service: {lead[2]}\n🏢 Business: {lead[3]}\n⚙️ Features: {lead[4]}\n💰 Budget: {lead[5]}\n📝 Requirement: {lead[6]}\n📞 Contact: {lead[7]}\n📌 Status: {lead[8]}"
        await call.message.answer(text, reply_markup=status_keyboard(lead[0]), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("status_"))
async def change_status(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split("_")
    status = parts[1].upper()
    lead_id = parts[2]

    update_status(lead_id, status)
    await call.answer("Status Updated ✅")
    await call.message.answer(f"✅ Lead #{lead_id} updated to {status}")

@dp.callback_query(F.data == "broadcast")
async def broadcast_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.answer()
    await state.set_state(AdminForm.broadcast_message)
    await call.message.answer("📢 Broadcast Mode\n\nSend message for all users:")

@dp.message(AdminForm.broadcast_message)
async def send_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    users = get_users()
    sent = 0
    for u in users:
        try:
            await bot.send_message(u[0], message.text)
            sent += 1
        except Exception:
            pass
    await message.answer(f"✅ Broadcast Completed. Sent to {sent} users.")
    await state.clear()

@dp.message()
async def unknown(message: Message):
    await message.answer("🤖 I am Paraweb Assistant.\nPlease use the menu below 🚀", reply_markup=main_menu())

# ===============================
# 7. BOT RUNNER
# ===============================
async def main():
    init_db()
    print("🚀 Paraweb Bot Started Successfully!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
