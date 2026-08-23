import asyncio
import os
import sqlite3
from threading import Thread
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
)

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
    raise ValueError("BOT_TOKEN ya ADMIN_ID missing hai!")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise ValueError("ADMIN_ID numeric integer honi chahiye!")

BRAND = "Paraweb"


# =========================================================
# FLASK SERVER
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
            [InlineKeyboardButton(text="⬅️ Back to Main Menu", callback_data="back_to_main")]
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
        await call.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    except TelegramBadRequest:
        pass


# =========================================================
# START COMMAND
# =========================================================

@dp.message(CommandStart())
async def start(message: Message):
    save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    text = f"🚀 *Welcome to {BRAND}*\n\nWe design & develop Websites, Mobile Apps, and Telegram Bots.\n\nSelect an option to get started 👇"
    await message.answer(text, reply_markup=main_menu(), parse_mode="Markdown")


# =========================================================
# PROJECT FORM & AUTOMATED QUOTATION FLOW
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
    await message.answer("💡 *Step 2/5:* Aapko kya-kya main features chahiye? (Short details likhein)")

@dp.message(ProjectForm.features)
async def process_features(message: Message, state: FSMContext):
    await state.update_data(features=message.text)
    await state.set_state(ProjectForm.budget)
    await message.answer("💰 *Step 3/5:* Aapka expected budget kitna hai? (e.g. ₹2000 - ₹5000 / $50 - $100)")

@dp.message(ProjectForm.budget)
async def process_budget(message: Message, state: FSMContext):
    await state.update_data(budget=message.text)
    await state.set_state(ProjectForm.requirement)
    await message.answer("📝 *Step 4/5:* Koi aur specific requirement ya timeline?")

@dp.message(ProjectForm.requirement)
async def process_req(message: Message, state: FSMContext):
    await state.update_data(requirement=message.text)
    await state.set_state(ProjectForm.contact)
    await message.answer("📞 *Step 5/5:* Aapka Contact Number ya WhatsApp Number kya hai?")

@dp.message(ProjectForm.contact)
async def process_contact(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    
    contact = message.text
    u_id = message.from_user.id
    
    # Save Lead in Database
    save_lead(
        user_id=u_id,
        service=data.get("service"),
        business=data.get("business"),
        features=data.get("features"),
        budget=data.get("budget"),
        requirement=data.get("requirement"),
        contact=contact
    )

    # Generate Instant Quotation Summary
    quotation_text = (
        f"📄 *PARAWEB OFFICIAL QUOTATION*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Service:* {data.get('service')}\n"
        f"• *Business:* {data.get('business')}\n"
        f"• *Budget Range:* {data.get('budget')}\n"
        f"• *Contact:* `{contact}`\n"
        f"• *Status:* 🟡 Quotation Generated / Pending Review\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ *Next Steps:* Project confirm karne ke liye payment karein aur niche button se *Payment Proof* submit karein."
    )

    pay_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Submit Payment Proof", callback_data="user_paid")],
            [InlineKeyboardButton(text="🚀 Return to Main Menu", callback_data="back_to_main")]
        ]
    )

    await message.answer(quotation_text, reply_markup=pay_kb, parse_mode="Markdown")
    
    # Notify Admin About New Lead
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
        "💳 *Submit Payment Proof*\n\nAapne jo payment ki hai uski Screenshot ya Transaction ID/UTR Number chat me bhejein:",
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
        f"Quick Action Commands:\n"
        f"`/addbot {user.id} BotName 30`\n"
        f"`/extend {user.id} BotName 30`"
    )

    if message.photo:
        await bot.send_photo(ADMIN_ID, photo=message.photo[-1].file_id, caption=admin_alert, parse_mode="Markdown")
    else:
        await bot.send_message(ADMIN_ID, f"{admin_alert}\n\n*Details:* {message.text}", parse_mode="Markdown")

    await message.answer("✅ *Payment Proof Received!*\n\nAdmin 10-15 mins me review karke aapki service/bot activate kar dega.", reply_markup=main_menu())


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


# --- USERS DETAIL FIX ---

@dp.callback_query(F.data == "admin_users_list")
async def admin_users_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()

    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, first_name FROM users ORDER BY id DESC")
        users = cursor.fetchall()
        conn.close()
    except Exception as e:
        users = []

    if not users:
        await safe_edit(call, "👥 Database me abhi koi user saved nahi hai.", reply_markup=back_admin())
        return

    text = f"👥 *Total Registered Users:* `{len(users)}`\n\n*Recent Users List:*\n"
    for u in users[:15]:
        u_id, username, fname = u
        uname_text = f"@{username}" if username else "No Username"
        text += f"• {fname} | `{u_id}` | {uname_text}\n"

    await safe_edit(call, text, reply_markup=back_admin())


# --- LEADS SEARCH & MANAGEMENT ---

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
        await message.answer("❌ Direct numeric Lead ID bhejein.", reply_markup=back_admin())
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
    await safe_edit(call, "📢 *Broadcast System*\n\nSend any message or photo to broadcast to all users.", reply_markup=back_admin())

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
# HOSTING COMMANDS (PLUS & MINUS DAYS SUPPORT)
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
        
        # Extends or Reduces Days automatically based on + / - value
        success, msg = extend_user_bot(user_id, bot_name, days)
        await message.answer(msg, parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Format: `/extend <user_id> <bot_name> <days>`\n*(Tip: Days minus karne ke liye negative number dalein e.g. -5)*", parse_mode="Markdown")

@dp.message(Command("subdays"))
async def admin_sub_days(message: Message):
    if not is_admin(message.from_user.id): return
    try:
        args = message.text.split()[1:]
        user_id, bot_name, days = int(args[0]), args[1], abs(int(args[2]))
        # Deduct days
        success, msg = extend_user_bot(user_id, bot_name, -days)
        await message.answer(f"📉 `{days}` Days deduct kar diye gaye hain!\n\n{msg}", parse_mode="Markdown")
    except Exception:
        await message.answer("⚠️ Format: `/subdays <user_id> <bot_name> <days>`\nExample: `/subdays 987654321 ShopBot 5`", parse_mode="Markdown")

@dp.message(Command("mybots"))
@dp.message(Command("status"))
@dp.callback_query(F.data == "check_my_bots")
async def check_user_bots_handler(event):
    user_id = event.from_user.id
    chat_id = event.message.chat.id if isinstance(event, CallbackQuery) else event.chat.id
    if isinstance(event, CallbackQuery): await event.answer()

    bots = get_user_bots(user_id)
    if not bots:
        await bot.send_message(chat_id, "❌ Aapka koi hosted bot active nahi hai.")
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
        await safe_edit(call, "📭 Aapka koi active project inquiry nahi mili.", reply_markup=main_menu())
        return
    
    lead = leads[0]
    await safe_edit(call, f"📊 *Your Project Status*\n\n• *Service:* {lead[2]}\n• *Status:* *{lead[8]}*", reply_markup=main_menu())

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
    print("🚀 Paraweb Full Fixed Bot Running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
