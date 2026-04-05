from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
from app.database import get_db, next_doc_number
from app.services import pdf_service, email_service

router = APIRouter(prefix="/invoices", tags=["invoices"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
PAYMENT_TERMS = ["COD", "Net 7", "Net 14", "Net 21", "Net 30", "Net 60"]


@router.get("/", response_class=HTMLResponse)
def inv_list(request: Request):
    db = get_db()
    invs = db.execute("""
        SELECT i.*, c.customer_name, ps.packing_slip_number as pl_num
        FROM Invoice i
        LEFT JOIN Clients c ON i.client_id=c.client_id
        LEFT JOIN Packing_Slip ps ON i.packing_slip_number=ps.packing_slip_number
        ORDER BY i.invoice_date DESC
    """).fetchall()
    db.close()
    return templates.TemplateResponse(
        "invoices/list.html", {"request": request, "invs": invs}
    )


@router.get("/new", response_class=HTMLResponse)
def inv_new(request: Request, from_pl: str = ""):
    db = get_db()
    pls = db.execute("""
        SELECT ps.*, c.customer_name FROM Packing_Slip ps
        LEFT JOIN Clients c ON ps.client_id=c.client_id
        ORDER BY ps.packing_slip_date DESC
    """).fetchall()
    prefill_pl = prefill_client = prefill_quote = None
    if from_pl:
        prefill_pl = db.execute(
            "SELECT * FROM Packing_Slip WHERE packing_slip_number=?", (from_pl,)
        ).fetchone()
        if prefill_pl and prefill_pl["client_id"]:
            prefill_client = db.execute(
                "SELECT * FROM Clients WHERE client_id=?", (prefill_pl["client_id"],)
            ).fetchone()
        if prefill_pl and prefill_pl["quote_number"]:
            prefill_quote = db.execute(
                "SELECT * FROM Quote WHERE quote_number=?",
                (prefill_pl["quote_number"],),
            ).fetchone()
    db.close()
    today = datetime.today().strftime("%Y-%m-%d")
    return templates.TemplateResponse(
        "invoices/form.html",
        {
            "request": request,
            "pls": pls,
            "payment_terms": PAYMENT_TERMS,
            "today": today,
            "prefill_pl": prefill_pl,
            "prefill_client": prefill_client,
            "prefill_quote": prefill_quote,
        },
    )


@router.post("/new")
async def inv_create(
    packing_slip_number: str = Form(...),
    purchase_number: str = Form(""),
    payment_term: str = Form(""),
    invoice_date: str = Form(...),
    client_id: str = Form(""),
):
    db = get_db()
    mmddyyyy = datetime.strptime(invoice_date, "%Y-%m-%d").strftime("%m%d%Y")
    invnum = next_doc_number(db, "INV", mmddyyyy)
    db.execute(
        "INSERT INTO Invoice VALUES (?,?,?,?,?,?)",
        (
            invnum,
            packing_slip_number,
            purchase_number or None,
            payment_term or None,
            invoice_date,
            client_id or None,
        ),
    )
    db.commit()
    db.close()
    return RedirectResponse(f"/invoices/{invnum}", status_code=303)


@router.get("/{inv_number}", response_class=HTMLResponse)
def inv_detail(request: Request, inv_number: str):
    db = get_db()
    inv = db.execute(
        "SELECT * FROM Invoice WHERE invoice_number=?", (inv_number,)
    ).fetchone()
    pl = (
        db.execute(
            "SELECT * FROM Packing_Slip WHERE packing_slip_number=?",
            (inv["packing_slip_number"],),
        ).fetchone()
        if inv and inv["packing_slip_number"]
        else None
    )
    client = (
        db.execute(
            "SELECT * FROM Clients WHERE client_id=?", (inv["client_id"],)
        ).fetchone()
        if inv and inv["client_id"]
        else None
    )
    quote = None
    items = []
    if pl and pl["quote_number"]:
        quote = db.execute(
            "SELECT * FROM Quote WHERE quote_number=?", (pl["quote_number"],)
        ).fetchone()
        items = db.execute(
            """
            SELECT qi.*, p.product_service_description, p.weight, p.dimensions
            FROM Quote_Items qi JOIN Product p ON qi.parts_number=p.parts_number
            WHERE qi.quote_number=?
        """,
            (pl["quote_number"],),
        ).fetchall()
    db.close()
    return templates.TemplateResponse(
        "invoices/detail.html",
        {
            "request": request,
            "inv": inv,
            "pl": pl,
            "client": client,
            "quote": quote,
            "items": items,
            "payment_terms": PAYMENT_TERMS,
        },
    )


@router.post("/{inv_number}/update-po")
async def inv_update_po(inv_number: str, purchase_number: str = Form(...)):
    db = get_db()
    db.execute(
        "UPDATE Invoice SET purchase_number=? WHERE invoice_number=?",
        (purchase_number, inv_number),
    )
    db.commit()
    db.close()
    return RedirectResponse(f"/invoices/{inv_number}", status_code=303)


@router.get("/{inv_number}/pdf")
def inv_pdf(inv_number: str):
    db = get_db()
    inv = dict(
        db.execute(
            "SELECT * FROM Invoice WHERE invoice_number=?", (inv_number,)
        ).fetchone()
    )
    pl = {}
    if inv.get("packing_slip_number"):
        row = db.execute(
            "SELECT * FROM Packing_Slip WHERE packing_slip_number=?",
            (inv["packing_slip_number"],),
        ).fetchone()
        if row:
            pl = dict(row)
    client, quote, items = {}, {}, []
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
                SELECT qi.*, p.product_service_description, p.weight, p.dimensions
                FROM Quote_Items qi JOIN Product p ON qi.parts_number=p.parts_number
                WHERE qi.quote_number=?
            """,
                    (pl["quote_number"],),
                ).fetchall()
            ]
    db.close()
    pdf = pdf_service.build_invoice_pdf(inv, pl, client, items, quote)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{inv_number}.pdf"'},
    )


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
        db.close()
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
                SELECT qi.*, p.product_service_description, p.weight, p.dimensions
                FROM Quote_Items qi JOIN Product p ON qi.parts_number=p.parts_number
                WHERE qi.quote_number=?
            """,
                    (pl["quote_number"],),
                ).fetchall()
            ]
    db.close()
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
    db.close()

    return {"ok": result["ok"], "error": result.get("error")}
