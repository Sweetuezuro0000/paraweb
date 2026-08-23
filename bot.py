import os
import asyncio
from flask import Flask
from threading import Thread
import libsql_client

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton,
    ReplyKeyboardRemove
)

# ================= 1. ENV & FLASK SETUP =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
TURSO_URL = os.getenv("TURSO_DB_URL")
TURSO_TOKEN = os.getenv("TURSO_DB_TOKEN")

# Fix Turso Protocol for Render (WSS -> HTTPS REST)
if TURSO_URL and TURSO_URL.startswith("libsql://"):
    TURSO_URL = TURSO_URL.replace("libsql://", "https://")

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running live!"

def run_flask():
    app.run(host="0.0.0.0", port=10000)

# ================= 2. DATABASE FUNCTIONS =================
def get_db():
    return libsql_client.create_client_sync(
        url=TURSO_URL,
        auth_token=TURSO_TOKEN
    )

def init_db():
    try:
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INT PRIMARY KEY, 
                username TEXT, 
                first_name TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                user_id INT, 
                name TEXT, 
                phone TEXT, 
                service TEXT, 
                budget TEXT
            )
        """)
        print("✅ Turso Database Connected Successfully!")
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")

# FIX: Added kwargs (service, budget) so TypeError never occurs
def save_lead(user_id, name, phone, service="N/A", budget="N/A"):
    try:
        db = get_db()
        db.execute(
            "INSERT INTO leads (user_id, name, phone, service, budget) VALUES (?, ?, ?, ?, ?)",
            [user_id, name, phone, service, budget]
        )
    except Exception as e:
        print(f"Error saving lead: {e}")

# ================= 3. AIOGRAM SETUP & STATES =================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class LeadForm(StatesGroup):
    selecting_service = State()
    selecting_budget = State()
    waiting_for_contact = State()

# ================= 4. INLINE KEYBOARDS =================
def get_services_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💻 Web Development", callback_data="service_web")],
        [InlineKeyboardButton(text="📱 App Development", callback_data="service_app")],
        [InlineKeyboardButton(text="🎨 UI/UX Design", callback_data="service_design")],
        [InlineKeyboardButton(text="🚀 Telegram Bot / Automation", callback_data="service_bot")]
    ])

def get_budget_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 ₹5,000 - ₹15,000", callback_data="budget_low")],
        [InlineKeyboardButton(text="💳 ₹15,000 - ₹50,000", callback_data="budget_mid")],
        [InlineKeyboardButton(text="💰 ₹50,000+", callback_data="budget_high")]
    ])

def get_main_menu():
    # Payment button HATA DIYA HAI. Sirf essential options hain.
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Our Services"), KeyboardButton(text="📞 Contact Support")]
        ],
        resize_keyboard=True
    )

# ================= 5. HANDLERS =================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Save User to DB
    try:
        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            [message.from_user.id, message.from_user.username or "N/A", message.from_user.first_name or "N/A"]
        )
    except Exception as e:
        print(f"DB Error on start: {e}")

    await message.answer(
        f"Hello {message.from_user.first_name}! 👋\nWelcome to our bot. Choose an option below:",
        reply_markup=get_main_menu()
    )

# Services Request -> Inline Buttons
@dp.message(F.text == "🚀 Our Services")
async def show_services(message: types.Message, state: FSMContext):
    await state.set_state(LeadForm.selecting_service)
    await message.answer(
        "Please select the service you are interested in:",
        reply_markup=get_services_keyboard()
    )

# Inline Callback for Service Selection
@dp.callback_query(LeadForm.selecting_service, F.data.startswith("service_"))
async def process_service(callback: types.CallbackQuery, state: FSMContext):
    service_name = callback.data.replace("service_", "").capitalize()
    await state.update_data(service=service_name)
    
    await state.set_state(LeadForm.selecting_budget)
    await callback.message.edit_text(
        f"Selected Service: **{service_name}**\n\nNow select your budget requirement:",
        parse_mode="Markdown",
        reply_markup=get_budget_keyboard()
    )
    await callback.answer()

# Inline Callback for Budget Selection
@dp.callback_query(LeadForm.selecting_budget, F.data.startswith("budget_"))
async def process_budget(callback: types.CallbackQuery, state: FSMContext):
    budget_range = callback.data.replace("budget_", "").upper()
    await state.update_data(budget=budget_range)
    
    await state.set_state(LeadForm.waiting_for_contact)
    
    # Request Phone Number via Share Contact Button
    contact_btn = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Share Contact Number", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    
    await callback.message.delete()
    await callback.message.answer(
        "Great! Please share your contact number to finalize your request:",
        reply_markup=contact_btn
    )
    await callback.answer()

# Process Contact Submission & Save Lead
@dp.message(LeadForm.waiting_for_contact, F.contact)
async def process_contact(message: types.Message, state: FSMContext):
    data = await state.get_data()
    service = data.get("service", "N/A")
    budget = data.get("budget", "N/A")
    
    phone = message.contact.phone_number
    name = message.from_user.full_name
    
    # Save lead cleanly
    save_lead(
        user_id=message.from_user.id,
        name=name,
        phone=phone,
        service=service,
        budget=budget
    )
    
    await state.clear()
    await message.answer(
        "✅ Thank you! Your requirement has been saved. Our team will contact you shortly.",
        reply_markup=get_main_menu()
    )

# FIX: Admin Users List with Safe Tuple Access (IndexError Resolved)
@dp.message(Command("admin_users"))
async def admin_users_list(message: types.Message):
    try:
        db = get_db()
        result = db.execute("SELECT user_id, username, first_name FROM users").rows
        
        if not result:
            await message.answer("No users found.")
            return

        response = "📋 **User List:**\n\n"
        for u in result:
            u_id = u[0]
            username = u[1] if len(u) > 1 and u[1] else "N/A"
            fname = u[2] if len(u) > 2 and u[2] else "N/A"
            response += f"• ID: `{u_id}` | @{username} | {fname}\n"

        await message.answer(response, parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"Error fetching users: {e}")

# ================= 6. BOT RUNNER =================
async def main():
    init_db()
    # Start Flask Web Server Thread
    Thread(target=run_flask, daemon=True).start()
    # Start Bot Polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
