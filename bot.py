import asyncio
import os
import random

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import CommandStart


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
                    callback_data="start_project"
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
                    text="💡 Idea Generator",
                    callback_data="idea"
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

    await message.answer(
        WELCOME_TEXT,
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )



# ===============================
# START PROJECT
# ===============================


@dp.callback_query(
    F.data=="start_project"
)
async def project_start(call: CallbackQuery):

    await call.answer()

    await typing(call.message)

    text = """
🔥 *Project Assistant Activated*

I will help you plan your project.

First choose what you want to build:
"""

    await call.message.edit_text(
        text,
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )



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



# ===============================
# RUN BOT
# ===============================


async def main():

    print("🚀 Paraweb Bot Started")

    await dp.start_polling(bot)



if __name__=="__main__":

    asyncio.run(main())
