import asyncio
import os
import random
from database import *
from database import get_leads
from database import connect
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import CommandStart
from database import get_users
from database import update_status
from database import get_user_leads
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import State, StatesGroup
from pdf_generator import generate_pdf
from aiogram.types import FSInputFile
from payment import send_payment
import os
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    # Render जो पोर्ट देगा, यह उसे अपने आप उठा लेगा
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# अपने असली बॉट को चालू (polling) करने वाली लाइन से ठीक पहले इसे लिखें
keep_alive()

# इसके नीचे आपका पुराना बॉट का कोड रहेगा (जैसे: bot.polling())

# ===============================
# CONFIG
# ===============================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN missing in .env")


bot = Bot(TOKEN)
dp = Dispatcher()


# ===============================
# BRAND SETTINGS
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


# ===============================
# KEYBOARDS
# ===============================


def main_menu():

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="🚀 Start Project",
                    callback_data="project_start"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🌐 Website",
                    callback_data="service_website"
                ),
                InlineKeyboardButton(
                    text="📱 App",
                    callback_data="service_app"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🤖 Telegram Bot",
                    callback_data="service_bot"
                )
            ],

            [
                InlineKeyboardButton(
                    text="📊 My Project",
                    callback_data="my_project"
                )
            ]

        ]
    )

    return keyboard


def back_button():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="⬅️ Back",
                    callback_data="back"
                )
            ]

        ]
    )



# ===============================
# TYPING EFFECT
# ===============================


async def typing(message):

    await bot.send_chat_action(
        chat_id=message.chat.id,
        action="typing"
    )

    await asyncio.sleep(
        random.uniform(1,2)
    )



# ===============================
# START COMMAND
# ===============================

@dp.message(CommandStart())
async def start(message: Message):
    await typing(message)

    save_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    await message.answer(
        WELCOME_TEXT,
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )
# ===============================
# START COMMAND WITH LOGGER
# ===============================

# ⚠️ यहाँ अपने असली लॉग चैनल की ID डालें (यह हमेशा -100 से शुरू होती है)
LOG_CHANNEL_ID = -1004463199472  

    # ---- यहाँ से लॉग भेजने का नया कोड शुरू होता है ----
    try:
        user = message.from_user
        username = f"@{user.username}" if user.username else "None"
        
        log_text = (
            "🆕 **New User Started the Bot!**\n\n"
            f"👤 **Name:** {user.first_name}\n"
            f"🆔 **User ID:** `{user.id}`\n"
            f"🌐 **Username:** {username}"
        )
        
        # Aiogram में बोट ऑब्जेक्ट को ऐसे कॉल करके चैनल में मैसेज भेजते हैं
        await message.bot.send_message(
            chat_id=LOG_CHANNEL_ID, 
            text=log_text, 
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Log channel error: {e}")
    # ---- नया कोड यहाँ खत्म होता है ----

# ===============================
# START PROJECT
# ===============================


@dp.callback_query(F.data == "project_start")
async def project_start(call: CallbackQuery):

    await call.answer()

    await typing(call.message)

    text = """
🔥 *Project Assistant Activated*

I will help you plan your project.

First choose what you want to build:
"""

    try:
        await call.message.edit_text(
            text,
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )
    except TelegramBadRequest:
        pass
# ===============================
# SERVICE SELECT
# ===============================


@dp.callback_query(
    F.data.startswith("service_")
)
async def service_select(call: CallbackQuery):

    await call.answer()

    service = call.data.replace(
        "service_",
        ""
    )


    names = {

        "website":
        "🌐 Website Development",

        "app":
        "📱 Mobile App Development",

        "bot":
        "🤖 Telegram Bot Development"

    }


    text=f"""
✅ Selected:

*{names.get(service)}*

Great choice 🚀

Now we will understand your requirements.
"""


    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="📝 Continue",
                    callback_data=f"continue_{service}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="⬅️ Back",
                    callback_data="back"
                )
            ]

        ]
    )


    await call.message.edit_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )



# ===============================
# IDEA GENERATOR BASE
# ===============================


@dp.callback_query(
    F.data=="idea"
)
async def idea_generator(call: CallbackQuery):

    await call.answer()

    await typing(call.message)


    text="""
💡 *Idea Generator*

Tell us your business type.

Example:

🏪 Shop
🍔 Restaurant
🎓 Education
🏥 Service
"""


    await call.message.edit_text(
        text,
        reply_markup=back_button(),
        parse_mode="Markdown"
    )



# ===============================
# BACK BUTTON
# ===============================


@dp.callback_query(
    F.data=="back"
)
async def back(call: CallbackQuery):

    await call.answer()

    await call.message.edit_text(
        WELCOME_TEXT,
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )



# ===============================
# RUN BOT
# ===============================



# ===============================
# PART 2 : PROJECT ASSISTANT FLOW
# ===============================

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


# ===============================
# USER STATES
# ===============================


class ProjectForm(StatesGroup):

    service = State()
    business = State()
    features = State()
    budget = State()
    requirement = State()
    contact = State()

class AdminForm(StatesGroup):
    broadcast_message = State()

# ===============================
# BUSINESS BUTTONS
# ===============================


def business_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="🏪 Shop",
                    callback_data="business_shop"
                ),

                InlineKeyboardButton(
                    text="🍔 Restaurant",
                    callback_data="business_restaurant"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🎓 Education",
                    callback_data="business_education"
                ),

                InlineKeyboardButton(
                    text="🏢 Company",
                    callback_data="business_company"
                )
            ],

            [
                InlineKeyboardButton(
                    text="💡 Startup",
                    callback_data="business_startup"
                )
            ]

        ]
    )



# ===============================
# FEATURE BUTTONS
# ===============================


def feature_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="💳 Payment",
                    callback_data="feature_payment"
                ),

                InlineKeyboardButton(
                    text="👥 Login",
                    callback_data="feature_login"
                )
            ],

            [
                InlineKeyboardButton(
                    text="📊 Dashboard",
                    callback_data="feature_dashboard"
                ),

                InlineKeyboardButton(
                    text="📦 Products",
                    callback_data="feature_product"
                )
            ],

            [
                InlineKeyboardButton(
                    text="➡️ Continue",
                    callback_data="feature_done"
                )
            ]

        ]
    )



# ===============================
# BUDGET BUTTONS
# ===============================


def budget_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="₹5k - ₹10k",
                    callback_data="budget_5"
                )
            ],

            [
                InlineKeyboardButton(
                    text="₹10k - ₹25k",
                    callback_data="budget_10"
                )
            ],

            [
                InlineKeyboardButton(
                    text="₹25k+",
                    callback_data="budget_25"
                )
            ],

            [
                InlineKeyboardButton(
                    text="💬 Discuss",
                    callback_data="budget_discuss"
                )
            ]

        ]
    )



# ===============================
# CONTINUE PROJECT
# ===============================


@dp.callback_query(
    F.data.startswith("continue_")
)
async def continue_project(
    call:CallbackQuery,
    state:FSMContext
):

    await call.answer()

    service = call.data.replace(
        "continue_",
        ""
    )

    await state.update_data(
        service=service
    )


    await state.set_state(
        ProjectForm.business
    )


    await call.message.edit_text(
        """
🔥 Great!

Tell us about your business.

Choose category 👇
""",
        reply_markup=business_keyboard()
    )



# ===============================
# BUSINESS SELECT
# ===============================


@dp.callback_query(
    F.data.startswith("business_")
)
async def business_select(
    call:CallbackQuery,
    state:FSMContext
):

    await call.answer()

    business = call.data.replace(
        "business_",
        ""
    )

    await state.update_data(
        business=business
    )


    await state.set_state(
        ProjectForm.features
    )


    await call.message.edit_text(
        """
⚙️ What features do you need?

Select your requirements 👇
""",
        reply_markup=feature_keyboard()
    )



# ===============================
# FEATURE SELECT
# ===============================


@dp.callback_query(
    F.data.startswith("feature_")
)
async def feature_select(
    call:CallbackQuery,
    state:FSMContext
):

    await call.answer()

    feature = call.data.replace(
        "feature_",
        ""
    )


    if feature=="done":

        await state.set_state(
            ProjectForm.budget
        )

        await call.message.edit_text(
            """
💰 What is your approximate budget?
""",
            reply_markup=budget_keyboard()
        )

        return


    data = await state.get_data()

    features=data.get(
        "features",
        []
    )

    features.append(feature)

    await state.update_data(
        features=features
    )


    await call.message.answer(
        f"✅ Added: {feature}"
    )



# ===============================
# BUDGET SELECT
# ===============================


@dp.callback_query(
    F.data.startswith("budget_")
)
async def budget_select(
    call:CallbackQuery,
    state:FSMContext
):

    await call.answer()

    budget=call.data.replace(
        "budget_",
        ""
    )


    await state.update_data(
        budget=budget
    )


    await state.set_state(
        ProjectForm.requirement
    )


    await call.message.edit_text(
        """
📝 Now describe your project.

Tell us:
• Your idea
• Required pages/features
• Any reference

""")



# ===============================
# REQUIREMENT SAVE
# ===============================


@dp.message(
    ProjectForm.requirement
)
async def requirement_save(
    message:Message,
    state:FSMContext
):

    await state.update_data(
        requirement=message.text
    )


    await state.set_state(
        ProjectForm.contact
    )


    await message.answer(
        """
📞 Almost done!

Please share your contact number.
"""
    )



# ===============================
# FINAL SUMMARY
# ===============================


@dp.message(
    ProjectForm.contact
)
async def contact_save(
    message: Message,
    state: FSMContext
):
    await state.update_data(
        contact=message.text
    )

    data = await state.get_data()

    await message.answer(
f"""
🚀 PROJECT SUMMARY

Service:
{data.get('service')}

Business:
{data.get('business')}

Features:
{data.get('features')}

Budget:
{data.get('budget')}

Requirement:
{data.get('requirement')}

Contact:
{data.get('contact')}

✅ Your request has been received.

Paraweb team will contact you soon 🔥
"""
    )
    pdf = generate_pdf(data)

    await message.answer_document(
        FSInputFile(pdf),
        caption="📄 Your Project Quotation"
    )
    await send_payment(message)

    save_lead(
        message.from_user.id,
        data
    )

    await notify_admin(
        data,
        message.from_user
    )

    await state.clear()
# ===============================
# PART 3 : PREMIUM EXPERIENCE
# ===============================


# ===============================
# AI THINKING EFFECT
# ===============================


async def ai_thinking(message):

    steps = [

        "🔍 Understanding your idea...",
        "⚙️ Analyzing requirements...",
        "🧠 Preparing best solution...",
        "🚀 Creating roadmap..."

    ]


    temp = await message.answer(
        steps[0]
    )


    for step in steps[1:]:

        await asyncio.sleep(1)

        await temp.edit_text(
            step
        )


    await asyncio.sleep(1)

    await temp.delete()



# ===============================
# PROJECT SCORE SYSTEM
# ===============================


def calculate_score(data):

    score = 50


    if data.get("features"):
        score += 20


    if data.get("budget"):
        score += 15


    if len(
        data.get(
            "requirement",
            ""
        )
    ) > 50:

        score += 15


    if score > 100:
        score = 100


    return score



# ===============================
# SMART RECOMMENDATION
# ===============================


def recommendation(service,business):


    result={

        "website":
        """
🌐 Website Recommendation:

✓ Modern responsive design
✓ SEO optimization
✓ Fast loading
✓ Admin management
        """,


        "app":
        """
📱 App Recommendation:

✓ User accounts
✓ Push notifications
✓ Payment system
✓ Dashboard
        """,


        "bot":
        """
🤖 Bot Recommendation:

✓ Automation
✓ Customer support
✓ Lead management
✓ AI integration
        """

    }


    return result.get(
        service,
        "Custom solution recommended"
    )



# ===============================
# TERMINAL ANIMATION
# ===============================


async def terminal_effect(message):


    logs=[

        "> Initializing Paraweb Core...",
        "> Loading development modules...",
        "> Connecting creative engine...",
        "> System Ready ✅"

    ]


    box=await message.answer(
        logs[0]
    )


    current=""


    for log in logs:

        current += "\n"+log

        await asyncio.sleep(0.8)

        await box.edit_text(
            current
        )



# ===============================
# PERSONALITY MODES
# ===============================


PERSONALITIES={


"developer":
"""
👨‍💻 Developer Mode Activated

I will focus on:
• Technology
• Features
• Architecture
• Performance
""",


"business":
"""
💼 Business Mode Activated

I will focus on:
• Growth
• Customers
• Revenue
• Strategy
""",


"creative":
"""
🎨 Creative Mode Activated

I will focus on:
• Design
• Ideas
• User Experience
"""

}



def personality_keyboard():

    return InlineKeyboardMarkup(

        inline_keyboard=[

            [

            InlineKeyboardButton(
                text="👨‍💻 Developer",
                callback_data="mode_developer"
            )

            ],

            [

            InlineKeyboardButton(
                text="💼 Business",
                callback_data="mode_business"
            )

            ],

            [

            InlineKeyboardButton(
                text="🎨 Creative",
                callback_data="mode_creative"
            )

            ]

        ]

    )



# ===============================
# MODE BUTTON
# ===============================


@dp.callback_query(
    F.data=="mode"
)
async def choose_mode(
    call:CallbackQuery
):

    await call.answer()


    await call.message.edit_text(

        """
🧠 Choose your Paraweb Assistant personality:
""",

        reply_markup=personality_keyboard()

    )



# ===============================
# MODE SELECT
# ===============================


@dp.callback_query(
    F.data.startswith("mode_")
)
async def mode_select(
    call:CallbackQuery
):

    await call.answer()


    mode=call.data.replace(
        "mode_",
        ""
    )


    await call.message.edit_text(

        PERSONALITIES.get(mode),

    )



# ===============================
# FUTURE PREVIEW FEATURE
# ===============================


@dp.callback_query(
    F.data=="future"
)
async def future_preview(
    call:CallbackQuery
):

    await call.answer()


    await terminal_effect(
        call.message
    )


    await call.message.answer(

"""
🔮 Future Preview Complete


Your idea can become:

🚀 Digital Platform

Possible upgrades:

✓ Mobile App
✓ Automation
✓ Customer System
✓ AI Features


Paraweb can build it.
"""

    )



# ===============================
# PROJECT ANALYSIS COMMAND
# ===============================


@dp.message(
    F.text=="/analyze"
)
async def analyze(message:Message):


    await ai_thinking(
        message
    )


    await message.answer(

"""
🧠 Analysis Complete


Project Strength:

████████░░ 80%


Recommendation:

Start with MVP,
then expand features 🚀
"""

    )
    # ===============================
# PART 5 : ADMIN PANEL
# ===============================


# ===============================
# ADMIN CHECK
# ===============================
ADMIN_ID = int(os.getenv("ADMIN_ID"))
def is_admin(user_id):

    return user_id == ADMIN_ID



# ===============================
# ADMIN MENU
# ===============================

def admin_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="📩 View Leads",
                    callback_data="admin_leads"
                )
            ],

            [
                InlineKeyboardButton(
                    text="👥 Users Count",
                    callback_data="admin_users"
                )
            ],

            [
                InlineKeyboardButton(
                    text="📢 Broadcast",
                    callback_data="broadcast"
                )
            ]

        ]
    )
# ===============================
# ADMIN COMMAND
# ===============================


@dp.message(
    F.text=="/admin"
)
async def admin_panel(
    message:Message
):

    if not is_admin(
        message.from_user.id
    ):
        return


    await message.answer(

"""
👑 Paraweb Admin Panel

Choose option:
""",

reply_markup=admin_keyboard()

    )



# ===============================
# USER COUNT
# ===============================


@dp.callback_query(
    F.data=="admin_users"
)
async def users_count(
    call:CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):
        return


    db=connect()

    cursor=db.cursor()


    cursor.execute(
        "SELECT COUNT(*) FROM users"
    )


    count=cursor.fetchone()[0]


    db.close()


    await call.answer()


    await call.message.edit_text(

f"""
👥 Total Users:

{count}

"""

    )



# ===============================
# SHOW LEADS
# ===============================


# ===============================
# ADMIN LEADS WITH ACTION BUTTONS
# ===============================


@dp.callback_query(
    F.data=="admin_leads"
)
async def show_leads(
    call:CallbackQuery
):

    if not is_admin(
        call.from_user.id
    ):
        return


    leads = get_leads()


    await call.answer()


    if not leads:

        await call.message.edit_text(
            "📭 No leads found"
        )

        return



    for lead in leads[:10]:


        text=f"""
🔥 LEAD #{lead[0]}


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


        await call.message.answer(

            text,

            reply_markup=status_keyboard(
                lead[0]
            )

        )
# ===============================
# NEW LEAD NOTIFICATION
# ===============================


async def notify_admin(
    data,
    user
):


    text=f"""

🔥 NEW PARAWEB LEAD


👤 Name:
{user.first_name}


🌐 Service:
{data.get('service')}


🏢 Business:
{data.get('business')}


💰 Budget:
{data.get('budget')}


📝 Requirement:
{data.get('requirement')}


📞 Contact:
{data.get('contact')}

"""


    await bot.send_message(
        ADMIN_ID,
        text
    )
# ===============================
# BROADCAST
# ===============================

@dp.callback_query(
    F.data=="broadcast"
)
async def broadcast_start(
    call:CallbackQuery,
    state:FSMContext
):

    if not is_admin(
        call.from_user.id
    ):
        return


    await call.answer()


    await state.set_state(
    AdminForm.broadcast_message
)


    await call.message.answer(
        """
📢 Broadcast Mode

Send message for all users:
"""
    )
@dp.message(
    AdminForm.broadcast_message
)
async def send_broadcast(
    message:Message,
    state:FSMContext
):

    if not is_admin(
        message.from_user.id
    ):
        return


    users=get_users()


    sent=0


    for user in users:

        try:

            await bot.send_message(
                user[0],
                message.text
            )

            sent+=1


        except:
            pass



    await message.answer(
f"""
✅ Broadcast Completed

Sent to:
{sent} users
"""
    )


    await state.clear()    
# ===============================
# CLIENT PROJECT STATUS
# ===============================


@dp.callback_query(
    F.data=="my_project"
)
async def my_project(
    call:CallbackQuery
):

    await call.answer()


    leads=get_user_leads(
        call.from_user.id
    )


    if not leads:

        await call.message.edit_text(
            """
📂 No project found.

Start your first project with Paraweb 🚀
"""
        )

        return



    lead=leads[0]


    status=lead[8]


    stages={

        "NEW":
"""
🟦 Requirement Received
⬜ Planning
⬜ Development
⬜ Testing
⬜ Launch
""",

        "CONTACTED":
"""
✅ Requirement Received
🟦 Discussion Started
⬜ Development
⬜ Testing
⬜ Launch
""",

        "WORKING":
"""
✅ Requirement Received
✅ Planning
🟦 Development
⬜ Testing
⬜ Launch
""",

        "DONE":
"""
✅ Requirement Received
✅ Development
✅ Testing
🟦 Project Delivered 🚀
"""

    }



    await call.message.edit_text(

f"""
🚀 Paraweb Project Tracker


Project:
{lead[2]}


Status:

{stages.get(status, stages["NEW"])}


Current Stage:
{status}

"""

    )
def status_keyboard(lead_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📞 Contacted",
                    callback_data=f"status_contacted_{lead_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Working",
                    callback_data=f"status_working_{lead_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Done",
                    callback_data=f"status_done_{lead_id}"
                )
            ]
        ]
    )


@dp.callback_query(F.data.startswith("status_"))
async def change_status(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    parts = call.data.split("_")
    status = parts[1].upper()
    lead_id = parts[2]

    update_status(
        lead_id,
        status
    )

    await call.answer("Status Updated ✅")


    # FIND USER ID

    db = connect()

    cursor = db.cursor()


    cursor.execute(
        """
        SELECT user_id 
        FROM leads 
        WHERE id=?
        """,
        (lead_id,)
    )


    user = cursor.fetchone()


    db.close()



    if user:


        messages={

            "CONTACTED":
"""
📞 Paraweb Update

Your project discussion has started.

Our team will contact you soon 🚀
""",

            "WORKING":
"""
⚙️ Paraweb Update

Your project development has started 🔥

We are working on your idea.
""",

            "DONE":
"""
🎉 Paraweb Update

Your project has been completed.

Thank you for choosing Paraweb 🚀
"""

        }


        await bot.send_message(
            user[0],
            messages.get(
                status,
                "Your project status updated."
            )
        )



    await call.message.answer(

f"""
✅ Lead Updated

ID:
{lead_id}

Status:
{status}
"""
    )
# ===============================
# UNKNOWN MESSAGE
# ===============================


@dp.message()
async def unknown(message: Message):

    await typing(message)

    await message.answer(
        """
🤖 I am Paraweb Assistant.

Please use the buttons below
to continue your journey 🚀
""",
        reply_markup=main_menu()
    )
@dp.callback_query(F.data == "payment_done")
async def payment_done(call: CallbackQuery):

    await call.answer()

    await call.message.answer(
        """
✅ Payment request received.

Our team will verify your payment shortly.

Thank you ❤️
"""
    )

    await bot.send_message(
        ADMIN_ID,
        f"""
💰 PAYMENT REQUEST

User: {call.from_user.full_name}
Username: @{call.from_user.username}
User ID: {call.from_user.id}
"""
    )

async def main():
    init_db()
    print("🚀 Paraweb Bot Started")

    await dp.start_polling(bot)



if __name__=="__main__":

    asyncio.run(main())
