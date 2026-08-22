import asyncio
import os
import random
from threading import Thread
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
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

# Aapki Purani Database aur Manager Files
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

# Hosting Management SQLite Functions
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


# =========================================================
# CONFIG
# =========================================================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_RAW = os.getenv("ADMIN_ID")

if not TOKEN:
    raise ValueError("BOT_TOKEN missing in environment")

if not ADMIN_ID_RAW:
    raise ValueError("ADMIN_ID missing in environment")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise ValueError("ADMIN_ID must be a Telegram numeric ID")

BRAND = "Paraweb"
LOG_CHANNEL_ID = -1004463199472
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@YourAdminUsername")


# =========================================================
# FLASK / RENDER KEEP ALIVE
# =========================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Paraweb Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    thread = Thread(target=run_web, daemon=True)
    thread.start()


# =========================================================
# BOT & DISPATCHER
# =========================================================

bot = Bot(TOKEN)
dp = Dispatcher()


# =========================================================
# TEXTS & STATES
# =========================================================

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

class ProjectForm(StatesGroup):
    service = State()
    business = State()
    features = State()
    budget = State()
    requirement = State()
    contact = State()

class AdminForm(StatesGroup):
    broadcast_message = State()


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
                InlineKeyboardButton(text="💡 Idea Generator", callback_data="idea"),
                InlineKeyboardButton(text="🧠 Assistant Mode", callback_data="mode"),
            ],
            [InlineKeyboardButton(text="🔮 Future Preview", callback_data="future")],
            [
                InlineKeyboardButton(text="📊 My Project", callback_data="my_project"),
                InlineKeyboardButton(text="🖥️ My Hosted Bots", callback_data="check_my_bots"),
            ],
        ]
    )

def service_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌐 Website", callback_data="service_website"),
                InlineKeyboardButton(text="📱 App", callback_data="service_app"),
            ],
            [InlineKeyboardButton(text="🤖 Telegram Bot", callback_data="service_bot")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back")],
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
                InlineKeyboardButton(text="🍔 Restaurant", callback_data="business_restaurant"),
            ],
            [
                InlineKeyboardButton(text="🎓 Education", callback_data="business_education"),
                InlineKeyboardButton(text="🏢 Company", callback_data="business_company"),
            ],
            [InlineKeyboardButton(text="💡 Startup", callback_data="business_startup")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back")],
        ]
    )

def feature_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Payment", callback_data="feature_payment"),
                InlineKeyboardButton(text="👥 Login", callback_data="feature_login"),
            ],
            [
                InlineKeyboardButton(text="📊 Dashboard", callback_data="feature_dashboard"),
                InlineKeyboardButton(text="📦 Products", callback_data="feature_product"),
            ],
            [
                InlineKeyboardButton(text="🔔 Notifications", callback_data="feature_notifications"),
                InlineKeyboardButton(text="🤖 AI", callback_data="feature_ai"),
            ],
            [InlineKeyboardButton(text="➡️ Continue", callback_data="feature_done")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back")],
        ]
    )

def budget_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="₹5k - ₹10k", callback_data="budget_5")],
            [InlineKeyboardButton(text="₹10k - ₹25k", callback_data="budget_10")],
            [InlineKeyboardButton(text="₹25k+", callback_data="budget_25")],
            [InlineKeyboardButton(text="💬 Discuss", callback_data="budget_discuss")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back")],
        ]
    )

PERSONALITIES = {
    "developer": "👨‍💻 *Developer Mode Activated*\n\nFocus: Technology, Features, Architecture.",
    "business": "💼 *Business Mode Activated*\n\nFocus: Growth, Customers, Revenue, Strategy.",
    "creative": "🎨 *Creative Mode Activated*\n\nFocus: Design, Ideas, User Experience.",
}

def personality_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👨‍💻 Developer", callback_data="mode_developer")],
            [InlineKeyboardButton(text="💼 Business", callback_data="mode_business")],
            [InlineKeyboardButton(text="🎨 Creative", callback_data="mode_creative")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back")],
        ]
    )


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def typing(message: Message):
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
        await asyncio.sleep(random.uniform(0.5, 1.0))
    except Exception as e:
        print(f"Typing error: {e}")

async def safe_edit(call: CallbackQuery, text: str, reply_markup=None, parse_mode=None):
    try:
        await call.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            print(f"Edit error: {e}")

def valid_phone(text: str) -> bool:
    cleaned = text.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    digits = cleaned[1:] if cleaned.startswith("+") else cleaned
    return digits.isdigit() and 10 <= len(digits) <= 15

def calculate_score(data):
    score = 50
    if data.get("features"): score += 20
    if data.get("budget"): score += 15
    if len(data.get("requirement", "")) > 50: score += 15
    return min(score, 100)

def recommendation(service, business):
    result = {
        "website": "🌐 *Website Recommendation*\n✓ Modern responsive design\n✓ SEO optimization",
        "app": "📱 *App Recommendation*\n✓ User accounts\n✓ Push notifications",
        "bot": "🤖 *Bot Recommendation*\n✓ Automation\n✓ Customer support",
    }
    return result.get(service, "Custom solution recommended")


# =========================================================
# START COMMAND
# =========================================================

@dp.message(CommandStart())
async def start(message: Message):
    await typing(message)
    try:
        save_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    except Exception as e:
        print(f"Save user error: {e}")

    await message.answer(WELCOME_TEXT, reply_markup=main_menu(), parse_mode="Markdown")

    try:
        user = message.from_user
        username = f"@{user.username}" if user.username else "None"
        log_text = f"🆕 *New User Started!*\n👤 *Name:* {user.first_name}\n🆔 *ID:* `{user.id}`\n🌐 *Username:* {username}"
        await bot.send_message(chat_id=LOG_CHANNEL_ID, text=log_text, parse_mode="Markdown")
    except Exception as e:
        print(f"Log channel error: {e}")


# =========================================================
# HOSTING MANAGEMENT (ADMIN & USER COMMANDS)
# =========================================================

# Admin: Add New Bot Hosting -> /addbot <user_id> <bot_name> <days>
@dp.message(Command("addbot"))
async def admin_add_bot(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Ye command sirf Admin use kar sakta hai.")
        return

    try:
        args = message.text.split()[1:]
        user_id = int(args[0])
        bot_name = args[1]
        days = int(args[2])

        success, msg = add_user_bot(user_id, bot_name, days)
        await message.answer(msg, parse_mode="Markdown")

    except (IndexError, ValueError):
        await message.answer("⚠️ *Wrong Format!*\n\nUse: `/addbot <user_id> <bot_name> <days>`\nExample: `/addbot 987654321 MyBot 30`", parse_mode="Markdown")


# Admin: Extend Bot Hosting -> /extend <user_id> <bot_name> <days>
@dp.message(Command("extend"))
async def admin_extend_bot(message: Message):
    if not is_admin(message.from_user.id):
        return

    try:
        args = message.text.split()[1:]
        user_id = int(args[0])
        bot_name = args[1]
        days = int(args[2])

        success, msg = extend_user_bot(user_id, bot_name, days)
        await message.answer(msg, parse_mode="Markdown")

        if success:
            try:
                await bot.send_message(user_id, f"🎉 *Subscription Updated!*\nAapka bot `{bot_name}` successfully *{days} din* ke liye extend ho gaya hai!", parse_mode="Markdown")
            except Exception:
                pass

    except (IndexError, ValueError):
        await message.answer("⚠️ *Wrong Format!*\n\nUse: `/extend <user_id> <bot_name> <days>`", parse_mode="Markdown")


# User: View Hosted Bots Status -> /mybots or /status
@dp.message(Command("mybots"))
@dp.message(Command("status"))
async def show_user_hosting_status(message: Message):
    await display_user_bots(message.from_user.id, message.chat.id)


@dp.callback_query(F.data == "check_my_bots")
async def callback_check_my_bots(call: CallbackQuery):
    await call.answer()
    await display_user_bots(call.from_user.id, call.message.chat.id)


async def display_user_bots(user_id: int, chat_id: int):
    bots = get_user_bots(user_id)
    if not bots:
        await bot.send_message(chat_id, f"❌ Aapka koi bhi bot {BRAND} server par host nahi hai.")
        return

    for b in bots:
        b_id, b_name, days, price, exp_date = b
        exp_dt = datetime.strptime(exp_date, "%Y-%m-%d %H:%M:%S")
        remaining_days = (exp_dt - datetime.now()).days

        status_tag = f"🟢 Active ({remaining_days} days left)" if remaining_days >= 0 else "🔴 Expired"

        info_msg = (
            f"🤖 *Bot Name:* `{b_name}`\n"
            f"📊 *Status:* {status_tag}\n"
            f"📅 *Expiry Date:* `{exp_date[:10]}`\n"
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔄 Extend / Renew Plan", callback_data=f"renew_{b_name}")]]
        )
        await bot.send_message(chat_id, info_msg, parse_mode="Markdown", reply_markup=markup)


# Callbacks for Hosting Extension Request
@dp.callback_query(F.data.startswith("renew_"))
async def handle_renew_click(call: CallbackQuery):
    await call.answer()
    bot_name = call.data.replace("renew_", "")

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="7 Days - ₹19", callback_data=f"plan_7_{bot_name}")],
            [InlineKeyboardButton(text="14 Days - ₹35", callback_data=f"plan_14_{bot_name}")],
            [InlineKeyboardButton(text="30 Days - ₹59", callback_data=f"plan_30_{bot_name}")],
        ]
    )
    await safe_edit(call, f"💳 `{bot_name}` ke liye Plan select karein:", reply_markup=markup, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("plan_"))
async def handle_plan_select(call: CallbackQuery):
    await call.answer("Request processing...")
    parts = call.data.split("_")
    days = int(parts[1])
    bot_name = parts[2]
    user_id = call.from_user.id

    await call.message.answer(
        f"➡️ `{bot_name}` (Plan: {days} Days) ke renewal ke liye payment karke Admin ko screenshot bhejein.\n\n"
        f"👤 *Admin:* {ADMIN_USERNAME}",
        parse_mode="Markdown"
    )

    admin_alert = (
        f"🔔 *[{BRAND}] Renewal Requested!*\n\n"
        f"• *User ID:* `{user_id}`\n"
        f"• *Bot Name:* `{bot_name}`\n"
        f"• *Plan Selected:* {days} Days\n\n"
        f"Approval ke liye command:\n"
        f"`/extend {user_id} {bot_name} {days}`"
    )
    await bot.send_message(ADMIN_ID, admin_alert, parse_mode="Markdown")


# Auto Expiry Alert Async Task
async def hosting_expiry_checker():
    while True:
        try:
            expiring_records = get_expiring_users()
            for rec in expiring_records:
                rec_id, u_id, b_name, exp_date = rec
                alert_msg = (
                    f"⚠️ *[{BRAND}] Hosting Expiry Warning!*\n\n"
                    f"Aapka bot `{b_name}` expire hone wala hai.\n"
                    f"📅 *Expiry Date:* `{exp_date[:10]}`\n\n"
                    f"Renew karne ke liye `/mybots` run karein."
                )
                try:
                    await bot.send_message(u_id, alert_msg, parse_mode="Markdown")
                    mark_notified(rec_id)
                except Exception as e:
                    print(f"Alert sending failed for {u_id}: {e}")
        except Exception as e:
            print(f"Error in expiry checker task: {e}")

        await asyncio.sleep(3600)  # Har 1 ghante me check karega


# =========================================================
# EXISTING PROJECT & SERVICES FLOW
# =========================================================

@dp.callback_query(F.data == "project_start")
async def project_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await safe_edit(call, "🔥 *Project Assistant Activated*\n\nFirst choose what you want to build:", reply_markup=service_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("service_"))
async def service_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    service = call.data.replace("service_", "")
    names = {"website": "🌐 Website Development", "app": "📱 Mobile App Development", "bot": "🤖 Telegram Bot Development"}
    await state.update_data(service=service, features=[])
    
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Continue", callback_data=f"continue_{service}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back")]
        ]
    )
    await safe_edit(call, f"✅ *Selected:*\n\n{names.get(service, service)}\n\nGreat choice 🚀\nNow we will understand your requirements.", reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("continue_"))
async def continue_project(call: CallbackQuery, state: FSMContext):
    await call.answer()
    service = call.data.replace("continue_", "")
    await state.update_data(service=service, features=[])
    await state.set_state(ProjectForm.business)
    await safe_edit(call, "🔥 *Great!*\n\nTell us about your business.\nChoose category 👇", reply_markup=business_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("business_"))
async def business_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    business = call.data.replace("business_", "")
    await state.update_data(business=business, features=[])
    await state.set_state(ProjectForm.features)
    await safe_edit(call, "⚙️ *What features do you need?*\n\nSelect all required features.\nThen press Continue 👇", reply_markup=feature_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("feature_"))
async def feature_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    feature = call.data.replace("feature_", "")

    if feature == "done":
        data = await state.get_data()
        if not data.get("features"):
            await call.answer("Please select at least one feature.", show_alert=True)
            return
        await state.set_state(ProjectForm.budget)
        await safe_edit(call, "💰 *What is your approximate budget?*", reply_markup=budget_keyboard(), parse_mode="Markdown")
        return

    data = await state.get_data()
    features = data.get("features", [])
    if feature in features:
        await call.answer("Already selected ✅", show_alert=False)
        return
    features.append(feature)
    await state.update_data(features=features)
    await call.answer(f"Added: {feature} ✅")

@dp.callback_query(F.data.startswith("budget_"))
async def budget_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    budget = call.data.replace("budget_", "")
    budget_names = {"5": "₹5k - ₹10k", "10": "₹10k - ₹25k", "25": "₹25k+", "discuss": "Discuss with team"}
    await state.update_data(budget=budget_names.get(budget, budget))
    await state.set_state(ProjectForm.requirement)
    await safe_edit(call, "📝 *Now describe your project.*\n\nTell us:\n• Your idea\n• Required pages/features\n• Any reference", parse_mode="Markdown")

@dp.message(ProjectForm.requirement)
async def requirement_save(message: Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 10:
        await message.answer("Please describe your project in a little more detail.")
        return
    await state.update_data(requirement=message.text.strip())
    await state.set_state(ProjectForm.contact)
    await message.answer("📞 *Almost done!*\n\nPlease share your contact number.\n\nExample:\n`9876543210`", parse_mode="Markdown")

@dp.message(ProjectForm.contact)
async def contact_save(message: Message, state: FSMContext):
    if not message.text or not valid_phone(message.text.strip()):
        await message.answer("❌ Invalid contact number.\nPlease send a valid 10–15 digit number.")
        return

    await state.update_data(contact=message.text.strip())
    data = await state.get_data()

    try:
        save_lead(message.from_user.id, data)
    except Exception as e:
        print(f"Lead save error: {e}")

    score = calculate_score(data)
    rec_text = recommendation(data.get("service"), data.get("business"))

    await message.answer(
        f"🚀 *PROJECT RECEIVED*\n\n🌐 *Service:* {data.get('service')}\n🏢 *Business:* {data.get('business')}\n⚙️ *Features:* {', '.join(data.get('features', []))}\n💰 *Budget:* {data.get('budget')}\n📝 *Requirement:* {data.get('requirement')}\n📞 *Contact:* {data.get('contact')}\n📊 *Score:* {score}/100\n\n{rec_text}\n\n✅ Paraweb team will contact you soon 🔥",
        parse_mode="Markdown"
    )

    try:
        pdf = generate_pdf(data)
        if pdf and os.path.exists(pdf):
            await message.answer_document(FSInputFile(pdf), caption="📄 Your Project Quotation")
    except Exception as e:
        print(f"PDF error: {e}")

    try: await send_payment(message)
    except Exception as e: print(f"Payment error: {e}")

    try: await notify_admin(data, message.from_user)
    except Exception as e: print(f"Admin notification error: {e}")

    await state.clear()

async def notify_admin(data, user):
    username = f"@{user.username}" if user.username else "None"
    text = f"🔥 *NEW PARAWEB LEAD*\n\n👤 *Name:* {user.first_name}\n🌐 *Service:* {data.get('service')}\n🏢 *Business:* {data.get('business')}\n⚙️ *Features:* {', '.join(data.get('features', []))}\n💰 *Budget:* {data.get('budget')}\n📝 *Req:* {data.get('requirement')}\n📞 *Contact:* {data.get('contact')}\n🆔 *User ID:* `{user.id}`\n🌐 *Username:* {username}"
    await bot.send_message(ADMIN_ID, text, parse_mode="Markdown")


# =========================================================
# OTHER FEATURES & ADMIN PANEL
# =========================================================

@dp.callback_query(F.data == "idea")
async def idea_generator(call: CallbackQuery):
    await call.answer()
    await safe_edit(call, "💡 *Idea Generator*\n\nTell us your business type in a message.", reply_markup=back_button(), parse_mode="Markdown")

@dp.callback_query(F.data == "mode")
async def choose_mode(call: CallbackQuery):
    await call.answer()
    await safe_edit(call, "🧠 *Choose your Paraweb Assistant personality:*", reply_markup=personality_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("mode_"))
async def mode_select(call: CallbackQuery):
    await call.answer()
    mode = call.data.replace("mode_", "")
    await safe_edit(call, PERSONALITIES.get(mode, "Mode not found."), reply_markup=back_button(), parse_mode="Markdown")

@dp.callback_query(F.data == "future")
async def future_preview(call: CallbackQuery):
    await call.answer()
    await call.message.answer("🔮 *Future Preview Complete*\n\nYour idea can become a Digital Platform with App, AI, and Admin Dashboard.", parse_mode="Markdown")

@dp.callback_query(F.data == "back")
async def back(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await safe_edit(call, WELCOME_TEXT, reply_markup=main_menu(), parse_mode="Markdown")

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id): return
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📩 View Leads", callback_data="admin_leads")],
            [
                InlineKeyboardButton(text="👥 Users Count", callback_data="admin_users"),
                InlineKeyboardButton(text="🤖 Hosted Bots", callback_data="admin_bots") # <-- NEW BUTTON
            ],
            [InlineKeyboardButton(text="📢 Broadcast", callback_data="broadcast")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back")]
        ]
    )
    await message.answer("👑 *Paraweb Admin Panel*", reply_markup=markup, parse_mode="Markdown")
    
@dp.callback_query(F.data == "admin_users")
async def users_count(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    try:
        db = connect()
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        db.close()
        await safe_edit(call, f"👥 *Total Users:* {count}", reply_markup=back_button(), parse_mode="Markdown")
    except Exception as e: print(f"Users count error: {e}")

@dp.callback_query(F.data == "admin_leads")
async def show_leads(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    leads = get_leads()
    if not leads:
        await safe_edit(call, "📭 No leads found.", reply_markup=back_button())
        return
    for lead in leads[:10]:
        await call.message.answer(f"🔥 *LEAD #{lead[0]}*\nUser ID: {lead[1]}\nService: {lead[2]}\nStatus: {lead[8]}", parse_mode="Markdown")

@dp.callback_query(F.data == "my_project")
async def my_project(call: CallbackQuery):
    await call.answer()
    leads = get_user_leads(call.from_user.id)
    if not leads:
        await safe_edit(call, "📂 *No project found.*\nStart your first project with Paraweb 🚀", reply_markup=main_menu(), parse_mode="Markdown")
        return
    lead = leads[0]
    await safe_edit(call, f"🚀 *Paraweb Project Tracker*\n\nProject: {lead[2]}\nCurrent Status: *{lead[8]}*", reply_markup=main_menu(), parse_mode="Markdown")

@dp.message()
async def unknown(message: Message):
    await message.answer("🤖 *I am Paraweb Assistant.*\nPlease use the buttons below to continue 🚀", reply_markup=main_menu(), parse_mode="Markdown")
# Callback handler for '🤖 Hosted Bots' button
@dp.callback_query(F.data == "admin_bots")
async def show_all_hosted_bots(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.answer()
    
    conn = connect() # hosting.db ya main db connect karein
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, bot_name, expiry_date FROM user_bots")
    bots = cursor.fetchall()
    conn.close()

    if not bots:
        await safe_edit(call, "🤖 *Hosted Bots Status*\n\nAbhi koi bhi bot host nahi hua hai.", reply_markup=back_button(), parse_mode="Markdown")
        return

    text = f"🤖 *Total Hosted Bots:* `{len(bots)}`\n\n"
    for b in bots:
        text += f"• *Bot:* `{b[1]}` | *User ID:* `{b[0]}`\n  *Expiry:* `{b[2][:10]}`\n\n"

    await safe_edit(call, text, reply_markup=back_button(), parse_mode="Markdown")

# Admin Command: Directly view all bots via /allbots
@dp.message(Command("allbots"))
async def command_all_bots(message: Message):
    if not is_admin(message.from_user.id): return
    
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, bot_name, expiry_date FROM user_bots")
    bots = cursor.fetchall()
    conn.close()

    if not bots:
        await message.answer("📭 Abhi koi bhi bot host nahi hai.")
        return

    msg = f"📊 *Total Hosted Bots:* `{len(bots)}`\n\n"
    for b in bots:
        msg += f"• `{b[1]}` | User: `{b[0]}` | Expires: `{b[2][:10]}`\n"
        
    await message.answer(msg, parse_mode="Markdown")


# =========================================================
# MAIN ENTRY POINT
# =========================================================

async def main():
    # Database Initializations
    init_main_db()
    init_hosting_db()

    print("🚀 Paraweb Bot & Hosting Manager Started")

    # Start Background Task for Expiry Checking
    asyncio.create_task(hosting_expiry_checker())

    # Start Bot Polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
