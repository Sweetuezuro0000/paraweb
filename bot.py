import asyncio
import os
import random
from threading import Thread

from dotenv import load_dotenv
from flask import Flask

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)

from database import (
    init_db,
    save_user,
    save_lead,
    get_leads,
    get_users,
    get_user_leads,
    update_status,
    connect,
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
# BOT
# =========================================================

bot = Bot(TOKEN)
dp = Dispatcher()


# =========================================================
# TEXT
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


# =========================================================
# STATES
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


# =========================================================
# KEYBOARDS
# =========================================================

def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Start Project",
                    callback_data="project_start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Website",
                    callback_data="service_website",
                ),
                InlineKeyboardButton(
                    text="📱 App",
                    callback_data="service_app",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Telegram Bot",
                    callback_data="service_bot",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💡 Idea Generator",
                    callback_data="idea",
                ),
                InlineKeyboardButton(
                    text="🧠 Assistant Mode",
                    callback_data="mode",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔮 Future Preview",
                    callback_data="future",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 My Project",
                    callback_data="my_project",
                )
            ],
        ]
    )


def service_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌐 Website",
                    callback_data="service_website",
                ),
                InlineKeyboardButton(
                    text="📱 App",
                    callback_data="service_app",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Telegram Bot",
                    callback_data="service_bot",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Back",
                    callback_data="back",
                )
            ],
        ]
    )


def back_button():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Back",
                    callback_data="back",
                )
            ]
        ]
    )


def business_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏪 Shop",
                    callback_data="business_shop",
                ),
                InlineKeyboardButton(
                    text="🍔 Restaurant",
                    callback_data="business_restaurant",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎓 Education",
                    callback_data="business_education",
                ),
                InlineKeyboardButton(
                    text="🏢 Company",
                    callback_data="business_company",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💡 Startup",
                    callback_data="business_startup",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Back",
                    callback_data="back",
                )
            ],
        ]
    )


def feature_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Payment",
                    callback_data="feature_payment",
                ),
                InlineKeyboardButton(
                    text="👥 Login",
                    callback_data="feature_login",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📊 Dashboard",
                    callback_data="feature_dashboard",
                ),
                InlineKeyboardButton(
                    text="📦 Products",
                    callback_data="feature_product",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Notifications",
                    callback_data="feature_notifications",
                ),
                InlineKeyboardButton(
                    text="🤖 AI",
                    callback_data="feature_ai",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="➡️ Continue",
                    callback_data="feature_done",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Back",
                    callback_data="back",
                )
            ],
        ]
    )


def budget_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="₹5k - ₹10k",
                    callback_data="budget_5",
                )
            ],
            [
                InlineKeyboardButton(
                    text="₹10k - ₹25k",
                    callback_data="budget_10",
                )
            ],
            [
                InlineKeyboardButton(
                    text="₹25k+",
                    callback_data="budget_25",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Discuss",
                    callback_data="budget_discuss",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Back",
                    callback_data="back",
                )
            ],
        ]
    )


# =========================================================
# PERSONALITY
# =========================================================

PERSONALITIES = {
    "developer": """
👨‍💻 *Developer Mode Activated*

I will focus on:

• Technology
• Features
• Architecture
• Performance
""",
    "business": """
💼 *Business Mode Activated*

I will focus on:

• Growth
• Customers
• Revenue
• Strategy
""",
    "creative": """
🎨 *Creative Mode Activated*

I will focus on:

• Design
• Ideas
• User Experience
""",
}


def personality_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👨‍💻 Developer",
                    callback_data="mode_developer",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💼 Business",
                    callback_data="mode_business",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎨 Creative",
                    callback_data="mode_creative",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Back",
                    callback_data="back",
                )
            ],
        ]
    )


# =========================================================
# ADMIN
# =========================================================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📩 View Leads",
                    callback_data="admin_leads",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Users Count",
                    callback_data="admin_users",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📢 Broadcast",
                    callback_data="broadcast",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Back",
                    callback_data="back",
                )
            ],
        ]
    )


def status_keyboard(lead_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📞 Contacted",
                    callback_data=f"status_contacted_{lead_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Working",
                    callback_data=f"status_working_{lead_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏸️ On Hold",
                    callback_data=f"status_hold_{lead_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancelled",
                    callback_data=f"status_cancelled_{lead_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Done",
                    callback_data=f"status_done_{lead_id}",
                )
            ],
        ]
    )


# =========================================================
# HELPERS
# =========================================================

async def typing(message: Message):
    try:
        await bot.send_chat_action(
            chat_id=message.chat.id,
            action="typing",
        )
        await asyncio.sleep(random.uniform(0.5, 1.0))
    except Exception as e:
        print(f"Typing error: {e}")


async def safe_edit(
    call: CallbackQuery,
    text: str,
    reply_markup=None,
    parse_mode=None,
):
    try:
        await call.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            print(f"Edit error: {e}")


def valid_phone(text: str) -> bool:
    cleaned = (
        text.replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )

    if cleaned.startswith("+"):
        digits = cleaned[1:]
    else:
        digits = cleaned

    return digits.isdigit() and 10 <= len(digits) <= 15


def calculate_score(data):
    score = 50

    if data.get("features"):
        score += 20

    if data.get("budget"):
        score += 15

    requirement = data.get("requirement", "")

    if len(requirement) > 50:
        score += 15

    return min(score, 100)


def recommendation(service, business):
    result = {
        "website": """
🌐 *Website Recommendation*

✓ Modern responsive design
✓ SEO optimization
✓ Fast loading
✓ Admin management
""",
        "app": """
📱 *App Recommendation*

✓ User accounts
✓ Push notifications
✓ Payment system
✓ Dashboard
""",
        "bot": """
🤖 *Bot Recommendation*

✓ Automation
✓ Customer support
✓ Lead management
✓ AI integration
""",
    }

    return result.get(
        service,
        "Custom solution recommended",
    )


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start(message: Message):
    await typing(message)

    try:
        save_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
    except Exception as e:
        print(f"Save user error: {e}")

    await message.answer(
        WELCOME_TEXT,
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )

    try:
        user = message.from_user

        username = (
            f"@{user.username}"
            if user.username
            else "None"
        )

        log_text = (
            "🆕 *New User Started the Bot!*\n\n"
            f"👤 *Name:* {user.first_name}\n"
            f"🆔 *User ID:* `{user.id}`\n"
            f"🌐 *Username:* {username}"
        )

        await bot.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_text,
            parse_mode="Markdown",
        )

    except Exception as e:
        print(f"Log channel error: {e}")


# =========================================================
# START PROJECT
# =========================================================

@dp.callback_query(F.data == "project_start")
async def project_start(
    call: CallbackQuery,
    state: FSMContext,
):
    await call.answer()

    await state.clear()

    await safe_edit(
        call,
        """
🔥 *Project Assistant Activated*

First choose what you want to build:
""",
        reply_markup=service_keyboard(),
        parse_mode="Markdown",
    )


# =========================================================
# SERVICE
# =========================================================

@dp.callback_query(F.data.startswith("service_"))
async def service_select(
    call: CallbackQuery,
    state: FSMContext,
):
    await call.answer()

    service = call.data.replace(
        "service_",
        "",
    )

    names = {
        "website": "🌐 Website Development",
        "app": "📱 Mobile App Development",
        "bot": "🤖 Telegram Bot Development",
    }

    await state.update_data(
        service=service,
        features=[],
    )

    await safe_edit(
        call,
        f"""
✅ *Selected:*

{names.get(service, service)}

Great choice 🚀

Now we will understand your requirements.
""",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📝 Continue",
                        callback_data=f"continue_{service}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Back",
                        callback_data="back",
                    )
                ],
            ]
        ),
        parse_mode="Markdown",
    )


# =========================================================
# CONTINUE PROJECT
# =========================================================

@dp.callback_query(F.data.startswith("continue_"))
async def continue_project(
    call: CallbackQuery,
    state: FSMContext,
):
    await call.answer()

    service = call.data.replace(
        "continue_",
        "",
    )

    await state.update_data(
        service=service,
        features=[],
    )

    await state.set_state(
        ProjectForm.business
    )

    await safe_edit(
        call,
        """
🔥 *Great!*

Tell us about your business.

Choose category 👇
""",
        reply_markup=business_keyboard(),
        parse_mode="Markdown",
    )


# =========================================================
# BUSINESS
# =========================================================

@dp.callback_query(F.data.startswith("business_"))
async def business_select(
    call: CallbackQuery,
    state: FSMContext,
):
    await call.answer()

    business = call.data.replace(
        "business_",
        "",
    )

    await state.update_data(
        business=business,
        features=[],
    )

    await state.set_state(
        ProjectForm.features
    )

    await safe_edit(
        call,
        """
⚙️ *What features do you need?*

Select all required features.

Then press Continue 👇
""",
        reply_markup=feature_keyboard(),
        parse_mode="Markdown",
    )


# =========================================================
# FEATURES
# =========================================================

@dp.callback_query(F.data.startswith("feature_"))
async def feature_select(
    call: CallbackQuery,
    state: FSMContext,
):
    await call.answer()

    feature = call.data.replace(
        "feature_",
        "",
    )

    if feature == "done":
        data = await state.get_data()

        if not data.get("features"):
            await call.answer(
                "Please select at least one feature.",
                show_alert=True,
            )
            return

        await state.set_state(
            ProjectForm.budget
        )

        await safe_edit(
            call,
            """
💰 *What is your approximate budget?*
""",
            reply_markup=budget_keyboard(),
            parse_mode="Markdown",
        )

        return

    data = await state.get_data()

    features = data.get(
        "features",
        [],
    )

    # Prevent duplicate feature
    if feature in features:
        await call.answer(
            "Already selected ✅",
            show_alert=False,
        )
        return

    features.append(feature)

    await state.update_data(
        features=features,
    )

    await call.answer(
        f"Added: {feature} ✅"
    )


# =========================================================
# BUDGET
# =========================================================

@dp.callback_query(F.data.startswith("budget_"))
async def budget_select(
    call: CallbackQuery,
    state: FSMContext,
):
    await call.answer()

    budget = call.data.replace(
        "budget_",
        "",
    )

    budget_names = {
        "5": "₹5k - ₹10k",
        "10": "₹10k - ₹25k",
        "25": "₹25k+",
        "discuss": "Discuss with team",
    }

    await state.update_data(
        budget=budget_names.get(
            budget,
            budget,
        )
    )

    await state.set_state(
        ProjectForm.requirement
    )

    await safe_edit(
        call,
        """
📝 *Now describe your project.*

Tell us:

• Your idea
• Required pages/features
• Any reference
""",
        parse_mode="Markdown",
    )


# =========================================================
# REQUIREMENT
# =========================================================

@dp.message(ProjectForm.requirement)
async def requirement_save(
    message: Message,
    state: FSMContext,
):
    if not message.text:
        await message.answer(
            "Please send your project requirement as text."
        )
        return

    requirement = message.text.strip()

    if len(requirement) < 10:
        await message.answer(
            "Please describe your project in a little more detail."
        )
        return

    await state.update_data(
        requirement=requirement,
    )

    await state.set_state(
        ProjectForm.contact
    )

    await message.answer(
        """
📞 *Almost done!*

Please share your contact number.

Example:
`9876543210`
""",
        parse_mode="Markdown",
    )


# =========================================================
# CONTACT + FINAL
# =========================================================

@dp.message(ProjectForm.contact)
async def contact_save(
    message: Message,
    state: FSMContext,
):
    if not message.text:
        await message.answer(
            "Please send your contact number."
        )
        return

    contact = message.text.strip()

    if not valid_phone(contact):
        await message.answer(
            "❌ Invalid contact number.\n\n"
            "Please send a valid 10–15 digit number."
        )
        return

    await state.update_data(
        contact=contact,
    )

    data = await state.get_data()

    # -----------------------------------------------------
    # SAVE LEAD FIRST
    # -----------------------------------------------------

    try:
        save_lead(
            message.from_user.id,
            data,
        )
    except Exception as e:
        print(f"Lead save error: {e}")

        await message.answer(
            "❌ Something went wrong while saving your request.\n"
            "Please try again later."
        )

        return

    # -----------------------------------------------------
    # SCORE
    # -----------------------------------------------------

    score = calculate_score(data)

    recommendation_text = recommendation(
        data.get("service"),
        data.get("business"),
    )

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------

    await message.answer(
        f"""
🚀 *PROJECT RECEIVED*

🌐 *Service:*
{data.get("service")}

🏢 *Business:*
{data.get("business")}

⚙️ *Features:*
{", ".join(data.get("features", []))}

💰 *Budget:*
{data.get("budget")}

📝 *Requirement:*
{data.get("requirement")}

📞 *Contact:*
{data.get("contact")}

📊 *Project Score:*
{score}/100

{recommendation_text}

✅ Your request has been received.

Paraweb team will contact you soon 🔥
""",
        parse_mode="Markdown",
    )

    # -----------------------------------------------------
    # PDF
    # -----------------------------------------------------

    try:
        pdf = generate_pdf(data)

        if pdf and os.path.exists(pdf):
            await message.answer_document(
                FSInputFile(pdf),
                caption="📄 Your Project Quotation",
            )

    except Exception as e:
        print(f"PDF error: {e}")

    # -----------------------------------------------------
    # PAYMENT
    # -----------------------------------------------------

    try:
        await send_payment(message)
    except Exception as e:
        print(f"Payment error: {e}")

    # -----------------------------------------------------
    # ADMIN NOTIFICATION
    # -----------------------------------------------------

    try:
        await notify_admin(
            data,
            message.from_user,
        )
    except Exception as e:
        print(f"Admin notification error: {e}")

    await state.clear()


# =========================================================
# ADMIN NOTIFICATION
# =========================================================

async def notify_admin(data, user):
    username = (
        f"@{user.username}"
        if user.username
        else "None"
    )

    text = f"""
🔥 *NEW PARAWEB LEAD*

👤 *Name:*
{user.first_name}

🌐 *Service:*
{data.get("service")}

🏢 *Business:*
{data.get("business")}

⚙️ *Features:*
{", ".join(data.get("features", []))}

💰 *Budget:*
{data.get("budget")}

📝 *Requirement:*
{data.get("requirement")}

📞 *Contact:*
{data.get("contact")}

🆔 *User ID:*
{user.id}

🌐 *Username:*
{username}
"""

    await bot.send_message(
        ADMIN_ID,
        text,
        parse_mode="Markdown",
    )


# =========================================================
# IDEA GENERATOR
# =========================================================

@dp.callback_query(F.data == "idea")
async def idea_generator(call: CallbackQuery):
    await call.answer()

    await safe_edit(
        call,
        """
💡 *Idea Generator*

Tell us your business type.

Examples:

🏪 Shop
🍔 Restaurant
🎓 Education
🏥 Service
🚀 Startup

Send your business type as a message.
""",
        reply_markup=back_button(),
        parse_mode="Markdown",
    )


# =========================================================
# PERSONALITY
# =========================================================

@dp.callback_query(F.data == "mode")
async def choose_mode(call: CallbackQuery):
    await call.answer()

    await safe_edit(
        call,
        """
🧠 *Choose your Paraweb Assistant personality:*
""",
        reply_markup=personality_keyboard(),
        parse_mode="Markdown",
    )


@dp.callback_query(F.data.startswith("mode_"))
async def mode_select(call: CallbackQuery):
    await call.answer()

    mode = call.data.replace(
        "mode_",
        "",
    )

    await safe_edit(
        call,
        PERSONALITIES.get(
            mode,
            "Mode not found.",
        ),
        reply_markup=back_button(),
        parse_mode="Markdown",
    )


# =========================================================
# FUTURE PREVIEW
# =========================================================

async def terminal_effect(message):
    logs = [
        "> Initializing Paraweb Core...",
        "> Loading development modules...",
        "> Connecting creative engine...",
        "> System Ready ✅",
    ]

    box = await message.answer(logs[0])

    current = ""

    for log in logs:
        current += "\n" + log

        await asyncio.sleep(0.7)

        try:
            await box.edit_text(current)
        except TelegramBadRequest:
            pass

    return box


@dp.callback_query(F.data == "future")
async def future_preview(call: CallbackQuery):
    await call.answer()

    await terminal_effect(
        call.message
    )

    await call.message.answer(
        """
🔮 *Future Preview Complete*

Your idea can become:

🚀 Digital Platform

Possible upgrades:

✓ Mobile App
✓ Automation
✓ Customer System
✓ AI Features
✓ Payment System
✓ Admin Dashboard

Paraweb can build it.
""",
        parse_mode="Markdown",
    )


# =========================================================
# ANALYZE COMMAND
# =========================================================

async def ai_thinking(message):
    steps = [
        "🔍 Understanding your idea...",
        "⚙️ Analyzing requirements...",
        "🧠 Preparing best solution...",
        "🚀 Creating roadmap...",
    ]

    temp = await message.answer(steps[0])

    for step in steps[1:]:
        await asyncio.sleep(0.8)

        try:
            await temp.edit_text(step)
        except TelegramBadRequest:
            pass

    await asyncio.sleep(0.5)

    try:
        await temp.delete()
    except Exception:
        pass


@dp.message(F.text == "/analyze")
async def analyze(message: Message):
    await ai_thinking(message)

    await message.answer(
        """
🧠 *Analysis Complete*

Project Strength:

████████░░ 80%

Recommendation:

Start with MVP,
then expand features 🚀
""",
        parse_mode="Markdown",
    )


# =========================================================
# BACK
# =========================================================

@dp.callback_query(F.data == "back")
async def back(
    call: CallbackQuery,
    state: FSMContext,
):
    await call.answer()

    await state.clear()

    await safe_edit(
        call,
        WELCOME_TEXT,
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )


# =========================================================
# ADMIN PANEL
# =========================================================

@dp.message(F.text == "/admin")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        """
👑 *Paraweb Admin Panel*

Choose option:
""",
        reply_markup=admin_keyboard(),
        parse_mode="Markdown",
    )


# =========================================================
# USERS COUNT
# =========================================================

@dp.callback_query(F.data == "admin_users")
async def users_count(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer()
        return

    await call.answer()

    try:
        db = connect()
        cursor = db.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM users"
        )

        count = cursor.fetchone()[0]

        db.close()

        await safe_edit(
            call,
            f"""
👥 *Total Users:*

{count}
""",
            reply_markup=admin_keyboard(),
            parse_mode="Markdown",
        )

    except Exception as e:
        print(f"Users count error: {e}")

        await call.message.answer(
            "❌ Could not load user count."
        )


# =========================================================
# SHOW LEADS
# =========================================================

@dp.callback_query(F.data == "admin_leads")
async def show_leads(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer()
        return

    await call.answer()

    try:
        leads = get_leads()
    except Exception as e:
        print(f"Get leads error: {e}")

        await call.message.answer(
            "❌ Could not load leads."
        )

        return

    if not leads:
        await safe_edit(
            call,
            "📭 No leads found.",
            reply_markup=admin_keyboard(),
        )
        return

    await safe_edit(
        call,
        f"📩 *Total Leads:* {len(leads)}\n\nShowing latest 10.",
        reply_markup=admin_keyboard(),
        parse_mode="Markdown",
    )

    for lead in leads[:10]:

        text = f"""
🔥 *LEAD #{lead[0]}*

👤 User ID:
{lead[1]}

🌐 Service:
{lead[2]}

🏢 Business:
{lead[3]}

⚙️ Features:
{lead[4]}

💰 Budget:
{lead[5]}

📝 Requirement:
{lead[6]}

📞 Contact:
{lead[7]}

📌 Status:
{lead[8]}
"""

        try:
            await call.message.answer(
                text,
                reply_markup=status_keyboard(lead[0]),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"Lead display error: {e}")


# =========================================================
# STATUS UPDATE
# =========================================================

@dp.callback_query(F.data.startswith("status_"))
async def change_status(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer()
        return

    parts = call.data.split("_", 2)

    if len(parts) != 3:
        await call.answer(
            "Invalid status.",
            show_alert=True,
        )
        return

    status = parts[1].upper()
    lead_id = parts[2]

    allowed_statuses = {
        "CONTACTED",
        "WORKING",
        "HOLD",
        "CANCELLED",
        "DONE",
    }

    if status not in allowed_statuses:
        await call.answer(
            "Invalid status.",
            show_alert=True,
        )
        return

    try:
        update_status(
            lead_id,
            status,
        )
    except Exception as e:
        print(f"Status update error: {e}")

        await call.answer(
            "Update failed.",
            show_alert=True,
        )
        return

    await call.answer(
        "Status Updated ✅"
    )

    # Find user
    user = None

    try:
        db = connect()
        cursor = db.cursor()

        cursor.execute(
            """
            SELECT user_id
            FROM leads
            WHERE id=?
            """,
            (lead_id,),
        )

        user = cursor.fetchone()

        db.close()

    except Exception as e:
        print(f"Find user error: {e}")

    messages = {
        "CONTACTED": """
📞 *Paraweb Update*

Your project discussion has started.

Our team will contact you soon 🚀
""",
        "WORKING": """
⚙️ *Paraweb Update*

Your project development has started 🔥

We are working on your idea.
""",
        "HOLD": """
⏸️ *Paraweb Update*

Your project is currently on hold.

Our team will update you soon.
""",
        "CANCELLED": """
❌ *Paraweb Update*

Your project has been cancelled.

Please contact our team if you have any questions.
""",
        "DONE": """
🎉 *Paraweb Update*

Your project has been completed.

Thank you for choosing Paraweb 🚀
""",
    }

    if user:
        try:
            await bot.send_message(
                user[0],
                messages.get(
                    status,
                    "Your project status has been updated.",
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"User status notification error: {e}")

    await call.message.answer(
        f"""
✅ *Lead Updated*

ID:
{lead_id}

Status:
{status}
""",
        parse_mode="Markdown",
    )


# =========================================================
# BROADCAST
# =========================================================

@dp.callback_query(F.data == "broadcast")
async def broadcast_start(
    call: CallbackQuery,
    state: FSMContext,
):
    if not is_admin(call.from_user.id):
        await call.answer()
        return

    await call.answer()

    await state.set_state(
        AdminForm.broadcast_message
    )

    await call.message.answer(
        """
📢 *Broadcast Mode*

Send the message you want to send to all users.

Send `/cancel` to cancel.
""",
        parse_mode="Markdown",
    )


@dp.message(AdminForm.broadcast_message)
async def send_broadcast(
    message: Message,
    state: FSMContext,
):
    if not is_admin(message.from_user.id):
        return

    if message.text == "/cancel":
        await state.clear()

        await message.answer(
            "❌ Broadcast cancelled."
        )

        return

    if not message.text:
        await message.answer(
            "Please send a text message."
        )
        return

    try:
        users = get_users()
    except Exception as e:
        print(f"Get users error: {e}")

        await message.answer(
            "❌ Could not load users."
        )

        await state.clear()
        return

    sent = 0
    failed = 0

    status_message = await message.answer(
        "📢 Broadcast starting..."
    )

    for user in users:

        try:
            await bot.send_message(
                user[0],
                message.text,
            )

            sent += 1

            await asyncio.sleep(0.05)

        except TelegramRetryAfter as e:
            await asyncio.sleep(
                e.retry_after
            )

            try:
                await bot.send_message(
                    user[0],
                    message.text,
                )

                sent += 1

            except Exception:
                failed += 1

        except Exception as e:
            print(
                f"Broadcast failed for {user[0]}: {e}"
            )
            failed += 1

    try:
        await status_message.edit_text(
            f"""
📢 *Broadcast Completed*

✅ Sent:
{sent}

❌ Failed:
{failed}

👥 Total:
{len(users)}
""",
            parse_mode="Markdown",
        )
    except Exception:
        await message.answer(
            f"Broadcast completed.\nSent: {sent}\nFailed: {failed}"
        )

    await state.clear()


# =========================================================
# MY PROJECT
# =========================================================

@dp.callback_query(F.data == "my_project")
async def my_project(call: CallbackQuery):
    await call.answer()

    try:
        leads = get_user_leads(
            call.from_user.id
        )
    except Exception as e:
        print(f"User leads error: {e}")

        await call.message.answer(
            "❌ Could not load your projects."
        )

        return

    if not leads:
        await safe_edit(
            call,
            """
📂 *No project found.*

Start your first project with Paraweb 🚀
""",
            reply_markup=main_menu(),
            parse_mode="Markdown",
        )
        return

    # Show latest project
    lead = leads[0]

    status = lead[8]

    stages = {
        "NEW": """
🟦 Requirement Received
⬜ Planning
⬜ Development
⬜ Testing
⬜ Launch
""",
        "CONTACTED": """
✅ Requirement Received
🟦 Discussion Started
⬜ Development
⬜ Testing
⬜ Launch
""",
        "WORKING": """
✅ Requirement Received
✅ Planning
🟦 Development
⬜ Testing
⬜ Launch
""",
        "HOLD": """
✅ Requirement Received
⏸️ Project On Hold
⬜ Development
⬜ Testing
⬜ Launch
""",
        "DONE": """
✅ Requirement Received
✅ Development
✅ Testing
🟦 Project Delivered 🚀
""",
        "CANCELLED": """
✅ Requirement Received
❌ Project Cancelled
""",
    }

    await safe_edit(
        call,
        f"""
🚀 *Paraweb Project Tracker*

Project:
{lead[2]}

Status:

{stages.get(
    status,
    stages["NEW"],
)}

Current Stage:
*{status}*
""",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )


# =========================================================
# PAYMENT DONE
# =========================================================

@dp.callback_query(F.data == "payment_done")
async def payment_done(call: CallbackQuery):
    await call.answer()

    await call.message.answer(
        """
✅ *Payment request received.*

Our team will verify your payment shortly.

Thank you ❤️
""",
        parse_mode="Markdown",
    )

    try:
        username = (
            f"@{call.from_user.username}"
            if call.from_user.username
            else "None"
        )

        await bot.send_message(
            ADMIN_ID,
            f"""
💰 *PAYMENT REQUEST*

👤 User:
{call.from_user.full_name}

🌐 Username:
{username}

🆔 User ID:
{call.from_user.id}
""",
            parse_mode="Markdown",
        )

    except Exception as e:
        print(
            f"Payment admin notification error: {e}"
        )


# =========================================================
# UNKNOWN MESSAGE
# =========================================================

@dp.message()
async def unknown(message: Message):

    await message.answer(
        """
🤖 *I am Paraweb Assistant.*

Please use the buttons below
to continue your journey 🚀
""",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    init_db()

    print("🚀 Paraweb Bot Started")

    await dp.start_polling(bot)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
```
