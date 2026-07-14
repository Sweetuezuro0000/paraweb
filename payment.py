from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile
)
import os


UPI_ID = "emiakura00@oksbi"


def payment_keyboard():

    return InlineKeyboardMarkup(

        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="✅ I Have Paid",
                    callback_data="payment_done"
                )
            ]

        ]

    )


async def send_payment(message):

    text = f"""
💳 ADVANCE PAYMENT

Please pay the advance amount.

Google Pay UPI:

{UPI_ID}

After payment click:

✅ I Have Paid
"""

    qr = "assets/gpay_qr.png"

    if os.path.exists(qr):

        await message.answer_photo(

            FSInputFile(qr),

            caption=text,

            reply_markup=payment_keyboard()

        )

    else:

        await message.answer(

            text,

            reply_markup=payment_keyboard()

        )
