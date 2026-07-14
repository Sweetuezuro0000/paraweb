import os
from datetime import datetime
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import inch


def generate_pdf(data):

    os.makedirs("quotations", exist_ok=True)

    quotation_id = datetime.now().strftime("PW-%Y%m%d-%H%M%S")

    filename = f"quotations/{quotation_id}.pdf"

    doc = SimpleDocTemplate(filename)

    styles = getSampleStyleSheet()

    title = styles["Heading1"]
    title.alignment = TA_CENTER

    story = []

    logo_path = "assets/logo.png"

    if os.path.exists(logo_path):
        logo = Image(
            logo_path,
            width=1.5 * inch,
            height=1.5 * inch
        )
        story.append(logo)

    story.append(
        Paragraph(
            "PARAWEB PROJECT QUOTATION",
            title
        )
    )

    story.append(Spacer(1, 20))

    story.append(
        Paragraph(
            f"<b>Quotation ID:</b> {quotation_id}",
            styles["Normal"]
        )
    )

    story.append(
        Paragraph(
            f"<b>Date:</b> {datetime.now().strftime('%d-%m-%Y %H:%M')}",
            styles["Normal"]
        )
    )

    story.append(Spacer(1, 15))

    fields = [

        ("Service", data.get("service")),
        ("Business", data.get("business")),
        ("Features", data.get("features")),
        ("Budget", data.get("budget")),
        ("Requirement", data.get("requirement")),
        ("Contact", data.get("contact"))

    ]

    for title_text, value in fields:

        story.append(
            Paragraph(
                f"<b>{title_text}</b>",
                styles["Heading3"]
            )
        )

        story.append(
            Paragraph(
                str(value),
                styles["Normal"]
            )
        )

        story.append(Spacer(1, 10))

    story.append(Spacer(1, 20))

    story.append(
        Paragraph(
            "<b>Thank you for choosing Paraweb.</b>",
            styles["Heading2"]
        )
    )

    story.append(
        Paragraph(
            "Our team will contact you soon.",
            styles["Normal"]
        )
    )

    doc.build(story)

    return filename
