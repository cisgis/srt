"""
PDF generation for Quote, Packing Slip, and Invoice documents.
Matches the Steel River Technologies template layout exactly.
"""
import io
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config

W, H = letter  # 612 x 792

# ── Colours ──────────────────────────────────────────────────
BLACK  = colors.black
WHITE  = colors.white
LTGRAY = colors.HexColor("#f0f0f0")
MGRAY  = colors.HexColor("#d0d0d0")
DKGRAY = colors.HexColor("#555555")

# ── Styles ───────────────────────────────────────────────────
base = getSampleStyleSheet()

def _style(name, parent="Normal", **kw):
    s = ParagraphStyle(name, parent=base[parent])
    for k, v in kw.items():
        setattr(s, k, v)
    return s

S_NORMAL  = _style("sn",  fontSize=8,  leading=10)
S_SMALL   = _style("ss",  fontSize=7,  leading=9,  textColor=DKGRAY)
S_BOLD    = _style("sb",  fontSize=8,  leading=10, fontName="Helvetica-Bold")
S_TITLE   = _style("st",  fontSize=22, leading=24, fontName="Helvetica-Bold")
S_DOCTYPE = _style("sdt", fontSize=16, leading=18, fontName="Helvetica", alignment=TA_RIGHT)
S_HDR     = _style("shdr",fontSize=7,  leading=9,  fontName="Helvetica-Bold", textColor=DKGRAY)
S_R       = _style("sr",  fontSize=8,  leading=10, alignment=TA_RIGHT)
S_C       = _style("sc",  fontSize=8,  leading=10, alignment=TA_CENTER)

def _logo():
    p = config.LOGO_PATH
    if p.exists():
        return Image(str(p), width=0.9*inch, height=0.9*inch)
    return Paragraph("<b>SRT</b>", base["Normal"])

def _box_table(label, value, w=2.2*inch):
    """Small labelled box matching the template."""
    return Table(
        [[Paragraph(label, S_HDR)], [Paragraph(str(value or ""), S_NORMAL)]],
        colWidths=[w],
        style=TableStyle([
            ("BOX",    (0,0),(-1,-1), 0.5, BLACK),
            ("TOPPADDING",    (0,0),(-1,-1), 3),
            ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
        ])
    )

def _address_box(label, lines, w=2.5*inch):
    content = "<br/>".join(str(l) for l in lines if l)
    return Table(
        [[Paragraph(label, S_HDR)], [Paragraph(content, S_NORMAL)]],
        colWidths=[w],
        style=TableStyle([
            ("BOX",    (0,0),(-1,-1), 0.5, BLACK),
            ("TOPPADDING",    (0,0),(-1,-1), 3),
            ("BOTTOMPADDING", (0,0),(-1,-1), 3),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
            ("ROWBACKGROUNDS", (0,0),(0,0), [LTGRAY]),
        ])
    )

def _meta_row(cols):
    """Horizontal info row: [(label, value), ...]"""
    headers = [Paragraph(c[0], S_HDR)  for c in cols]
    values  = [Paragraph(str(c[1] or ""), S_NORMAL) for c in cols]
    n = len(cols)
    col_w = [6.5*inch / n] * n
    t = Table([headers, values], colWidths=col_w)
    t.setStyle(TableStyle([
        ("BOX",         (0,0),(-1,-1), 0.5, BLACK),
        ("INNERGRID",   (0,0),(-1,-1), 0.5, BLACK),
        ("BACKGROUND",  (0,0),(-1, 0), LTGRAY),
        ("TOPPADDING",  (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
        ("LEFTPADDING", (0,0),(-1,-1), 5),
    ]))
    return t

def _line_items_table(rows, col_defs, totals_rows=None):
    """
    col_defs = [(header, width, align), ...]
    rows     = list of lists of cell values
    """
    headers = [Paragraph(c[0], S_HDR) for c in col_defs]
    col_w   = [c[1] for c in col_defs]

    def _cell(val, align):
        s = S_R if align == "R" else (S_C if align == "C" else S_NORMAL)
        return Paragraph(str(val) if val is not None else "", s)

    body = []
    for r in rows:
        body.append([_cell(r[i], col_defs[i][2]) for i in range(len(col_defs))])

    # Pad to minimum 20 rows so table looks like the template
    while len(body) < 20:
        body.append([""] * len(col_defs))

    all_rows = [headers] + body
    if totals_rows:
        for tr in totals_rows:
            all_rows.append(tr)

    ts = TableStyle([
        ("BOX",           (0,0), (-1,-1), 0.5, BLACK),
        ("INNERGRID",     (0,0), (-1,-1), 0.3, MGRAY),
        ("BACKGROUND",    (0,0), (-1, 0), LTGRAY),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("FONTNAME",      (0,0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 7),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LTGRAY]),
    ])
    t = Table(all_rows, colWidths=col_w, repeatRows=1)
    t.setStyle(ts)
    return t

def _header_block(doc_type_label, company_address_lines, right_boxes):
    """
    Top header: logo + company name + doc type on one row,
    company address left, right_boxes stacked on right.
    """
    logo = _logo()
    co_name = Paragraph(f"<b>{config.COMPANY_NAME}</b>", S_TITLE)
    doc_lbl = Paragraph(doc_type_label, S_DOCTYPE)

    top_row = Table(
        [[logo, co_name, doc_lbl]],
        colWidths=[1.0*inch, 4.0*inch, 1.5*inch],
        style=TableStyle([
            ("VALIGN",  (0,0),(-1,-1), "MIDDLE"),
            ("LEFTPADDING",  (0,0),(0,0), 0),
            ("RIGHTPADDING", (2,0),(2,0), 0),
        ])
    )
    return top_row

# ═══════════════════════════════════════════════════════════════
# QUOTE PDF
# ═══════════════════════════════════════════════════════════════
def build_quote_pdf(quote: dict, client: dict, items: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []

    # ── Header ─────────────────────────────────────────────
    story.append(_header_block("Sales Quote", [], []))
    story.append(Spacer(1, 6))

    # Company address (left) + Quote To box (right)
    addr_lines = [
        config.COMPANY_ADDRESS,
        f"Phone: {config.COMPANY_PHONE}",
        f"Email: {config.COMPANY_EMAIL_CONTACT}",
    ]
    co_addr = Paragraph("<br/>".join(addr_lines), S_SMALL)

    bill_lines = [client.get("customer_name",""), client.get("billing_address","")]
    quote_to_box = _address_box("Quote To", bill_lines, w=2.8*inch)

    ship_to_box  = _address_box("Ship To", [quote.get("ship_to","")], w=2.8*inch)

    row1 = Table(
        [[co_addr, "", quote_to_box],
         ["",      "", ship_to_box]],
        colWidths=[3.0*inch, 0.3*inch, 2.8*inch],
        style=TableStyle([
            ("VALIGN",       (0,0),(-1,-1), "TOP"),
            ("TOPPADDING",   (0,0),(-1,-1), 2),
            ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ])
    )

    # Ship From box (left) – mirrors template
    ship_from_box = _address_box("Ship From", [quote.get("ship_from","")], w=2.3*inch)
    row2 = Table(
        [[ship_from_box]],
        colWidths=[6.5*inch],
        style=TableStyle([("ALIGN",(0,0),(0,0),"LEFT")])
    )

    story.append(row1)
    story.append(Spacer(1, 4))
    story.append(ship_from_box)
    story.append(Spacer(1, 6))

    # ── Meta row: Date | Quote No. | Expiration Date | Term ─
    story.append(_meta_row([
        ("Date",            quote.get("quote_date","")),
        ("Quote No.",       quote.get("quote_number","")),
        ("Expiration Date", quote.get("quote_expiration_date","")),
        ("Term",            quote.get("payment_term","")),
    ]))
    story.append(Spacer(1, 8))

    # ── Line items ──────────────────────────────────────────
    col_defs = [
        ("Part No.",    1.3*inch, "L"),
        ("Description", 2.5*inch, "L"),
        ("Quantity",    0.65*inch,"C"),
        ("Cost",        0.85*inch,"R"),
        ("Total",       0.85*inch,"R"),
        ("Lead Time",   0.7*inch, "C"),
    ]
    tax_rate = quote.get("sales_tax_rate", 0) or 0
    subtotal = sum((it.get("quoted_price",0) or 0) * (it.get("quantity",1) or 1) for it in items)
    tax_amt  = subtotal * tax_rate
    total    = subtotal + tax_amt

    rows = []
    for it in items:
        qty   = it.get("quantity", 1) or 1
        price = it.get("quoted_price", 0) or 0
        rows.append([
            it.get("parts_number",""),
            it.get("product_service_description",""),
            qty,
            f"{price:,.2f}",
            f"{qty*price:,.2f}T",
            it.get("lead_time",""),
        ])

    totals_rows = [
        [Paragraph("Sales Tax", S_NORMAL),
         Paragraph(f"{tax_rate*100:.2f}%", S_C), "", "", Paragraph(f"{tax_amt:,.2f}", S_R), ""],
        ["", "", "", Paragraph("Total", S_BOLD),
         Paragraph(f"${total:,.2f}", S_BOLD), ""],
    ]
    story.append(_line_items_table(rows, col_defs, totals_rows))

    # ── Footer total box ────────────────────────────────────
    story.append(Spacer(1, 6))
    total_box = Table(
        [[Paragraph(f"${total:,.2f}", _style("tf", fontSize=14, fontName="Helvetica-Bold", alignment=TA_RIGHT))]],
        colWidths=[6.5*inch],
        style=TableStyle([
            ("BOX",(0,0),(-1,-1),0.5,BLACK),
            ("TOPPADDING",(0,0),(-1,-1),4),
            ("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("RIGHTPADDING",(0,0),(-1,-1),8),
        ])
    )
    story.append(total_box)

    doc.build(story)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════
# PACKING SLIP PDF
# ═══════════════════════════════════════════════════════════════
def build_packing_slip_pdf(pl: dict, client: dict, items: list, quote: dict = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []

    story.append(_header_block("Packing Slip", [], []))
    story.append(Spacer(1, 6))

    addr_lines = [
        config.COMPANY_ADDRESS,
        f"Phone: {config.COMPANY_PHONE}",
        f"Email: {config.COMPANY_EMAIL_ACCOUNTING}",
    ]
    co_addr = Paragraph("<br/>".join(addr_lines), S_SMALL)

    # Right side: Date/Invoice Number box + Bill To + Ship To
    date_inv = _meta_row([
        ("Date",           pl.get("packing_slip_date","")),
        ("Invoice Number", pl.get("packing_slip_number","")),
    ])
    bill_lines = [client.get("customer_name",""), client.get("billing_address","")]
    bill_box = _address_box("Bill To", bill_lines, w=2.8*inch)

    ship_lines = [
        client.get("customer_name",""),
        client.get("well_address","") or client.get("billing_address",""),
        pl.get("ship_via",""),
    ]
    ship_box = _address_box("Ship To", ship_lines, w=2.8*inch)

    right_col = Table(
        [[date_inv], [Spacer(1,4)], [bill_box], [Spacer(1,4)], [ship_box]],
        colWidths=[2.8*inch],
        style=TableStyle([("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)])
    )

    ship_from_box = _address_box("Ship From", [pl.get("ship_from","")], w=2.3*inch)

    top = Table(
        [[co_addr, "", right_col]],
        colWidths=[3.2*inch, 0.3*inch, 2.8*inch],
        style=TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),2)])
    )
    story.append(top)
    story.append(Spacer(1,6))
    story.append(ship_from_box)
    story.append(Spacer(1,6))

    # Meta: P.O. Number | Quote No. | Ship Via | Terms
    story.append(_meta_row([
        ("P.O. Number", pl.get("po_number","")),
        ("Quote No.",   quote.get("quote_number","") if quote else ""),
        ("Ship Via",    pl.get("ship_via","")),
        ("Terms",       quote.get("payment_term","") if quote else pl.get("payment_term","")),
    ]))
    story.append(Spacer(1,8))

    # Line items
    col_defs = [
        ("SN",               0.4*inch,  "C"),
        ("PN",               1.3*inch,  "L"),
        ("Description",      3.0*inch,  "L"),
        ("Quantity",         0.75*inch, "C"),
        ("Weight/Dimension", 1.05*inch, "C"),
    ]
    rows = []
    for i, it in enumerate(items, 1):
        rows.append([
            i,
            it.get("parts_number",""),
            it.get("product_service_description",""),
            it.get("quantity", ""),
            it.get("dimensions",""),
        ])

    story.append(_line_items_table(rows, col_defs))
    story.append(Spacer(1, 12))

    # Signature block
    sig = Table(
        [
            [Paragraph("Receiver Print Name: ___________________________", S_NORMAL),
             Paragraph("Supplier Print Name: ___________________________", S_NORMAL)],
            [Spacer(1,8), Spacer(1,8)],
            [Paragraph("Receiver Signature: ___________________________", S_NORMAL),
             Paragraph("Supplier Signature: ___________________________", S_NORMAL)],
            [Spacer(1,8), Spacer(1,8)],
            [Paragraph("Date: _____________________", S_NORMAL),
             Paragraph("Date: _____________________", S_NORMAL)],
        ],
        colWidths=[3.25*inch, 3.25*inch],
        style=TableStyle([
            ("TOPPADDING",(0,0),(-1,-1),2),
            ("BOTTOMPADDING",(0,0),(-1,-1),2),
        ])
    )
    story.append(sig)

    doc.build(story)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════
# INVOICE PDF  (mirrors Packing Slip layout, no signature block)
# ═══════════════════════════════════════════════════════════════
def build_invoice_pdf(inv: dict, pl: dict, client: dict, items: list, quote: dict = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []

    story.append(_header_block("Invoice", [], []))
    story.append(Spacer(1, 6))

    addr_lines = [
        config.COMPANY_ADDRESS,
        f"Phone: {config.COMPANY_PHONE}",
        f"Email: {config.COMPANY_EMAIL_ACCOUNTING}",
    ]
    co_addr = Paragraph("<br/>".join(addr_lines), S_SMALL)

    date_inv = _meta_row([
        ("Date",           inv.get("invoice_date","")),
        ("Invoice Number", inv.get("invoice_number","")),
    ])
    bill_lines = [client.get("customer_name",""), client.get("billing_address","")]
    bill_box = _address_box("Bill To", bill_lines, w=2.8*inch)
    ship_lines = [
        client.get("customer_name",""),
        client.get("well_address","") or client.get("billing_address",""),
    ]
    ship_box = _address_box("Ship To", ship_lines, w=2.8*inch)

    right_col = Table(
        [[date_inv],[Spacer(1,4)],[bill_box],[Spacer(1,4)],[ship_box]],
        colWidths=[2.8*inch],
        style=TableStyle([("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)])
    )
    ship_from_box = _address_box("Ship From", [pl.get("ship_from","")], w=2.3*inch)

    top = Table(
        [[co_addr, "", right_col]],
        colWidths=[3.2*inch, 0.3*inch, 2.8*inch],
        style=TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),2)])
    )
    story.append(top)
    story.append(Spacer(1,6))
    story.append(ship_from_box)
    story.append(Spacer(1,6))

    story.append(_meta_row([
        ("P.O. Number",   inv.get("purchase_number","")),
        ("Quote No.",     quote.get("quote_number","") if quote else ""),
        ("Ship Via",      pl.get("ship_via","")),
        ("Terms",         inv.get("payment_term","")),
    ]))
    story.append(Spacer(1,8))

    col_defs = [
        ("SN",               0.4*inch,  "C"),
        ("PN",               1.3*inch,  "L"),
        ("Description",      3.0*inch,  "L"),
        ("Quantity",         0.75*inch, "C"),
        ("Weight/Dimension", 1.05*inch, "C"),
    ]
    rows = []
    for i, it in enumerate(items, 1):
        rows.append([i, it.get("parts_number",""), it.get("product_service_description",""),
                     it.get("quantity",""), it.get("dimensions","")])

    story.append(_line_items_table(rows, col_defs))

    doc.build(story)
    return buf.getvalue()
