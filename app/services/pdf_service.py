"""
PDF generation for Quote, Packing Slip, and Invoice documents.
Uses reportlab for PDF generation.
"""

import io
from datetime import datetime
from pathlib import Path
from typing import Optional
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config

# ── Template paths ───────────────────────────────────────────
TEMPLATE_DIR = Path(__file__).parent.parent.parent / "examples"

W, H = letter  # 612 x 792 points

# ── Colors ──────────────────────────────────────────────────
BLACK = HexColor("#000000")
WHITE = HexColor("#ffffff")
LTGRAY = HexColor("#f0f0f0")
DKGRAY = HexColor("#555555")
TEAL = HexColor("#1a5f7a")
ORANGE = HexColor("#f39c12")


# ── Helper functions ───────────────────────────────────────────
def _format_date(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%m/%d/%Y")
    except (ValueError, TypeError):
        return date_str


def _draw_box(c, x, y, width, height, title, lines):
    c.setFillColor(LTGRAY)
    c.rect(x, y - height + 15, width, height, fill=1, stroke=0)

    c.setFillColor(TEAL)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x + 5, y - 12, title.upper())

    c.setFillColor(BLACK)
    c.setFont("Helvetica", 9)
    for i, line in enumerate(lines[:3]):
        if line:
            c.drawString(x + 5, y - 25 - (i * 12), line[:40])


# QUOTE PDF
# ═══════════════════════════════════════════════════════════════
def build_quote_pdf(quote: dict, client: dict, items: list) -> bytes:
    import asyncio
    from fastapi.templating import Jinja2Templates
    from pathlib import Path

    # Calculate totals
    subtotal = sum(
        item.get("quantity", 0) * item.get("quoted_price", 0) for item in items
    )
    if quote.get("rental_days"):
        subtotal = subtotal * quote["rental_days"]
    tax_rate = quote.get("sales_tax_rate") or 0
    tax = subtotal * tax_rate
    discount = quote.get("discount") or 0
    shipping = quote.get("shipping_cost") or 0
    total = subtotal + tax - discount + shipping

    # Template directory
    TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

    # Prepare context for template
    context = {
        "quote": quote,
        "client": client,
        "items": items,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "logo_path": str(config.LOGO_PATH) if config.LOGO_PATH else "",
    }

    # Render template
    html_content = templates.get_template("quotes/pdf.html").render(context)

    # Use Playwright to convert HTML to PDF
    async def generate_pdf():
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                args=["--disable-web-security", "--allow-file-access-from-files"]
            )
            page = await browser.new_page()

            # Set a realistic viewport
            await page.set_viewport_size(
                {"width": 612, "height": 792}
            )  # Letter size in points

            # Load content and wait for everything
            import urllib.parse

            # Normalize file URLs first
            normalized_html = html_content.replace("file://", "file:///")

            # Properly URL-encode the HTML
            encoded_html = urllib.parse.quote(normalized_html)

            # Build the data URL
            data_url = f"data:text/html,{encoded_html}"

            # Navigate
            await page.goto(
                data_url,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(2000)

            # Generate PDF with settings closer to browser print
            pdf = await page.pdf(
                width="612pt", height="792pt", print_background=True, margin=None
            )
            await browser.close()
            return pdf

    return asyncio.run(generate_pdf())


def _format_date(date_str):
    """Convert YYYY-MM-DD to MM/DD/YY."""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%m/%d/%y")
    except (ValueError, TypeError):
        return date_str


def _strip_doc_prefix(doc_number):
    """Remove leading Q/PL/INV prefix."""
    if not doc_number:
        return ""
    for prefix in ("Q", "PL", "INV"):
        if doc_number.startswith(prefix):
            return doc_number[len(prefix) :]
    return doc_number


def _draw_box(c, x, y, w, h, label, lines, label_h=14):
    """Draw a labelled box matching the template style."""
    # Label background (gray)
    c.setFillColor(LTGRAY)
    c.rect(x, y + h - label_h, w, label_h, fill=1, stroke=0)
    # Content background (white)
    c.setFillColor(WHITE)
    c.rect(x, y, w, h - label_h, fill=1, stroke=0)
    # Border
    c.setStrokeColor(BLACK)
    c.setLineWidth(0.5)
    c.rect(x, y, w, h, fill=0, stroke=1)
    # Label text
    c.setFillColor(DKGRAY)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(x + 3, y + h - label_h + 3, label)
    # Content text
    c.setFillColor(BLACK)
    c.setFont("Helvetica", 8)
    cy = y + h - label_h - 4
    for line in lines:
        if line:
            c.drawString(x + 3, cy, str(line))
            cy -= 14


def _draw_meta_row(c, y, cols, row_h=28):
    """Draw a meta info row matching the template style."""
    w = 510
    x_start = 50
    n = len(cols)
    col_w = w / n

    # Header background (gray)
    c.setFillColor(LTGRAY)
    c.rect(x_start, y + row_h / 2, w, row_h / 2, fill=1, stroke=0)
    # Content background (white)
    c.setFillColor(WHITE)
    c.rect(x_start, y, w, row_h / 2, fill=1, stroke=0)
    # Border
    c.setStrokeColor(BLACK)
    c.setLineWidth(0.5)
    c.rect(x_start, y, w, row_h, fill=0, stroke=1)
    # Inner grid lines
    for i in range(1, n):
        c.line(x_start + i * col_w, y, x_start + i * col_w, y + row_h)
    # Header text
    c.setFillColor(DKGRAY)
    c.setFont("Helvetica-Bold", 7)
    for i, (label, _) in enumerate(cols):
        c.drawString(x_start + i * col_w + 4, y + row_h / 2 + 2, label)
    # Value text
    c.setFillColor(BLACK)
    c.setFont("Helvetica", 8)
    for i, (_, value) in enumerate(cols):
        c.drawString(x_start + i * col_w + 4, y + 4, str(value or ""))


def _draw_line_items(c, y, col_defs, rows, totals_rows=None, max_h=280):
    """Draw a line items table matching the template style."""
    x_start = 50
    w = 510
    header_h = 14
    row_h = 14
    min_rows = 20

    # Draw header
    c.setFillColor(LTGRAY)
    c.rect(x_start, y + max_h - header_h, w, header_h, fill=1, stroke=0)
    c.setFillColor(DKGRAY)
    c.setFont("Helvetica-Bold", 7)
    x = x_start
    for header, col_w, align in col_defs:
        c.drawString(x + 4, y + max_h - header_h + 2, header)
        x += col_w

    # Draw data rows
    c.setFillColor(BLACK)
    c.setFont("Helvetica", 8)
    all_rows = list(rows)
    # Pad with empty rows
    while len(all_rows) < min_rows:
        all_rows.append([""] * len(col_defs))
    # Add totals rows at the end
    if totals_rows:
        for tr in totals_rows:
            all_rows.append(tr)

    cy = y + max_h - header_h - 4
    for r_idx, row in enumerate(all_rows):
        # Alternate row background
        if r_idx % 2 == 1:
            c.setFillColor(LTGRAY)
            c.rect(x_start, cy - 10, w, row_h, fill=1, stroke=0)
            c.setFillColor(BLACK)

        x = x_start
        for i, (header, col_w, align) in enumerate(col_defs):
            val = row[i] if i < len(row) else ""
            if align == "R":
                c.drawRightString(x + col_w - 4, cy, str(val))
            elif align == "C":
                c.drawCentredString(x + col_w / 2, cy, str(val))
            else:
                c.drawString(x + 4, cy, str(val))
            x += col_w
        cy -= row_h

    # Draw border and grid lines
    c.setStrokeColor(BLACK)
    c.setLineWidth(0.5)
    c.rect(x_start, y, w, max_h, fill=0, stroke=1)
    # Vertical grid lines
    c.setStrokeColor(HexColor("#d0d0d0"))
    c.setLineWidth(0.3)
    x = x_start
    for _, col_w, _ in col_defs:
        x += col_w
        if x < x_start + w:
            c.line(x, y, x, y + max_h)
    # Horizontal grid lines
    cy = y + max_h - header_h
    for _ in range(len(all_rows)):
        c.line(x_start, cy, x_start + w, cy)
        cy -= row_h


# ═══════════════════════════════════════════════════════════════
# QUOTE PDF
# ═══════════════════════════════════════════════════════════════
def build_quote_pdf(quote: dict, client: dict, items: list) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    # Calculate totals
    subtotal = sum(
        item.get("quantity", 0) * item.get("quoted_price", 0) for item in items
    )
    if quote.get("rental_days"):
        subtotal = subtotal * quote["rental_days"]
    tax_rate = quote.get("sales_tax_rate") or 0
    tax = subtotal * tax_rate
    discount = quote.get("discount") or 0
    shipping = quote.get("shipping_cost") or 0
    total = subtotal + tax - discount + shipping

    # ── Header ─────────────────────────────────────────────────
    # Draw teal border at top
    c.setFillColor(TEAL)
    c.rect(0, H - 50, W, 3, fill=1, stroke=0)

    # Logo
    logo_path = config.LOGO_PATH
    if logo_path and logo_path.exists():
        c.drawImage(
            str(logo_path),
            50,
            H - 100,
            width=1.5 * inch,
            height=1.5 * inch,
            preserveAspectRatio=True,
        )

    # Company name
    c.setFillColor(TEAL)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(220, H - 70, "STEEL RIVER TECHNOLOGIES")

    # Company info (right side)
    c.setFillColor(DKGRAY)
    c.setFont("Helvetica", 10)
    c.drawRightString(W - 50, H - 60, "Steel River Technologies")
    c.setFont("Helvetica", 9)
    c.drawRightString(W - 50, H - 75, "1234 Industrial Blvd")
    c.drawRightString(W - 50, H - 90, "Houston, TX 77001")
    c.drawRightString(W - 50, H - 105, "Phone: (555) 123-4567")

    # ── Quote Type ─────────────────────────────────────────────
    quote_type = quote.get("quote_type", "SALE")
    is_rental = quote_type == "RENTAL"

    c.setFillColor(TEAL if not is_rental else ORANGE)
    c.setFont("Helvetica-Bold", 28)
    c.drawString(50, H - 160, f"{quote_type} QUOTE")

    # Quote number and dates
    c.setFillColor(BLACK)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, H - 195, f"Quote #: {quote.get('quote_number', '')}")

    c.setFont("Helvetica", 12)
    c.drawString(
        50,
        H - 215,
        f"Date: {_format_date(quote.get('quote_date', ''))}  |  Valid Until: {_format_date(quote.get('quote_expiration_date', ''))}",
    )

    # ── Quote To / Ship To boxes ────────────────────────────────
    _draw_box(
        c,
        50,
        H - 240,
        230,
        80,
        "Quote To",
        [
            client.get("name", ""),
            client.get("company", ""),
            client.get("site_address", "") or client.get("billing_address", ""),
        ],
    )

    _draw_box(
        c,
        310,
        H - 240,
        230,
        80,
        "Ship To",
        [quote.get("ship_to", "") or "Same as Quote To"],
    )

    # ── Payment Terms and Tax ─────────────────────────────────
    y_pos = H - 340
    c.setFont("Helvetica", 12)
    c.drawString(
        50,
        y_pos,
        f"Payment Terms: {quote.get('payment_term', 'N/A')}  |  Sales Tax: {tax_rate * 100:.2f}%",
    )

    # ── Line Items Table ────────────────────────────────────────
    y_pos -= 30

    # Table header
    c.setFillColor(TEAL)
    c.rect(50, y_pos - 20, W - 100, 25, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, y_pos - 12, "ITEM")
    c.drawString(180, y_pos - 12, "DESCRIPTION")
    c.drawString(350, y_pos - 12, "QTY")
    c.drawString(400, y_pos - 12, "UNIT PRICE")
    c.drawString(480, y_pos - 12, "LEAD TIME")
    c.drawString(530, y_pos - 12, "TOTAL")

    # Table rows
    y_pos -= 25
    for i, item in enumerate(items):
        if i % 2 == 0:
            c.setFillColor(LTGRAY)
            c.rect(50, y_pos - 18, W - 100, 22, fill=1, stroke=0)

        c.setFillColor(BLACK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(55, y_pos, item.get("parts_number", ""))

        c.setFont("Helvetica", 10)
        desc = item.get("description", "")[:30] if item.get("description") else ""
        c.drawString(180, y_pos, desc)

        c.drawRightString(375, y_pos, str(item.get("quantity", "")))
        c.drawRightString(450, y_pos, f"${item.get('quoted_price', 0):.2f}")
        c.drawRightString(510, y_pos, item.get("lead_time", "-") or "-")
        c.drawRightString(
            W - 60,
            y_pos,
            f"${item.get('quantity', 0) * item.get('quoted_price', 0):.2f}",
        )

        y_pos -= 22

    # ── Totals ────────────────────────────────────────────────
    y_pos -= 20

    # Subtotal
    c.setFont("Helvetica", 12)
    c.drawRightString(W - 150, y_pos, "Subtotal:")
    c.drawRightString(W - 60, y_pos, f"${subtotal:.2f}")

    y_pos -= 18
    c.drawRightString(W - 150, y_pos, f"Tax ({tax_rate * 100:.2f}%):")
    c.drawRightString(W - 60, y_pos, f"${tax:.2f}")

    if discount > 0:
        y_pos -= 18
        c.drawRightString(W - 150, y_pos, "Discount:")
        c.drawRightString(W - 60, y_pos, f"-${discount:.2f}")

    if shipping > 0:
        y_pos -= 18
        c.drawRightString(W - 150, y_pos, "Shipping:")
        c.drawRightString(W - 60, y_pos, f"${shipping:.2f}")

    y_pos -= 25
    c.setFillColor(TEAL)
    c.rect(W - 180, y_pos - 5, 120, 30, fill=0, stroke=1)
    c.setFillColor(TEAL)
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(W - 150, y_pos + 10, "TOTAL:")
    c.setFont("Helvetica-Bold", 16)
    c.drawRightString(W - 60, y_pos + 8, f"${total:.2f}")

    # ── Footer ─────────────────────────────────────────────────
    c.setFillColor(DKGRAY)
    c.setFont("Helvetica", 9)
    c.drawCentredString(
        W / 2,
        50,
        "Thank you for your business! | Steel River Technologies | www.steeleriver.com",
    )

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

    # ═══════════════════════════════════════════════════════════════
    # PACKING SLIP PDF
    total = subtotal + tax_amt

    col_defs = [
        ("Part No.", 100, "L"),
        ("Description", 180, "L"),
        ("Quantity", 50, "C"),
        ("Cost", 60, "R"),
        ("Total", 60, "R"),
        ("Lead Time", 60, "C"),
    ]

    rows = []
    for it in items:
        qty = it.get("quantity", 1) or 1
        price = it.get("quoted_price", 0) or 0
        rows.append(
            [
                it.get("parts_number", ""),
                it.get("description", ""),
                str(qty),
                f"{price:,.2f}",
                f"{qty * price:,.2f}T",
                it.get("lead_time", ""),
            ]
        )

    totals_rows = [
        ["", "Sales Tax", "", f"{tax_rate * 100:.2f}%", f"{tax_amt:,.2f}", ""],
        ["", "", "", "Total", f"${total:,.2f}", ""],
    ]

    _draw_line_items(c, 200, col_defs, rows, totals_rows=totals_rows)

    # ── Footer Total Box ────────────────────────────────────
    c.setStrokeColor(BLACK)
    c.setLineWidth(0.5)
    c.rect(50, 40, 510, 20, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(550, 45, f"${total:,.2f}")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════
# PACKING SLIP PDF
# ═══════════════════════════════════════════════════════════════
def build_packing_slip_pdf(
    pl: dict, client: dict, items: list, quote: Optional[dict] = None
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    # ── Header ──────────────────────────────────────────────
    logo_path = config.LOGO_PATH
    if logo_path.exists():
        c.drawImage(
            str(logo_path), 143, 715, width=68, height=21, preserveAspectRatio=True
        )

    c.setFont("Helvetica-Bold", 18)
    c.drawString(216, 720, "STEEL RIVER TECHNOLOGIES")

    c.setFont("Helvetica", 16)
    c.drawString(473, 715, "Packing Slip")

    # ── Date / Invoice Number Box (top right) ───────────────
    _draw_meta_row(
        c,
        666,
        [
            ("Date", _format_date(pl.get("packing_slip_date", ""))),
            ("Invoice Number", _strip_doc_prefix(pl.get("packing_slip_number", ""))),
        ],
        row_h=28,
    )

    # ── Company Address (left) ──────────────────────────────
    c.setFont("Helvetica", 9)
    c.drawString(27, 650, "8810 E CR-95, Midland, TX 79706")
    c.drawString(27, 634, "Phone: 432-618-0169")
    c.drawString(27, 618, "Email: accounting@steelriver-tech.com")

    # ── Bill To Box (right) ─────────────────────────────────
    _draw_box(
        c,
        385,
        570,
        175,
        64,
        "Bill To",
        [client.get("customer_name", ""), client.get("billing_address", "")],
    )

    # ── Ship From (left) + Ship To (right) ──────────────────
    ship_lines = [
        client.get("customer_name", ""),
        client.get("well_address", "") or client.get("billing_address", ""),
    ]
    if pl.get("ship_via"):
        ship_lines.append(pl.get("ship_via", ""))

    _draw_box(c, 27, 550, 60, 34, "Ship From", [pl.get("ship_from", "")])
    _draw_box(c, 385, 490, 175, 64, "Ship To", ship_lines)

    # ── Meta Row: P.O. Number | Quote No. | Ship Via | Terms ─
    _draw_meta_row(
        c,
        446,
        [
            ("P.O. Number", pl.get("po_number", "")),
            (
                "Quote No.",
                _strip_doc_prefix(quote.get("quote_number", "")) if quote else "",
            ),
            ("Ship Via", pl.get("ship_via", "")),
            ("Terms", quote.get("payment_term", "") if quote else ""),
        ],
    )

    # ── Line Items Table ────────────────────────────────────
    col_defs = [
        ("SN", 40, "C"),
        ("PN", 100, "L"),
        ("Description", 200, "L"),
        ("Quantity", 60, "C"),
        ("Weight/Dimension", 110, "C"),
    ]

    rows = []
    for i, it in enumerate(items, 1):
        rows.append(
            [
                str(i),
                it.get("parts_number", ""),
                it.get("description", ""),
                str(it.get("quantity", "")),
                it.get("dimensions", ""),
            ]
        )

    _draw_line_items(c, 160, col_defs, rows, max_h=280)

    # ── Signature Block ─────────────────────────────────────
    sig_y = 120
    c.setFont("Helvetica", 9)
    c.drawString(27, sig_y + 40, "Receiver Print Name: ___________________________")
    c.drawString(327, sig_y + 40, "Supplier Print Name: ___________________________")
    c.drawString(27, sig_y + 20, "Receiver Signature: ___________________________")
    c.drawString(327, sig_y + 20, "Supplier Signature: ___________________________")
    c.drawString(27, sig_y, "Date: _____________________")
    c.drawString(327, sig_y, "Date: _____________________")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════
# INVOICE PDF
# ═══════════════════════════════════════════════════════════════
def build_invoice_pdf(
    inv: dict, pl: dict, client: dict, items: list, quote: Optional[dict] = None
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    # ── Header ──────────────────────────────────────────────
    logo_path = config.LOGO_PATH
    if logo_path.exists():
        c.drawImage(
            str(logo_path), 143, 715, width=68, height=21, preserveAspectRatio=True
        )

    c.setFont("Helvetica-Bold", 18)
    c.drawString(216, 720, "STEEL RIVER TECHNOLOGIES")

    c.setFont("Helvetica", 16)
    c.drawString(473, 715, "Invoice")

    # ── Date / Invoice Number Box (top right) ───────────────
    _draw_meta_row(
        c,
        666,
        [
            ("Date", _format_date(inv.get("invoice_date", ""))),
            ("Invoice Number", _strip_doc_prefix(inv.get("invoice_number", ""))),
        ],
        row_h=28,
    )

    # ── Company Address (left) ──────────────────────────────
    c.setFont("Helvetica", 9)
    c.drawString(27, 650, "8810 E CR-95, Midland, TX 79706")
    c.drawString(27, 634, "Phone: 432-618-0169")
    c.drawString(27, 618, "Email: accounting@steelriver-tech.com")

    # ── Bill To Box (right) ─────────────────────────────────
    _draw_box(
        c,
        385,
        570,
        175,
        64,
        "Bill To",
        [client.get("name", ""), client.get("company", ""), client.get("billing_address", "")],
    )

    # ── Ship From (left) + Ship To (right) ──────────────────
    ship_lines = [
        client.get("name", ""),
        client.get("site_address", "") or client.get("billing_address", ""),
    ]

    _draw_box(c, 27, 550, 60, 34, "Ship From", [pl.get("ship_from", "")])
    _draw_box(c, 385, 490, 175, 64, "Ship To", ship_lines)

    # ── Meta Row: P.O. Number | Quote No. | Ship Via | Terms ─
    _draw_meta_row(
        c,
        446,
        [
            ("P.O. Number", inv.get("purchase_number", "")),
            (
                "Quote No.",
                _strip_doc_prefix(quote.get("quote_number", "")) if quote else "",
            ),
            ("Ship Via", pl.get("ship_via", "")),
            ("Terms", inv.get("payment_term", "")),
        ],
    )

    # ── Line Items Table ────────────────────────────────────
    col_defs = [
        ("SN", 40, "C"),
        ("PN", 100, "L"),
        ("Description", 200, "L"),
        ("Quantity", 60, "C"),
        ("Weight/Dimension", 110, "C"),
    ]

    rows = []
    for i, it in enumerate(items, 1):
        rows.append(
            [
                str(i),
                it.get("parts_number", ""),
                it.get("description", ""),
                str(it.get("quantity", "")),
                it.get("dimensions", ""),
            ]
        )

    _draw_line_items(c, 160, col_defs, rows, max_h=280)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()
