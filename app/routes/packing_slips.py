from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
from app.database import get_db, next_doc_number
from app.services import pdf_service, email_service

router = APIRouter(prefix="/packing-slips", tags=["packing_slips"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def pl_list(request: Request):
    return templates.TemplateResponse("packing_slips/list.html", {"request": request})


@router.get("/new", response_class=HTMLResponse)
def pl_new(request: Request, from_quote: str = ""):
    return templates.TemplateResponse("packing_slips/form.html", {"request": request})


@router.post("/new")
async def pl_create(
    quote_number: str = Form(""),
    packing_slip_date: str = Form(...),
    po_number: str = Form(""),
    ship_via: str = Form(""),
    delivered_by: str = Form(""),
    ship_from: str = Form(""),
    ship_to: str = Form(""),
    client_id: str = Form(""),
):
    db = get_db()
    mmddyyyy = datetime.strptime(packing_slip_date, "%Y-%m-%d").strftime("%m%d%Y")
    plnum = next_doc_number(db, "PL", mmddyyyy)
    db.execute(
        """INSERT INTO Packing_Slip VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            plnum,
            quote_number or None,
            packing_slip_date,
            po_number or None,
            ship_via or None,
            delivered_by or None,
            ship_from or None,
            ship_to or None,
            client_id or None,
        ),
    )
    db.commit()
    db.close()
    return RedirectResponse(f"/packing-slips/{plnum}", status_code=303)


@router.get("/{pl_number}", response_class=HTMLResponse)
def pl_detail(request: Request, pl_number: str):
    return templates.TemplateResponse(
        "packing_slips/detail.html",
        {"request": request, "pl": {"packing_slip_number": pl_number}},
    )


@router.get("/{pl_number}/pdf")
def pl_pdf(pl_number: str):
    db = get_db()
    pl = dict(
        db.execute(
            "SELECT * FROM Packing_Slip WHERE packing_slip_number=?", (pl_number,)
        ).fetchone()
    )
    client = {}
    if pl.get("client_id"):
        row = db.execute(
            "SELECT * FROM Clients WHERE client_id=?", (pl["client_id"],)
        ).fetchone()
        if row:
            client = dict(row)
    quote = {}
    items = []
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
    pdf = pdf_service.build_packing_slip_pdf(pl, client, items, quote)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pl_number}.pdf"'},
    )


@router.post("/{pl_number}/send")
async def pl_send(
    pl_number: str,
    to_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
):
    db = get_db()
    pl = db.execute(
        "SELECT * FROM Packing_Slip WHERE packing_slip_number=?", (pl_number,)
    ).fetchone()
    if not pl:
        db.close()
        return {"ok": False, "error": f"Packing slip '{pl_number}' not found"}

    pl = dict(pl)
    client = {}
    if pl.get("client_id"):
        row = db.execute(
            "SELECT * FROM Clients WHERE client_id=?", (pl["client_id"],)
        ).fetchone()
        if row:
            client = dict(row)
    quote, items = {}, []
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
    pdf = pdf_service.build_packing_slip_pdf(pl, client, items, quote)
    result = email_service.send_document_email(
        to_email, subject, body, pdf, f"{pl_number}.pdf"
    )

    db = get_db()
    db.execute(
        """INSERT INTO Email_Log (doc_type, doc_number, to_email, subject, status, error_message)
                  VALUES (?, ?, ?, ?, ?, ?)""",
        (
            "packing_slip",
            pl_number,
            to_email,
            subject,
            "sent" if result["ok"] else "failed",
            result.get("error"),
        ),
    )
    db.commit()
    db.close()

    return {"ok": result["ok"], "error": result.get("error")}
