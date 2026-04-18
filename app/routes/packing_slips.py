from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import json
import sqlite3
from app.database import get_db, get_write_lock, next_doc_number
from app.services import pdf_service, email_service
from app.logger import log_info, log_error

router = APIRouter(prefix="/packing-slips", tags=["packing_slips"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def pl_list(request: Request):
    db = get_db()
    pl_list = db.execute(
        "SELECT * FROM Packing_Slip ORDER BY created_at DESC"
    ).fetchall()

    return templates.TemplateResponse(
        "packing_slips/list.html", {"request": request, "packing_slips": pl_list}
    )


@router.get("/new", response_class=HTMLResponse)
def pl_new(
    request: Request,
    quote_number: str = "",
    client_id: str = "",
    ship_to: str = "",
    items_json: str = "[]",
):
    db = get_db()

    locations = db.execute(
        "SELECT name FROM Location WHERE is_yard=1 ORDER BY name"
    ).fetchall()
    locations_list = [{"name": l["name"]} for l in locations]

    quote_items = []
    available_products = {}

    try:
        items = json.loads(items_json)
    except (json.JSONDecodeError, TypeError):
        items = []

    if items:
        for it in items:
            parts_number = it.get("parts_number")
            yard = it.get("yard", "")

            quote_items.append(
                {
                    "parts_number": parts_number,
                    "quantity": it.get("quantity", 0),
                    "yard": yard,
                }
            )

            query = "SELECT serial_number, location, status FROM Product WHERE parts_number=? AND status='Available'"
            params = [parts_number]
            if yard:
                query += " AND location=?"
                params.append(yard)
            query += " ORDER BY serial_number"

            prods = db.execute(query, params).fetchall()
            available_products[parts_number] = [dict(p) for p in prods]

    today = datetime.now().strftime("%Y-%m-%d")

    return templates.TemplateResponse(
        "packing_slips/form.html",
        {
            "request": request,
            "quote_number": quote_number,
            "client_id": client_id,
            "ship_to": ship_to,
            "items_json": items_json,
            "locations": locations_list,
            "quote_items": quote_items,
            "available_products": available_products,
            "today": today,
        },
    )


@router.post("/new")
async def pl_create(
    request: Request,
    quote_number: str = Form(""),
    packing_slip_date: str = Form(...),
    po_number: str = Form(""),
    ship_via: str = Form(""),
    tracking_number: str = Form(""),
    ship_from: str = Form(""),
    ship_to: str = Form(""),
    client_id: str = Form(""),
    items_json: str = Form("[]"),
):
    try:
        now = datetime.now().isoformat()
        user = request.session.get("username", "unknown")

        lock = get_write_lock()
        with lock:
            db = get_db()
            mmddyyyy = datetime.strptime(packing_slip_date, "%Y-%m-%d").strftime(
                "%m%d%Y"
            )
            plnum = next_doc_number(db, "PL", mmddyyyy)
            print(f"PL: {plnum}")

        try:
            items = json.loads(items_json)
        except:
            items = []

        cli_id = None
        if client_id and client_id.isdigit():
            cli_id = int(client_id)

        try:
            db.execute(
                """INSERT INTO Packing_Slip 
                   (packing_slip_number, quote_number, packing_slip_date, po_number, ship_via, delivered_by, ship_from, ship_to, client_id, created_by, created_at, modified_by, modified_at, tracking_number)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    plnum,
                    quote_number or None,
                    packing_slip_date,
                    po_number or None,
                    ship_via or None,
                    None,
                    ship_from or None,
                    ship_to or None,
                    cli_id,
                    user,
                    now,
                    user,
                    now,
                    tracking_number or None,
                ),
            )
        except sqlite3.IntegrityError:
            db.rollback()
            existing = db.execute(
                "SELECT packing_slip_number FROM Packing_Slip WHERE packing_slip_number = ?",
                (plnum,),
            ).fetchone()
            if existing:
                return HTMLResponse(
                    f"Error: Packing slip {plnum} already exists. Please try again.",
                    status_code=500,
                )
            raise

        for item in items:
            sn_list = item.get("serial_numbers", [])
            parts = item.get("parts_number")
            for snum in sn_list:
                db.execute(
                    "INSERT INTO Packing_Slip_Items (packing_slip_number, parts_number, serial_number) VALUES (?,?,?)",
                    (plnum, parts, snum),
                )

        db.commit()
        log_info(f"Created PL: {plnum}")
        return RedirectResponse(f"/packing-slips/{plnum}", status_code=303)
    except Exception as e:
        import traceback

        print(f"Error: {e}\n{traceback.format_exc()}")
        try:
            db.rollback()
        except:
            pass
        return HTMLResponse(f"Error: {e}", status_code=500)


@router.get("/{pl_number}", response_class=HTMLResponse)
def pl_detail(request: Request, pl_number: str):
    db = get_db()
    pl = dict(
        db.execute(
            "SELECT * FROM Packing_Slip WHERE packing_slip_number=?", (pl_number,)
        ).fetchone()
    )
    pl_items = db.execute(
        "SELECT * FROM Packing_Slip_Items WHERE packing_slip_number=?", (pl_number,)
    ).fetchall()

    return templates.TemplateResponse(
        "packing_slips/edit.html",
        {"request": request, "pl": pl, "pl_items": pl_items, "is_edit": False},
    )


@router.get("/{pl_number}/edit", response_class=HTMLResponse)
def pl_edit(request: Request, pl_number: str):
    db = get_db()
    pl = dict(
        db.execute(
            "SELECT * FROM Packing_Slip WHERE packing_slip_number=?", (pl_number,)
        ).fetchone()
    )
    pl_items = db.execute(
        "SELECT * FROM Packing_Slip_Items WHERE packing_slip_number=?", (pl_number,)
    ).fetchall()

    quote_items = []
    available_products = {}
    for item in pl_items:
        parts_number = item["parts_number"]
        quote_items.append(
            {
                "parts_number": parts_number,
                "quantity": 1,
                "yard": "",
            }
        )
        prods = db.execute(
            "SELECT serial_number, location, status FROM Product WHERE parts_number=? AND (status='Available' OR serial_number=?) ORDER BY serial_number",
            (parts_number, item["serial_number"]),
        ).fetchall()
        available_products[parts_number] = [dict(p) for p in prods]

    locations = db.execute(
        "SELECT name FROM Location WHERE is_yard=1 ORDER BY name"
    ).fetchall()
    locations_list = [{"name": l["name"]} for l in locations]
    today = datetime.now().strftime("%Y-%m-%d")

    return templates.TemplateResponse(
        "packing_slips/edit.html",
        {
            "request": request,
            "pl": pl,
            "pl_items": pl_items,
            "quote_items": quote_items,
            "available_products": available_products,
            "locations": locations_list,
            "today": today,
            "is_edit": True,
        },
    )


@router.post("/{pl_number}/edit")
async def pl_update(
    request: Request,
    pl_number: str,
    packing_slip_date: str = Form(...),
    po_number: str = Form(""),
    ship_via: str = Form(""),
    tracking_number: str = Form(""),
    ship_from: str = Form(""),
    ship_to: str = Form(""),
    items_json: str = Form("[]"),
):
    user = request.session.get("username", "unknown")
    now = datetime.now().isoformat()
    db = get_db()
    db.execute(
        """UPDATE Packing_Slip SET
           packing_slip_date=?, po_number=?, ship_via=?, ship_from=?, ship_to=?,
           modified_by=?, modified_at=?, tracking_number=?
           WHERE packing_slip_number=?""",
        (
            packing_slip_date,
            po_number or None,
            ship_via or None,
            ship_from or None,
            ship_to or None,
            user,
            now,
            tracking_number or None,
            pl_number,
        ),
    )

    try:
        items = json.loads(items_json)
    except:
        items = []

    if items:
        db.execute(
            "DELETE FROM Packing_Slip_Items WHERE packing_slip_number=?", (pl_number,)
        )
        for item in items:
            parts_number = item.get("parts_number")
            for snum in item.get("serial_numbers", []):
                db.execute(
                    "INSERT INTO Packing_Slip_Items (packing_slip_number, parts_number, serial_number) VALUES (?,?,?)",
                    (pl_number, parts_number, snum),
                )

    db.commit()

    return RedirectResponse(f"/packing-slips/{pl_number}", status_code=303)


@router.get("/{pl_number}/pdf")
def pl_pdf(pl_number: str):
    db = get_db()
    pl = dict(
        db.execute(
            "SELECT * FROM Packing_Slip WHERE packing_slip_number=?", (pl_number,)
        ).fetchone()
    )

    return Response(b"PDF not implemented yet", media_type="application/pdf")
