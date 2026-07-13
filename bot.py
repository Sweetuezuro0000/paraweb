import os
import asyncio

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(TOKEN)
dp = Dispatcher()


# ==========================
# STATES
# ==========================

class Order(StatesGroup):
    requirement = State()
    contact = State()


# ==========================
# MENU
# ==========================

menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🌐 Website")],
        [KeyboardButton(text="📱 App")],
        [KeyboardButton(text="🤖 Telegram Bot")]
    ],
    resize_keyboard=True
)


# ==========================
# START
# ==========================

@dp.message(CommandStart())
async def start(message: Message):

    text = (
        "👋 Welcome to *Paraweb*\n\n"
        "We build:\n"
        "🌐 Websites\n"
        "📱 Mobile Apps\n"
        "🤖 Telegram Bots\n\n"
        "Please choose a service."
    )

    await message.answer(
        text,
        parse_mode="Markdown",
        reply_markup=menu
    )


# ==========================
# SERVICE SELECT
# ==========================

@dp.message(F.text.in_(["🌐 Website", "📱 App", "🤖 Telegram Bot"]))
async def service(message: Message, state: FSMContext):

    await state.update_data(service=message.text)

    await message.answer(
        "📝 Please describe your requirements.",
        reply_markup=ReplyKeyboardRemove()
    )

    await state.set_state(Order.requirement)


# ==========================
# REQUIREMENT
# ==========================

@dp.message(Order.requirement)
async def requirement(message: Message, state: FSMContext):

    await state.update_data(requirement=message.text)

    await message.answer(
        "📞 Please send your contact number or Telegram username."
    )

    await state.set_state(Order.contact)


# ==========================
# CONTACT
# ==========================

@dp.message(Order.contact)
async def contact(message: Message, state: FSMContext):

    await state.update_data(contact=message.text)

    data = await state.get_data()

    service = data["service"]
    requirement = data["requirement"]
    contact = data["contact"]

    admin_text = f"""
📩 New Order

👤 Name: {message.from_user.full_name}
🆔 ID: {message.from_user.id}
📌 Username: @{message.from_user.username}

💼 Service:
{service}

📝 Requirement:
{requirement}

📞 Contact:
{contact}
"""

    await bot.send_message(
        ADMIN_ID,
        admin_text
    )

    await message.answer(
        "✅ Thank you!\n\n"
        "Your request has been sent successfully.\n"
        "Our team will contact you soon.",
        reply_markup=menu
    )

    await state.clear()


# ==========================
# RUN
# ==========================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
