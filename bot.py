import asyncio
import os
import sqlite3
import os
import libsql_client

TURSO_URL = os.getenv("TURSO_DB_URL")
TURSO_TOKEN = os.getenv("TURSO_DB_TOKEN")

# Ensure URL uses https for REST protocol
if TURSO_URL and TURSO_URL.startswith("libsql://"):
    TURSO_URL = TURSO_URL.replace("libsql://", "https://")

def get_db():
    return libsql_client.create_client_sync(
        url=TURSO_URL,
        auth_token=TURSO_TOKEN
    )

def init_db():
    try:
        db = get_db()
        db.execute("CREATE TABLE IF NOT EXISTS users (user_id INT PRIMARY KEY, name TEXT)")
        print("✅ Turso Database Connected Successfully!")
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")from threading import Thread
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)

# Custom Local Modules (Restored)
from pdf_generator import generate_pdf
from payment import send_payment

from database import (
    init_db as init_main_db,
    save_user,
    save_lead,
    get_leads,
    get_users,
    get_user_leads,
    update_status,
    connect,
)

from hosting_manager import (
    init_db as init_hosting_db,
    add_user_bot,
    extend_user_bot,
    get_user_bots,
)


# =========================================================
# CONFIG
# =========================================================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")

if not TOKEN or not ADMIN_ID_RAW:
    raise ValueError("BOT_TOKEN ya ADMIN_ID env me missing hai!")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise ValueError("ADMIN_ID numeric integer honi chahiye!")

BRAND = "Paraweb"


# =========================================================
# FLASK SERVER (RENDER KEEP ALIVE)
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Paraweb Bot Active!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    Thread(target=run_web, daemon=True).start()


# =========================================================
# BOT & STATES
# =========================================================

bot = Bot(TOKEN)
dp = Dispatcher()

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

class PaymentForm(StatesGroup):
    waiting_for_proof = State()


# =========================================================
# KEYBOARDS
# =========================================================

def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Start New Project", callback_data="proj_start_all")],
            [
                InlineKeyboardButton(text="🌐 Website", callback_data="proj_website"),
                InlineKeyboardButton(text="📱 Mobile App", callback_data="proj_app"),
            ],
            [InlineKeyboardButton(text="🤖 Telegram Bot", callback_data="proj_bot")],
            [
                InlineKeyboardButton(text="📊 My Projects", callback_data="my_projects"),
                InlineKeyboardButton(text="🖥️ My Hosted Bots", callback_data="check_my_bots"),
            ],
            [InlineKeyboardButton(text="💳 Submit Payment Proof", callback_data="user_paid")]
        ]
    )

def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 All Leads", callback_data="admin_leads_list"),
                InlineKeyboardButton(text="🔍 Search Lead ID", callback_data="admin_search_lead")
            ],
            [
                InlineKeyboardButton(text="👥 Users Detail", callback_data="admin_users_list"),
                InlineKeyboardButton(text="🤖 Hosted Bots", callback_data="admin_bots_list")
            ],
            [InlineKeyboardButton(text="📢 Send Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="⬅️ Main Menu", callback_data="back_to_main")]
        ]
    )

def back_admin():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back to Admin Panel", callback_data="admin_panel_open")]]
    )

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def safe_edit(call: CallbackQuery, text: str, reply_markup=None, parse_mode="Markdown"):
    try:
        await call.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest:
        pass


# =========================================================
# START COMMAND
# =========================================================

@dp.message(CommandStart())
async def start(message: Message):
    save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = f"🚀 *Welcome to {BRAND}*\n\nWe design & develop Websites, Mobile Apps, and Telegram Bots.\nSelect an option to start 👇"
    await message.answer(text, reply_markup=main_menu(), parse_mode="Markdown")


# =========================================================
# PROJECT FORM, PDF GENERATION & PAYMENT FLOW
# =========================================================

@dp.callback_query(F.data.in_({"proj_start_all", "proj_website", "proj_app", "proj_bot"}))
async def start_project_flow(call: CallbackQuery, state: FSMContext):
    await call.answer()
    
    service_map = {
        "proj_start_all": "Custom Project",
        "proj_website": "Website Development",
        "proj_app": "Mobile App Development",
        "proj_bot": "Telegram Bot Development"
    }
    selected_service = service_map.get(call.data, "Custom Project")
    
    await state.update_data(service=selected_service)
    await state.set_state(ProjectForm.business)
    
    await safe_edit(
        call,
        f"🎯 *Service Selected:* `{selected_service}`\n\n*Step 1/5:* Aapke Business / Project ka naam kya hai?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="back_to_main")]])
    )

@dp.message(ProjectForm.business)
async def process_business(message: Message, state: FSMContext):
    await state.update_data(business=message.text)
    await state.set_state(ProjectForm.features)
    await message.answer("💡 *Step 2/5:* Features detail me likhein jo aapko chahiye:")

@dp.message(ProjectForm.features)
async def process_features(message: Message, state: FSMContext):
    await state.update_data(features=message.text)
    await state.set_state(ProjectForm.budget)
    await message.answer("💰 *Step 3/5:* Expected Budget (e.g. ₹2000 - ₹5000 / $50):")

@dp.message(ProjectForm.budget)
async def process_budget(message: Message, state: FSMContext):
    await state.update_data(budget=message.text)
    await state.set_state(ProjectForm.requirement)
    await message.answer("📝 *Step 4/5:* Specific timeline ya extra requirements:")

@dp.message(ProjectForm.requirement)
async def process_req(message: Message, state: FSMContext):
    await state.update_data(requirement=message.text)
    await state.set_state(ProjectForm.contact)
    await message.answer("📞 *Step 5/5:* Aapka Contact / WhatsApp Number:")

@dp.message(ProjectForm.contact)
async def process_contact(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    
    contact = message.text
    u_id = message.from_user.id
    
    # 1. Save Lead in Database
    save_lead(
        user_id=u_id,
        service=data.get("service"),
        business=data.get("business"),
        features=data.get("features"),
        budget=data.get("budget"),
        requirement=data.get("requirement"),
        contact=contact
    )

    await message.answer("🔄 *Generating Official PDF Quotation... Please wait.*", parse_mode="Markdown")

    # 2. Generate PDF Quotation
    lead_info = {
        "user_id": u_id,
        "service": data.get("service"),
        "business": data.get("business"),
        "features": data.get("features"),
        "budget": data.get("budget"),
        "requirement": data.get("requirement"),
        "contact": contact,
        "name": message.from_user.first_name
    }

    try:
        pdf_path = generate_pdf(lead_info)
        await message.answer_document(
            FSInputFile(pdf_path),
            caption=f"📄 *Here is your official {BRAND} Project Quotation PDF!*"
        )
    except Exception as e:
        print(f"PDF Generation Error: {e}")
        await message.answer("📄 *Quotation Details Saved Successfully!*")

    # 3. Call Payment Module to Send Payment / UPI Details
    try:
        await send_payment(message, data.get("budget"))
    except Exception as e:
        print(f"Payment Module Error: {e}")
        pay_msg = (
            f"💳 *PAYMENT INSTRUCTIONS*\n\n"
            f"Aap apne project ki advance payment karke niche button se screenshot bhej sakte hain."
        )
        await message.answer(
            pay_msg,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Submit Payment Proof", callback_data="user_paid")]]),
            parse_mode="Markdown"
        )

    # 4. Notify Admin
    try:
        admin_alert = f"🚨 *NEW LEAD RECEIVED!*\n\n• *Service:* {data.get('service')}\n• *User ID:* `{u_id}`\n• *Contact:* `{contact}`"
        await bot.send_message(ADMIN_ID, admin_alert, parse_mode="Markdown")
    except Exception:
        pass


# =========================================================
# PAYMENT PROOF SUBMISSION
# =========================================================

@dp.callback_query(F.data == "user_paid")
async def user_paid_click(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(PaymentForm.waiting_for_proof)
    await safe_edit(
        call,
        "💳 *Submit Payment Proof*\n\nAapne jo payment ki hai uski Screenshot ya UTR/Txn ID yahan chat me bhej dein:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="back_to_main")]])
    )

@dp.message(PaymentForm.waiting_for_proof)
async def receive_payment_proof(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    username = f"@{user.username}" if user.username else "N/A"

    admin_alert = (
        f"🚨 *NEW PAYMENT PROOF SUBMITTED!*\n\n"
        f"• *User:* {user.first_name}\n"
        f"• *User ID:* `{user.id}`\n"
        f"• *Username:* {username}\n\n"
        f"Quick Commands:\n"
        f"`/addbot {user.id} BotName 30`\n"
        f"`/extend {user.id} BotName 30`"
    )

    if message.photo:
        await bot.send_photo(ADMIN_ID, photo=message.photo[-1].file_id, caption=admin_alert, parse_mode="Markdown")
    else:
        await bot.send_message(ADMIN_ID, f"{admin_alert}\n\n*Proof Text:* {message.text}", parse_mode="Markdown")

    await message.answer("✅ *Payment Proof Received!*\n\nAdmin review karke service start kar dega.", reply_markup=main_menu())


# =========================================================
# ADMIN PANEL HANDLERS
# =========================================================

@dp.message(Command("admin"))
async def admin_panel_cmd(message: Message):
    if not is_admin(message.from_user.id): return
    await message.answer("👑 *Paraweb Admin Panel*", reply_markup=admin_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "admin_panel_open")
async def admin_panel_cb(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.clear()
    await safe_edit(call, "👑 *Paraweb Admin Panel*", reply_markup=admin_keyboard())


# --- USERS LIST FIX ---

@dp.callback_query(F.data == "admin_users_list")
async def admin_users_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()

    users = get_users()
    if not users:
        await safe_edit(call, "👥 Database me koi user saved nahi hai.", reply_markup=back_admin())
        return

    text = f"👥 *Total Registered Users:* `{len(users)}`\n\n*Recent Users List:*\n"
    for u in users[-15:]:
        u_id, username, fname = u[0], u[1], u[2]
        uname_text = f"@{username}" if username else "No Username"
        text += f"• {fname} | `{u_id}` | {uname_text}\n"

    await safe_edit(call, text, reply_markup=back_admin())


# --- LEADS LIST & SEARCH BY ID ---

@dp.callback_query(F.data == "admin_leads_list")
async def admin_leads_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    leads = get_leads()

    if not leads:
        await safe_edit(call, "📭 Koi leads nahi mili.", reply_markup=back_admin())
        return

    buttons = []
    for lead in leads[:10]:
        lead_id, u_id, service, _, _, _, _, _, status, _ = lead
        icon = "🟡" if status == "New" else ("🔵" if status == "Contacted" else ("⚙️" if status == "Working" else "✅"))
        buttons.append([InlineKeyboardButton(
            text=f"Lead #{lead_id} | {service} | {icon} {status}",
            callback_data=f"view_lead_{lead_id}"
        )])

    buttons.append([InlineKeyboardButton(text="🔍 Search Specific Lead ID", callback_data="admin_search_lead")])
    buttons.append([InlineKeyboardButton(text="⬅️ Back to Admin", callback_data="admin_panel_open")])
    
    await safe_edit(call, "📋 *Recent Leads Overview:*", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "admin_search_lead")
async def search_lead_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(AdminForm.search_lead_id)
    await safe_edit(call, "🔍 *Enter Lead ID Number:*\n\nType Lead ID (e.g. `1`, `5`):", reply_markup=back_admin())

@dp.message(AdminForm.search_lead_id)
async def process_lead_search(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    
    if not message.text.isdigit():
        await message.answer("❌ Numeric Lead ID bhejein.", reply_markup=back_admin())
        return

    lead_id = int(message.text)
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    lead = cursor.fetchone()
    conn.close()

    if not lead:
        await message.answer(f"❌ Lead #{lead_id} nahi mili!", reply_markup=back_admin())
        return

    _, u_id, service, bus, feat, budg, req, cont, status, created = lead

    text = (
        f"🔥 *LEAD DETAILS #{lead_id}*\n\n"
        f"• *User ID:* `{u_id}`\n"
        f"• *Service:* `{service}`\n"
        f"• *Business:* `{bus}`\n"
        f"• *Features:* `{feat}`\n"
        f"• *Budget:* `{budg}`\n"
        f"• *Contact:* `{cont}`\n"
        f"• *Requirement:* {req}\n"
        f"• *Status:* *{status}*\n"
        f"• *Date:* `{created}`\n\n"
        f"👇 *Update Status:* "
    )

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📞 Contacted", callback_data=f"set_st_{lead_id}_Contacted"),
                InlineKeyboardButton(text="⚙️ Working", callback_data=f"set_st_{lead_id}_Working"),
            ],
            [
                InlineKeyboardButton(text="✅ Done", callback_data=f"set_st_{lead_id}_Done"),
                InlineKeyboardButton(text="❌ Cancelled", callback_data=f"set_st_{lead_id}_Cancelled"),
            ],
            [InlineKeyboardButton(text="⬅️ Back to Admin", callback_data="admin_panel_open")]
        ]
    )
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("view_lead_"))
async def view_lead_cb(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    lead_id = int(call.data.replace("view_lead_", ""))
    
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    lead = cursor.fetchone()
    conn.close()

    if not lead:
        await call.answer("Lead nahi mili!", show_alert=True)
        return

    _, u_id, service, bus, feat, budg, req, cont, status, created = lead

    text = (
        f"🔥 *LEAD DETAILS #{lead_id}*\n\n"
        f"• *User ID:* `{u_id}`\n"
        f"• *Service:* `{service}`\n"
        f"• *Business:* `{bus}`\n"
        f"• *Budget:* `{budg}`\n"
        f"• *Contact:* `{cont}`\n"
        f"• *Requirement:* {req}\n"
        f"• *Status:* *{status}*\n"
        f"• *Date:* `{created}`\n\n"
        f"👇 *Update Status:* "
    )

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📞 Contacted", callback_data=f"set_st_{lead_id}_Contacted"),
                InlineKeyboardButton(text="⚙️ Working", callback_data=f"set_st_{lead_id}_Working"),
            ],
            [
                InlineKeyboardButton(text="✅ Done", callback_data=f"set_st_{lead_id}_Done"),
                InlineKeyboardButton(text="❌ Cancelled", callback_data=f"set_st_{lead_id}_Cancelled"),
            ],
            [InlineKeyboardButton(text="⬅️ Back to Admin", callback_data="admin_panel_open")]
        ]
    )
    await safe_edit(call, text, reply_markup=markup)

@dp.callback_query(F.data.startswith("set_st_"))
async def set_lead_status_cb(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    parts = call.data.split("_")
    lead_id, new_status = int(parts[2]), parts[3]
    update_status(lead_id, new_status)
    await call.answer(f"Status Updated to {new_status} ✅", show_alert=True)


# --- HOSTED BOTS & BROADCAST ---

@dp.callback_query(F.data == "admin_bots_list")
async def admin_bots_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()

    try:
        conn = sqlite3.connect("hosting.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, bot_name, days, expiry_date FROM user_bots")
        bots = cursor.fetchall()
        conn.close()
    except Exception:
        bots = []

    if not bots:
        await safe_edit(call, "🤖 *Hosted Bots*\n\nDatabase me koi bot active nahi hai.", reply_markup=back_admin())
        return

    text = f"🤖 *Total Hosted Bots:* `{len(bots)}`\n\n"
    for b in bots:
        u_id, b_name, days, exp = b
        try:
            exp_dt = datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
            rem = (exp_dt - datetime.now()).days
            tag = "🟢 Active" if rem >= 0 else "🔴 Expired"
        except Exception:
            rem, tag = 0, "❓"
        text += f"• *{b_name}* | User: `{u_id}`\n  *Status:* {tag} ({rem} days left)\n  *Expiry:* `{exp[:10]}`\n\n"

    await safe_edit(call, text, reply_markup=back_admin())

@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(AdminForm.broadcast_message)
    await safe_edit(call, "📢 *Broadcast System*\n\nSend any text message or photo to broadcast to all users.", reply_markup=back_admin())

@dp.message(AdminForm.broadcast_message)
async def process_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()

    users = get_users()
    sent, failed = 0, 0
    for u in users:
        u_id = u[0]
        try:
            if message.photo:
                await bot.send_photo(u_id, photo=message.photo[-1].file_id, caption=message.caption or "", parse_mode="Markdown")
            else:
                await message.copy_to(chat_id=u_id)
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            failed += 1

    await message.answer(f"✅ *Broadcast Finished!*\n\n• Sent: `{sent}`\n• Failed: `{failed}`", parse_mode="Markdown")


# =========================================================
# HOSTING COMMANDS (ADD, EXTEND (+/-), SUBDAYS, DELBOT, GIFTALL)
# =========================================================

@dp.message(Command("addbot"))
async def admin_add_bot(message: Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()[1:]
        user_id, bot_name, days = int(args[0]), args[1], int(args[2])
        success, msg = add_user_bot(user_id, bot_name, days)
        await message.answer(msg, parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Format: `/addbot <user_id> <bot_name> <days>`", parse_mode="Markdown")

@dp.message(Command("extend"))
async def admin_extend_bot(message: Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()[1:]
        user_id, bot_name, days = int(args[0]), args[1], int(args[2])
        success, msg = extend_user_bot(user_id, bot_name, days)
        await message.answer(msg, parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Format: `/extend <user_id> <bot_name> <days>`\n*(Negative days ke liye: e.g. -5)*", parse_mode="Markdown")

@dp.message(Command("subdays"))
async def admin_sub_days(message: Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()[1:]
        user_id, bot_name, days = int(args[0]), args[1], abs(int(args[2]))
        success, msg = extend_user_bot(user_id, bot_name, -days)
        await message.answer(f"📉 `{days}` Days deduct ho gaye hain!\n\n{msg}", parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Format: `/subdays <user_id> <bot_name> <days>`", parse_mode="Markdown")

@dp.message(Command("delbot"))
async def admin_del_bot(message: Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()[1:]
        user_id, bot_name = int(args[0]), args[1]

        conn = sqlite3.connect("hosting.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_bots WHERE user_id = ? AND bot_name = ?", (user_id, bot_name))
        rows = cursor.rowcount
        conn.commit()
        conn.close()

        if rows > 0:
            await message.answer(f"🗑️ Bot `{bot_name}` delete ho gaya hai.", parse_mode="Markdown")
        else:
            await message.answer("❌ Bot nahi mila.", parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Format: `/delbot <user_id> <bot_name>`", parse_mode="Markdown")

@dp.message(Command("giftall"))
async def admin_gift_all(message: Message):
    if not is_admin(message.from_user.id): return
    try:
        bonus_days = int(message.text.split()[1])
        conn = sqlite3.connect("hosting.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, bot_name, expiry_date FROM user_bots")
        bots = cursor.fetchall()

        now = datetime.now()
        count = 0
        for u_id, b_name, exp_str in bots:
            try:
                exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
                base_dt = exp_dt if exp_dt > now else now
                new_exp = (base_dt + timedelta(days=bonus_days)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("UPDATE user_bots SET expiry_date = ? WHERE user_id = ? AND bot_name = ?", (new_exp, u_id, b_name))
                count += 1
            except Exception: pass
        conn.commit()
        conn.close()

        await message.answer(f"🎉 Total `{count}` bots me *+{bonus_days} Days* add ho gaye!", parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Format: `/giftall <days>`", parse_mode="Markdown")

@dp.message(Command("mybots"))
@dp.message(Command("status"))
@dp.callback_query(F.data == "check_my_bots")
async def check_user_bots_handler(event):
    user_id = event.from_user.id
    chat_id = event.message.chat.id if isinstance(event, CallbackQuery) else event.chat.id
    if isinstance(event, CallbackQuery): await event.answer()

    bots = get_user_bots(user_id)
    if not bots:
        await bot.send_message(chat_id, "❌ Aapka koi bot active nahi hai.")
        return

    for b in bots:
        _, b_name, _, _, exp_date = b
        exp_dt = datetime.strptime(exp_date, "%Y-%m-%d %H:%M:%S")
        rem = (exp_dt - datetime.now()).days
        msg = f"🤖 *Bot:* `{b_name}`\n📊 *Status:* {'🟢 Active' if rem >= 0 else '🔴 Expired'} ({rem} days left)\n📅 *Expiry:* `{exp_date[:10]}`"
        await bot.send_message(chat_id, msg, parse_mode="Markdown")

@dp.callback_query(F.data == "my_projects")
async def my_projects_cb(call: CallbackQuery):
    await call.answer()
    leads = get_user_leads(call.from_user.id)
    if not leads:
        await safe_edit(call, "📭 Aapka koi active project nahi hai.", reply_markup=main_menu())
        return
    lead = leads[0]
    await safe_edit(call, f"📊 *Your Project Status*\n\n• Service: *{lead[2]}*\n• Status: *{lead[8]}*", reply_markup=main_menu())

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await safe_edit(call, "🚀 *Main Menu*", reply_markup=main_menu())


# =========================================================
# MAIN EXECUTION
# =========================================================

async def main():
    init_main_db()
    init_hosting_db()
    print("🚀 Paraweb Full Integrated Bot Running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
