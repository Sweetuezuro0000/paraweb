import asyncio
import os
import sqlite3
from threading import Thread
from datetime import datetime

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

# Local Database Modules
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
    get_expiring_users,
    mark_notified,
)

from pdf_generator import generate_pdf
from payment import send_payment

from datetime import datetime, timedelta
# =========================================================
# CONFIGURATION
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
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@YourAdminUsername")


# =========================================================
# FLASK KEEP-ALIVE SERVER (FOR RENDER)
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Paraweb Bot Server Active!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    thread = Thread(target=run_web, daemon=True)
    thread.start()


# =========================================================
# BOT & DISPATCHER INIT
# =========================================================

bot = Bot(TOKEN)
dp = Dispatcher()


# =========================================================
# STATES (FSM)
# =========================================================

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
            [InlineKeyboardButton(text="🚀 Start Project", callback_data="project_start")],
            [
                InlineKeyboardButton(text="🌐 Website", callback_data="service_website"),
                InlineKeyboardButton(text="📱 App", callback_data="service_app"),
            ],
            [InlineKeyboardButton(text="🤖 Telegram Bot", callback_data="service_bot")],
            [
                InlineKeyboardButton(text="📊 My Project", callback_data="my_project"),
                InlineKeyboardButton(text="🖥️ My Hosted Bots", callback_data="check_my_bots"),
            ],
            [InlineKeyboardButton(text="💳 Submit Payment Proof", callback_data="user_paid")],
        ]
    )

def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 All Leads List", callback_data="admin_leads_list"),
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


# =========================================================
# HELPERS
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def safe_edit(call: CallbackQuery, text: str, reply_markup=None, parse_mode="Markdown"):
    try:
        await call.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest:
        pass

def valid_phone(text: str) -> bool:
    cleaned = text.replace(" ", "").replace("-", "").replace("+", "")
    return cleaned.isdigit() and 10 <= len(cleaned) <= 15


# =========================================================
# START COMMAND
# =========================================================

@dp.message(CommandStart())
async def start(message: Message):
    save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = f"🚀 *Welcome to {BRAND}*\n\nWe build Websites, Mobile Apps & Telegram Bots.\nChoose an option below 👇"
    await message.answer(text, reply_markup=main_menu(), parse_mode="Markdown")


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


# --- 1. LEADS MANAGEMENT (LIST & ID SEARCH) ---

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

    buttons.append([InlineKeyboardButton(text="🔍 Search Specific ID", callback_data="admin_search_lead")])
    buttons.append([InlineKeyboardButton(text="⬅️ Back to Admin", callback_data="admin_panel_open")])
    
    await safe_edit(call, "📋 *Recent Leads Overview:*", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "admin_search_lead")
async def search_lead_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(AdminForm.search_lead_id)
    await safe_edit(call, "🔍 *Enter Lead ID:*\n\nJis Lead ID ki details dekhna chahte hain wo number type karke bhejein (e.g. `1`, `5`):", reply_markup=back_admin())

@dp.message(AdminForm.search_lead_id)
async def process_lead_search(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    
    if not message.text.isdigit():
        await message.answer("❌ Invalid Lead ID! Sirf numeric ID bhejein.", reply_markup=back_admin())
        return

    lead_id = int(message.text)
    await show_lead_details(message.chat.id, lead_id)

async def show_lead_details(chat_id: int, lead_id: int):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    lead = cursor.fetchone()
    conn.close()

    if not lead:
        await bot.send_message(chat_id, f"❌ Lead #{lead_id} nahi mili!", reply_markup=back_admin())
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
        f"• *Current Status:* *{status}*\n"
        f"• *Date:* `{created}`\n\n"
        f"👇 *Change Status:* "
    )

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📞 Contacted", callback_data=f"set_status_{lead_id}_Contacted"),
                InlineKeyboardButton(text="⚙️ Working", callback_data=f"set_status_{lead_id}_Working"),
            ],
            [
                InlineKeyboardButton(text="✅ Done", callback_data=f"set_status_{lead_id}_Done"),
                InlineKeyboardButton(text="❌ Cancelled", callback_data=f"set_status_{lead_id}_Cancelled"),
            ],
            [InlineKeyboardButton(text="⬅️ Back to Admin", callback_data="admin_panel_open")]
        ]
    )
    await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

@dp.callback_query(F.data.startswith("view_lead_"))
async def view_lead_cb(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    lead_id = int(call.data.replace("view_lead_", ""))
    await show_lead_details(call.message.chat.id, lead_id)

@dp.callback_query(F.data.startswith("set_status_"))
async def set_lead_status_cb(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    parts = call.data.split("_")
    lead_id = int(parts[2])
    new_status = parts[3]

    update_status(lead_id, new_status)
    await call.answer(f"Status Updated: {new_status} ✅", show_alert=True)
    await show_lead_details(call.message.chat.id, lead_id)


# --- 2. HOSTED BOTS MANAGEMENT ---

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
        await safe_edit(call, "🤖 *Hosted Bots*\n\nDatabase me abhi koi bot host nahi hai.", reply_markup=back_admin())
        return

    text = f"🤖 *Total Hosted Bots:* `{len(bots)}`\n\n"
    for b in bots:
        u_id, b_name, days, exp = b
        try:
            exp_dt = datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
            rem = (exp_dt - datetime.now()).days
            tag = "🟢 Active" if rem >= 0 else "🔴 Expired"
        except Exception:
            rem, tag = 0, "❓ Unknown"

        text += f"• *Bot:* `{b_name}` | *User:* `{u_id}`\n  *Status:* {tag} ({rem} days remaining)\n  *Expiry:* `{exp[:10]}`\n\n"

    await safe_edit(call, text, reply_markup=back_admin())


# --- 3. USERS DETAILS VIEW ---

@dp.callback_query(F.data == "admin_users_list")
async def admin_users_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()

    users = get_users()
    if not users:
        await safe_edit(call, "👥 Koi users nahi mile.", reply_markup=back_admin())
        return

    text = f"👥 *Total Registered Users:* `{len(users)}`\n\n*Recent Joined Users:*\n"
    for u in users[-10:]:
        u_id, username, fname, _ = u
        uname_text = f"@{username}" if username else "No Username"
        text += f"• {fname} | `{u_id}` | {uname_text}\n"

    await safe_edit(call, text, reply_markup=back_admin())


# --- 4. BROADCAST SYSTEM ---

@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await call.answer()
    await state.set_state(AdminForm.broadcast_message)
    await safe_edit(call, "📢 *Broadcast System*\n\nSend any text message or photo/banner to broadcast to all users.\n\n_Send /admin to cancel._", reply_markup=back_admin())

@dp.message(AdminForm.broadcast_message)
async def process_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()

    users = get_users()
    sent, failed = 0, 0
    status_msg = await message.answer("⏳ Broadcast in progress...")

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

    await status_msg.edit_text(f"✅ *Broadcast Finished!*\n\n• Successfully Sent: `{sent}`\n• Failed/Blocked: `{failed}`", parse_mode="Markdown")


# =========================================================
# USER PAYMENT PROOF SUBMISSION ("SUBMIT PAYMENT PROOF")
# =========================================================

@dp.callback_query(F.data == "user_paid")
async def user_paid_click(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(PaymentForm.waiting_for_proof)
    await safe_edit(
        call,
        "💳 *Submit Payment Proof / Screenshot*\n\nAapne jo payment ki hai uski Screenshot ya Transaction ID yahan chat me send karein:",
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
        f"Quick Extend Command:\n`/extend {user.id} BotName 30`"
    )

    if message.photo:
        await bot.send_photo(ADMIN_ID, photo=message.photo[-1].file_id, caption=admin_alert, parse_mode="Markdown")
    else:
        await bot.send_message(ADMIN_ID, f"{admin_alert}\n\n*Proof Text:* {message.text}", parse_mode="Markdown")

    await message.answer("✅ *Payment Proof Received!*\n\nAdmin aapki payment verify karke service active kar dega.", reply_markup=main_menu())

# =========================================================
# NEW: DELETE BOT COMMAND
# =========================================================

@dp.message(Command("delbot"))
async def admin_del_bot(message: Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()[1:]
        user_id = int(args[0])
        bot_name = args[1]

        conn = sqlite3.connect("hosting.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_bots WHERE user_id = ? AND bot_name = ?", (user_id, bot_name))
        rows = cursor.rowcount
        conn.commit()
        conn.close()

        if rows > 0:
            await message.answer(f"🗑️ Bot `{bot_name}` (User ID: `{user_id}`) database se successfully delete ho gaya hai.", parse_mode="Markdown")
            try:
                await bot.send_message(user_id, f"⚠️ Aapka bot `{bot_name}` admin dwara system se remove kar diya gaya hai.", parse_mode="Markdown")
            except Exception:
                pass
        else:
            await message.answer(f"❌ Bot `{bot_name}` user `{user_id}` ke paas nahi mila.", parse_mode="Markdown")

    except Exception:
        await message.answer("⚠️ *Format:* `/delbot <user_id> <bot_name>`\nExample: `/delbot 987654321 MyBot`", parse_mode="Markdown")


# =========================================================
# NEW: GIFT / BONUS DAYS TO ALL USERS (BULK)
# =========================================================

@dp.message(Command("giftall"))
async def admin_gift_all(message: Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()[1:]
        bonus_days = int(args[0])

        conn = sqlite3.connect("hosting.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, bot_name, expiry_date FROM user_bots")
        bots = cursor.fetchall()

        if not bots:
            await message.answer("📭 Hosting database me koi bot nahi mila.", parse_mode="Markdown")
            conn.close()
            return

        updated_count = 0
        now = datetime.now()

        for u_id, b_name, exp_str in bots:
            try:
                exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
                # Agar already expire ho chuka hai toh aaj se naye din milenge, nahi toh current expiry me add honge
                base_dt = exp_dt if exp_dt > now else now
                new_exp = base_dt + timedelta(days=bonus_days)
                new_exp_str = new_exp.strftime("%Y-%m-%d %H:%M:%S")

                cursor.execute("UPDATE user_bots SET expiry_date = ?, notified = 0 WHERE user_id = ? AND bot_name = ?", (new_exp_str, u_id, b_name))
                updated_count += 1

                # Send Notification to User
                try:
                    alert_text = (
                        f"🎁 *SPECIAL GIFT FROM PARAWEB!*\n\n"
                        f"Admin ne aapke bot `{b_name}` me *+{bonus_days} Days* ka bonus add kiya hai! 🎉\n\n"
                        f"📅 *Nayi Expiry Date:* `{new_exp_str[:10]}`"
                    )
                    await bot.send_message(u_id, alert_text, parse_mode="Markdown")
                except Exception:
                    pass

            except Exception as e:
                print(f"Bonus error for {u_id}: {e}")

        conn.commit()
        conn.close()

        await message.answer(f"🎉 *Success!* Total `{updated_count}` bots ko *+{bonus_days} Days* ka gift add ho gaya hai aur notification bhej di gayi hai!", parse_mode="Markdown")

    except Exception:
        await message.answer("⚠️ *Format:* `/giftall <days>`\nExample: `/giftall 7`", parse_mode="Markdown")
# =========================================================
# USER HOSTING & PROJECT TRACKER
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
        await message.answer("⚠️ Format: `/extend <user_id> <bot_name> <days>`", parse_mode="Markdown")

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

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await safe_edit(call, "🚀 *Main Menu*", reply_markup=main_menu())


# =========================================================
# MAIN START
# =========================================================

async def main():
    init_main_db()
    init_hosting_db()
    print("🚀 Fixed Paraweb Bot Started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
