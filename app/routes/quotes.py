from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path
import sys, json
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from app.database import get_db, next_doc_number
from app.services import pdf_service, email_service

router = APIRouter(prefix="/quotes", tags=["quotes"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

PAYMENT_TERMS = ["COD","Net 7","Net 14","Net 21","Net 30","Net 60"]

@router.get("/", response_class=HTMLResponse)
def quotes_list(request: Request):
    db = get_db()
    quotes = db.execute("""
        SELECT q.*, c.customer_name FROM Quote q
        LEFT JOIN Clients c ON q.client_id=c.client_id
        ORDER BY q.quote_date DESC
    """).fetchall()
    db.close()
    return templates.TemplateResponse("quotes/list.html", {"request": request, "quotes": quotes})

@router.get("/new", response_class=HTMLResponse)
def quote_new(request: Request):
    db = get_db()
    clients  = db.execute("SELECT * FROM Clients ORDER BY customer_name").fetchall()
    products = db.execute("SELECT parts_number, product_service_description, resale_price, list_price FROM Product ORDER BY parts_number").fetchall()
    warehouses = db.execute("SELECT * FROM Warehouse").fetchall()
    db.close()
    today = datetime.today().strftime("%Y-%m-%d")
    return templates.TemplateResponse("quotes/form.html", {
        "request": request, "quote": None,
        "clients": clients, "products": products,
        "warehouses": warehouses, "payment_terms": PAYMENT_TERMS,
        "today": today,
    })

@router.post("/new")
async def quote_create(
    request: Request,
    quote_date: str = Form(...),
    quote_expiration_date: str = Form(""),
    payment_term: str = Form(""),
    ship_to: str = Form(""), ship_from: str = Form(""),
    sales_tax_rate: str = Form("0"),
    client_id: str = Form(""),
):
    db = get_db()
    mmddyyyy = datetime.strptime(quote_date, "%Y-%m-%d").strftime("%m%d%Y")
    qnum = next_doc_number(db, "Q", mmddyyyy)

    db.execute("""INSERT INTO Quote VALUES (?,?,?,?,?,?,?,?)""", (
        qnum, quote_date, quote_expiration_date or None,
        payment_term or None, ship_to or None, ship_from or None,
        float(sales_tax_rate or 0) / 100, client_id or None,
    ))
    db.commit()

    # FIX (Bug 4): Wrap json.loads in try/except. If the JS didn't populate
    # items_json (e.g. the form was submitted without any line items being
    # added, or a JS error occurred), we now fall back to an empty list
    # instead of crashing with an unhandled 500.
    form = await request.form()
    items_json = form.get("items_json", "[]")
    try:
        items = json.loads(items_json)
    except (json.JSONDecodeError, TypeError):
        items = []

    for it in items:
        # FIX (Bug 5): float(it["quoted_price"]) crashed when quoted_price
        # was an empty string or None. Now defaults to 0.0 safely.
        try:
            price = float(it.get("quoted_price") or 0)
        except (ValueError, TypeError):
            price = 0.0
        try:
            qty = int(it.get("quantity") or 1)
        except (ValueError, TypeError):
            qty = 1
        db.execute("""INSERT INTO Quote_Items (quote_number,parts_number,quantity,quoted_price,lead_time)
                      VALUES (?,?,?,?,?)""",
            (qnum, it["parts_number"], qty, price, it.get("lead_time", "")))
    db.commit(); db.close()
    return RedirectResponse(f"/quotes/{qnum}", status_code=303)

@router.get("/{quote_number}", response_class=HTMLResponse)
def quote_detail(request: Request, quote_number: str):
    db = get_db()
    quote = db.execute("SELECT * FROM Quote WHERE quote_number=?", (quote_number,)).fetchone()
    client = db.execute("SELECT * FROM Clients WHERE client_id=?", (quote["client_id"],)).fetchone() if quote["client_id"] else None
    items = db.execute("""
        SELECT qi.*, p.product_service_description
        FROM Quote_Items qi JOIN Product p ON qi.parts_number=p.parts_number
        WHERE qi.quote_number=?
    """, (quote_number,)).fetchall()
    clients  = db.execute("SELECT * FROM Clients ORDER BY customer_name").fetchall()
    products = db.execute("SELECT parts_number, product_service_description, resale_price, list_price FROM Product ORDER BY parts_number").fetchall()
    warehouses = db.execute("SELECT * FROM Warehouse").fetchall()
    db.close()
    return templates.TemplateResponse("quotes/detail.html", {
        "request": request, "quote": quote, "client": client,
        "items": items, "clients": clients, "products": products,
        "warehouses": warehouses, "payment_terms": PAYMENT_TERMS,
    })

@router.get("/{quote_number}/pdf")
def quote_pdf(quote_number: str):
    db = get_db()
    quote  = dict(db.execute("SELECT * FROM Quote WHERE quote_number=?", (quote_number,)).fetchone())
    client = {}
    if quote.get("client_id"):
        row = db.execute("SELECT * FROM Clients WHERE client_id=?", (quote["client_id"],)).fetchone()
        if row: client = dict(row)
    items = [dict(r) for r in db.execute("""
        SELECT qi.*, p.product_service_description
        FROM Quote_Items qi JOIN Product p ON qi.parts_number=p.parts_number
        WHERE qi.quote_number=?
    """, (quote_number,)).fetchall()]
    db.close()
    pdf = pdf_service.build_quote_pdf(quote, client, items)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{quote_number}.pdf"'})

@router.post("/{quote_number}/send")
async def quote_send(
    quote_number: str,
    to_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
):
    db = get_db()
    quote  = dict(db.execute("SELECT * FROM Quote WHERE quote_number=?", (quote_number,)).fetchone())
    client = {}
    if quote.get("client_id"):
        row = db.execute("SELECT * FROM Clients WHERE client_id=?", (quote["client_id"],)).fetchone()
        if row: client = dict(row)
    items = [dict(r) for r in db.execute("""
        SELECT qi.*, p.product_service_description
        FROM Quote_Items qi JOIN Product p ON qi.parts_number=p.parts_number
        WHERE qi.quote_number=?
    """, (quote_number,)).fetchall()]
    db.close()
    pdf = pdf_service.build_quote_pdf(quote, client, items)
    result = email_service.send_document_email(to_email, subject, body, pdf, f"{quote_number}.pdf")
    return {"ok": result["ok"], "error": result.get("error")}