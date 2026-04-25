from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime, timedelta
import io
from app.database import get_db, close_db, next_doc_number
from app.services import pdf_service, email_service
from app.logger import log_info, log_error

router = APIRouter(prefix="/invoices", tags=["invoices"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
PAYMENT_TERMS = ["COD", "Net 7", "Net 14", "Net 21", "Net 30", "Net 60"]
_pdf_browser = None


async def _get_pdf_browser():
    global _pdf_browser
    from playwright.async_api import async_playwright

    try:
        if _pdf_browser is not None and _pdf_browser.is_connected():
            try:
                await _pdf_browser.pages
                return _pdf_browser
            except:
                pass
    except:
        pass
    
    p = await async_playwright().start()
    _pdf_browser = await p.chromium.launch(headless=True)
    return _pdf_browser


@router.get("/", response_class=HTMLResponse)
def inv_list(request: Request):
    db = get_db()
    invoices = db.execute("""
        SELECT i.*, c.name as client_name, pl.packing_slip_number
        FROM Invoice i
        LEFT JOIN Clients c ON i.client_id=c.client_id
        LEFT JOIN Packing_Slip pl ON i.packing_slip_number=pl.packing_slip_number
        ORDER BY i.created_at DESC
    """).fetchall()
    close_db()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    invoice_list = []
    for r in (invoices if invoices else []):
        inv = dict(r)
        due_date = None
        if inv.get("payment_term") and inv.get("payment_term") != "COD":
            try:
                days = int(inv["payment_term"].replace("Net ", "").replace("net ", ""))
                due_date = (datetime.strptime(inv.get("invoice_date", today), "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
            except:
                pass
        inv["due_date"] = due_date
        inv["is_overdue"] = due_date and due_date < today
        invoice_list.append(inv)
    
    return templates.TemplateResponse("invoices/list.html", {
        "request": request,
        "invoices": invoice_list,
        "today": today,
    })


@router.get("/new", response_class=HTMLResponse)
def inv_new(request: Request, pl_number: str = "", client_id: str = "", ship_to: str = "", items_json: str = "", po_number: str = "", error: str = ""):
    db = get_db()
    
    invoice = None
    client = {}
    items = []
    quote = {}
    total = 0
    
    if pl_number:
        pl = db.execute("SELECT * FROM Packing_Slip WHERE packing_slip_number=?", (pl_number,)).fetchone()
        if pl:
            pl = dict(pl)
            
            if pl.get("client_id"):
                c = db.execute("SELECT * FROM Clients WHERE client_id=?", (pl["client_id"],)).fetchone()
                if c:
                    client = dict(c)
            
            items = [dict(r) for r in db.execute("""
                SELECT psi.*, pn.description, pn.resale_price
                FROM Packing_Slip_Items psi 
                JOIN PartNumber pn ON psi.parts_number=pn.parts_number 
                WHERE psi.packing_slip_number=?
            """, (pl_number,)).fetchall()]
            
            if pl.get("quote_number"):
                quote = dict(db.execute("SELECT * FROM Quote WHERE quote_number=?", (pl["quote_number"],)).fetchone() or {})
            
            total = sum(item.get("resale_price", 0) or 0 for item in items)
    elif client_id:
        c = db.execute("SELECT * FROM Clients WHERE client_id=?", (client_id,)).fetchone()
        if c:
            client = dict(c)
    
    invoice_number = next_doc_number(db, "INV", datetime.now().strftime("%m%d%Y"))
    db.commit()
    close_db()
    
    discount_amount = quote.get("discount_amount", 0) or 0
    discount_percent = quote.get("discount_percent", 0) or 0
    shipping_cost = quote.get("shipping_cost", 0) or 0
    sales_tax_rate = quote.get("sales_tax_rate", 0) or 0
    
    if discount_percent > 0:
        discount_amount = total * (discount_percent / 100)
    
    subtotal = total - discount_amount
    sales_tax = subtotal * sales_tax_rate
    grand_total = subtotal + shipping_cost + sales_tax
    
    default_payment_term = quote.get("payment_term", "") if quote else ""
    
    return templates.TemplateResponse("invoices/form.html", {
        "request": request,
        "pl_number": pl_number,
        "client_id": client_id,
        "ship_to": ship_to,
        "items_json": items_json,
        "po_number": po_number,
        "invoice": invoice,
        "invoice_number": invoice_number,
        "client": client,
        "items": items,
        "today": datetime.now().strftime("%Y-%m-%d"),
        "quote": quote,
        "total": total,
        "discount_amount": discount_amount,
        "discount_percent": discount_percent,
        "shipping_cost": shipping_cost,
        "sales_tax_rate": sales_tax_rate,
        "subtotal": subtotal,
        "sales_tax": sales_tax,
        "grand_total": grand_total,
        "default_payment_term": default_payment_term,
        "error": error,
    })


@router.post("/new")
async def inv_create(
    request: Request,
    inv_number: str = Form(""),
    packing_slip_number: str = Form(...),
    purchase_number: str = Form(""),
    po_attachment: UploadFile = File(None),
    pl_attachment: UploadFile = File(None),
    payment_term: str = Form(""),
    invoice_date: str = Form(...),
    client_id: str = Form(""),
):
    now = datetime.now().isoformat()
    user = request.session.get("username", "unknown")

    db = get_db()
    
    mmddyyyy = datetime.strptime(invoice_date, "%Y-%m-%d").strftime("%m%d%Y")
    
    if inv_number:
        invnum = inv_number
        db.execute("INSERT OR IGNORE INTO doc_sequences (doc_number) VALUES (?)", (invnum,))
    else:
        invnum = next_doc_number(db, "INV", mmddyyyy)
    
    po_attachment_path = None
    if po_attachment and po_attachment.filename:
        upload_dir = Path("data/uploads/po_attachments")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / po_attachment.filename
        with open(file_path, "wb") as f:
            f.write(await po_attachment.read())
        po_attachment_path = f"data/uploads/po_attachments/{po_attachment.filename}"
    
    pl_attachment_path = None
    if pl_attachment and pl_attachment.filename:
        upload_dir = Path("data/uploads/pl_attachments")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / pl_attachment.filename
        with open(file_path, "wb") as f:
            f.write(await pl_attachment.read())
        pl_attachment_path = f"data/uploads/pl_attachments/{pl_attachment.filename}"
    
    if not purchase_number and not po_attachment_path:
        error_url = "/invoices/new"
        if packing_slip_number:
            error_url += f"?pl_number={packing_slip_number}&client_id={client_id or ''}"
        error_url += "&error=PO+Number+or+PDF+attachment+is+required"
        return RedirectResponse(error_url, status_code=303)
    
    db.execute(
        """INSERT INTO Invoice (invoice_number, packing_slip_number, purchase_number, po_attachment_path, pl_attachment_path, payment_term, invoice_date, client_id, created_by, created_at, modified_by, modified_at, status) 
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            invnum,
            packing_slip_number,
            purchase_number or None,
            po_attachment_path,
            pl_attachment_path,
            payment_term or None,
            invoice_date,
            client_id or None,
            user,
            now,
            user,
            now,
            "OPEN",
        ),
    )
    db.commit()
    log_info(f"Created Invoice: {invnum} by {user}")
    close_db()
    return RedirectResponse(f"/invoices/{invnum}", status_code=303)


@router.get("/{inv_number}", response_class=HTMLResponse)
def inv_detail(request: Request, inv_number: str, error: str = ""):
    db = get_db()
    inv_row = db.execute("SELECT * FROM Invoice WHERE invoice_number=?", (inv_number,)).fetchone()
    if not inv_row:
        close_db()
        return HTMLResponse("Invoice not found", status_code=404)
    inv = dict(inv_row)
    
    client = {}
    quote = {}
    total = 0
    
    if inv.get("client_id"):
        c = db.execute("SELECT * FROM Clients WHERE client_id=?", (inv["client_id"],)).fetchone()
        if c:
            client = dict(c)
    
    pl = db.execute("SELECT * FROM Packing_Slip WHERE packing_slip_number=?", (inv.get("packing_slip_number", ""),)).fetchone()
    if pl:
        pl = dict(pl)
    if pl and pl.get("quote_number"):
        quote = dict(db.execute("SELECT * FROM Quote WHERE quote_number=?", (pl["quote_number"],)).fetchone() or {})
    
    items = [dict(r) for r in db.execute("""
        SELECT psi.*, pn.description, pn.resale_price
        FROM Packing_Slip_Items psi 
        JOIN PartNumber pn ON psi.parts_number=pn.parts_number 
        WHERE psi.packing_slip_number=?
    """, (inv.get("packing_slip_number", ""),)).fetchall()]
    close_db()
    
    total = sum(item.get("resale_price", 0) or 0 for item in items)
    
    discount_amount = quote.get("discount_amount", 0) or 0
    discount_percent = quote.get("discount_percent", 0) or 0
    shipping_cost = quote.get("shipping_cost", 0) or 0
    sales_tax_rate = quote.get("sales_tax_rate", 0) or 0
    
    if discount_percent > 0:
        discount_amount = total * (discount_percent / 100)
    
    subtotal = total - discount_amount
    sales_tax = subtotal * sales_tax_rate
    grand_total = subtotal + shipping_cost + sales_tax
    
    default_payment_term = quote.get("payment_term", "") if quote else ""
    
    return templates.TemplateResponse("invoices/form.html", {
        "request": request,
        "invoice": inv,
        "client": client,
        "items": items,
        "today": datetime.now().strftime("%Y-%m-%d"),
        "quote": quote,
        "total": total,
        "discount_amount": discount_amount,
        "discount_percent": discount_percent,
        "shipping_cost": shipping_cost,
        "sales_tax_rate": sales_tax_rate,
        "subtotal": subtotal,
        "sales_tax": sales_tax,
        "grand_total": grand_total,
        "default_payment_term": default_payment_term,
        "error": error,
    })


@router.post("/{inv_number}")
async def inv_update(
    request: Request,
    inv_number: str,
    inv_number_form: str = Form(""),
    packing_slip_number: str = Form(""),
    purchase_number: str = Form(""),
    po_attachment: UploadFile = File(None),
    pl_attachment: UploadFile = File(None),
    payment_term: str = Form(""),
    invoice_date: str = Form(...),
    client_id: str = Form(""),
):
    now = datetime.now().isoformat()
    user = request.session.get("username", "unknown")
    
    po_attachment_path = None
    if po_attachment and po_attachment.filename:
        upload_dir = Path("data/uploads/po_attachments")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / po_attachment.filename
        with open(file_path, "wb") as f:
            f.write(await po_attachment.read())
        po_attachment_path = f"data/uploads/po_attachments/{po_attachment.filename}"
    
    pl_attachment_path = None
    if pl_attachment and pl_attachment.filename:
        upload_dir = Path("data/uploads/pl_attachments")
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / pl_attachment.filename
        with open(file_path, "wb") as f:
            f.write(await pl_attachment.read())
        pl_attachment_path = f"data/uploads/pl_attachments/{pl_attachment.filename}"
    
    db = get_db()
    
    existing_inv = db.execute("SELECT po_attachment_path, pl_attachment_path, purchase_number FROM Invoice WHERE invoice_number=?", (inv_number,)).fetchone()
    existing_attachment = existing_inv["po_attachment_path"] if existing_inv else None
    existing_pl_attachment = existing_inv["pl_attachment_path"] if existing_inv else None
    existing_po = existing_inv["purchase_number"] if existing_inv else None
    
    if not po_attachment_path:
        po_attachment_path = existing_attachment
    
    if not pl_attachment_path:
        pl_attachment_path = existing_pl_attachment
    
    final_po = purchase_number or existing_po
    
    if not final_po and not po_attachment_path:
        return RedirectResponse(f"/invoices/{inv_number}?error=PO+Number+or+PDF+attachment+is+required", status_code=303)
    
    db.execute(
        """UPDATE Invoice SET 
           packing_slip_number=?, purchase_number=?, po_attachment_path=?, pl_attachment_path=?, payment_term=?, 
           invoice_date=?, client_id=?, modified_by=?, modified_at=?
           WHERE invoice_number=?""",
        (
            packing_slip_number or None,
            purchase_number or None,
            po_attachment_path,
            pl_attachment_path,
            payment_term or None,
            invoice_date,
            client_id or None,
            user,
            now,
            inv_number,
        ),
    )
    db.commit()
    log_info(f"Updated Invoice: {inv_number} by {user}")
    close_db()
    return RedirectResponse(f"/invoices/{inv_number}?success=1", status_code=303)


@router.post("/{inv_number}/update-po")
async def inv_update_po(inv_number: str, purchase_number: str = Form(...)):
    db = get_db()
    db.execute(
        "UPDATE Invoice SET purchase_number=? WHERE invoice_number=?",
        (purchase_number, inv_number),
    )
    db.commit()
    close_db()
    return RedirectResponse(f"/invoices/{inv_number}", status_code=303)


@router.get("/{inv_number}/pdf")
def inv_pdf(request: Request, inv_number: str):
    db = get_db()
    inv_row = db.execute("SELECT * FROM Invoice WHERE invoice_number=?", (inv_number,)).fetchone()
    if not inv_row:
        close_db()
        return HTMLResponse("Invoice not found", status_code=404)
    inv = dict(inv_row)
    pl = {}
    if inv.get("packing_slip_number"):
        row = db.execute(
            "SELECT * FROM Packing_Slip WHERE packing_slip_number=?",
            (inv["packing_slip_number"],),
        ).fetchone()
        if row:
            pl = dict(row)
    client, quote = {}, {}
    if inv.get("client_id"):
        row = db.execute(
            "SELECT * FROM Clients WHERE client_id=?", (inv["client_id"],)
        ).fetchone()
        if row:
            client = dict(row)
    if pl.get("quote_number"):
        qrow = db.execute(
            "SELECT * FROM Quote WHERE quote_number=?", (pl["quote_number"],)
        ).fetchone()
        if qrow:
            quote = dict(qrow)
    
    items = [
        dict(r)
        for r in db.execute(
            """
        SELECT psi.*, pn.description, pn.resale_price
        FROM Packing_Slip_Items psi 
        JOIN PartNumber pn ON psi.parts_number=pn.parts_number
        WHERE psi.packing_slip_number=?
    """,
            (inv.get("packing_slip_number", ""),),
        ).fetchall()
    ]
    close_db()
    
    subtotal = sum(item.get("resale_price", 0) or 0 for item in items)
    discount_amount = quote.get("discount_amount", 0) or 0
    discount_percent = quote.get("discount_percent", 0) or 0
    shipping_cost = quote.get("shipping_cost", 0) or 0
    sales_tax_rate = quote.get("sales_tax_rate", 0) or 0
    
    if discount_percent > 0:
        discount_amount = subtotal * (discount_percent / 100)
    
    after_discount = subtotal - discount_amount
    sales_tax = after_discount * sales_tax_rate
    grand_total = after_discount + shipping_cost + sales_tax
    
    import base64
    from config import LOGO_PATH
    
    logo_b64 = ""
    logo_path = LOGO_PATH
    if logo_path and logo_path.exists():
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode("utf-8")
            if logo_path.suffix.lower() == ".png":
                logo_b64 = f"data:image/png;base64,{logo_b64}"
            elif logo_path.suffix.lower() == ".webp":
                logo_b64 = f"data:image/webp;base64,{logo_b64}"
    
    context = {
        "invoice": inv,
        "pl": pl,
        "client": client,
        "quote": quote,
        "items": items,
        "logo_data": logo_b64,
        "subtotal_value": subtotal,
        "discount_amount": discount_amount,
        "shipping_cost": shipping_cost,
        "sales_tax": sales_tax,
        "grand_total": grand_total,
    }
    
    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
    html_content = templates.get_template("invoices/pdf.html").render(context)
    
    import asyncio
    from playwright.async_api import async_playwright
    
    async def generate_pdf():
        browser = await _get_pdf_browser()
        page = await browser.new_page()
        await page.set_content(html_content, wait_until="domcontentloaded", timeout=30000)
        pdf_content = await page.pdf(
            format="Letter",
            print_background=True,
            display_header_footer=False,
        )
        await page.close()
        return pdf_content
    
    pdf_content = asyncio.run(generate_pdf())
    
    from pypdf import PdfWriter
    
    merger = PdfWriter()
    merger.append(io.BytesIO(pdf_content))
    
    print(f"DEBUG: inv['pl_attachment_path'] = {inv.get('pl_attachment_path')}")
    
    if inv.get("po_attachment_path"):
        po_path = Path(inv["po_attachment_path"])
        print(f"DEBUG: po_path exists = {po_path.exists()}")
        if po_path.exists():
            merger.append(str(po_path))
    
    if inv.get("pl_attachment_path"):
        pl_path = Path(inv["pl_attachment_path"])
        print(f"DEBUG: pl_path exists = {pl_path.exists()}")
        if pl_path.exists():
            merger.append(str(pl_path))
    
    output = io.BytesIO()
    merger.write(output)
    merger.close()
    
    return Response(
        content=output.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{inv_number}.pdf"'},
    )


@router.get("/{inv_number}/payment-received")
def inv_payment_received(request: Request, inv_number: str):
    db = get_db()
    db.execute(
        "UPDATE Invoice SET status='Payment Received', modified_at=? WHERE invoice_number=?",
        (datetime.now().isoformat(), inv_number),
    )
    db.commit()
    close_db()
    log_info(f"Invoice {inv_number} marked as Payment Received")
    return RedirectResponse(f"/invoices/{inv_number}", status_code=303)


@router.post("/{inv_number}/send")
async def inv_send(
    inv_number: str,
    to_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
):
    db = get_db()
    inv = db.execute(
        "SELECT * FROM Invoice WHERE invoice_number=?", (inv_number,)
    ).fetchone()
    if not inv:
        close_db()
        return {"ok": False, "error": f"Invoice '{inv_number}' not found"}

    inv = dict(inv)
    pl, client, quote, items = {}, {}, {}, []
    if inv.get("packing_slip_number"):
        row = db.execute(
            "SELECT * FROM Packing_Slip WHERE packing_slip_number=?",
            (inv["packing_slip_number"],),
        ).fetchone()
        if row:
            pl = dict(row)
    if inv.get("client_id"):
        row = db.execute(
            "SELECT * FROM Clients WHERE client_id=?", (inv["client_id"],)
        ).fetchone()
        if row:
            client = dict(row)
    if pl.get("quote_number"):
        qrow = db.execute(
            "SELECT * FROM Quote WHERE quote_number=?", (pl["quote_number"],)
        ).fetchone()
        if qrow:
            quote = dict(qrow)
    
    items = [
        dict(r)
        for r in db.execute(
            """
        SELECT psi.*, pn.description, pn.weight, pn.dimensions
        FROM Packing_Slip_Items psi 
        JOIN PartNumber pn ON psi.parts_number=pn.parts_number
        WHERE psi.packing_slip_number=?
    """,
            (inv.get("packing_slip_number", ""),),
        ).fetchall()
    ]
    close_db()
    pdf = pdf_service.build_invoice_pdf(inv, pl, client, items, quote)
    result = email_service.send_document_email(
        to_email, subject, body, pdf, f"{inv_number}.pdf"
    )

    db = get_db()
    db.execute(
        """INSERT INTO Email_Log (doc_type, doc_number, to_email, subject, status, error_message)
                  VALUES (?, ?, ?, ?, ?, ?)""",
        (
            "invoice",
            inv_number,
            to_email,
            subject,
            "sent" if result["ok"] else "failed",
            result.get("error"),
        ),
    )
    db.commit()
    close_db()

    return {"ok": result["ok"], "error": result.get("error")}
