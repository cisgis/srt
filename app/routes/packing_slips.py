from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import datetime
import json
import sqlite3
from app.database import get_db, get_write_lock, next_doc_number, close_db
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
    close_db()

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

            query = "SELECT serial_number, location, status FROM Product WHERE parts_number=? AND status IN ('In Stock', 'Inbound in Transit')"
            params = [parts_number]
            if yard:
                query += " AND location=?"
                params.append(yard)
            query += " ORDER BY serial_number"

            prods = db.execute(query, params).fetchall()
            available_products[parts_number] = [dict(p) for p in prods]

    today = datetime.now().strftime("%Y-%m-%d")
    close_db()

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
                db.execute(
                    "UPDATE Product SET status='Processing / Fulfillment', modified_by=?, modified_at=? WHERE serial_number=?",
                    (user, now, snum),
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

    locations = db.execute(
        "SELECT name FROM Location WHERE is_yard=1 ORDER BY name"
    ).fetchall()
    yards_list = [l["name"] for l in locations]
    locations_list = [{"name": l["name"]} for l in locations]

    quote_items = []
    available_products = {}
    for item in pl_items:
        parts_number = item["parts_number"]
        current_sn = item["serial_number"]
        
        prods = db.execute(
            """SELECT p.serial_number, p.location, p.status FROM Product p
            LEFT JOIN Packing_Slip_Items pli ON p.serial_number = pli.serial_number AND pli.packing_slip_number = ?
            WHERE p.parts_number=? AND (p.status = 'In Stock' OR pli.packing_slip_number = ?)
            ORDER BY p.location, p.serial_number""",
            (pl_number, parts_number, pl_number),
        ).fetchall()
        
        products_by_status = {}
        for p in prods:
            pd = dict(p)
            prod_status = pd.get("status", "")
            if prod_status not in products_by_status:
                products_by_status[prod_status] = []
            products_by_status[prod_status].append(pd)
        available_products[parts_number] = products_by_status
        
        current_loc = db.execute(
            "SELECT location FROM Product WHERE serial_number=?", (current_sn,)
        ).fetchone()
        current_yard = current_loc["location"] if current_loc else ""
        
        quote_items.append(
            {
                "parts_number": parts_number,
                "quantity": 1,
                "yard": current_yard,
            }
        )

    today = datetime.now().strftime("%Y-%m-%d")
    close_db()

    return templates.TemplateResponse(
        "packing_slips/edit.html",
        {
            "request": request,
            "pl": pl,
            "pl_items": pl_items,
            "quote_items": quote_items,
            "available_products": available_products,
            "locations": locations_list,
            "yards": yards_list,
            "today": today,
            "is_edit": False,
            "success": "",
        },
    )

@router.get("/{pl_number}/edit", response_class=HTMLResponse)
def pl_edit(request: Request, pl_number: str, success: str = ""):
    db = get_db()
    pl = dict(
        db.execute(
            "SELECT * FROM Packing_Slip WHERE packing_slip_number=?", (pl_number,)
        ).fetchone()
    )
    pl_items = db.execute(
        "SELECT * FROM Packing_Slip_Items WHERE packing_slip_number=?", (pl_number,)
    ).fetchall()

    locations = db.execute(
        "SELECT name FROM Location WHERE is_yard=1 ORDER BY name"
    ).fetchall()
    yards_list = [l["name"] for l in locations]
    locations_list = [{"name": l["name"]} for l in locations]

    quote_items = []
    available_products = {}
    for item in pl_items:
        parts_number = item["parts_number"]
        current_sn = item["serial_number"]
        
        prods = db.execute(
            """SELECT p.serial_number, p.location, p.status FROM Product p
            LEFT JOIN Packing_Slip_Items pli ON p.serial_number = pli.serial_number AND pli.packing_slip_number = ?
            WHERE p.parts_number=? AND (p.status = 'In Stock' OR pli.packing_slip_number = ?)
            ORDER BY p.location, p.serial_number""",
            (pl_number, parts_number, pl_number),
        ).fetchall()
        
        products_by_status = {}
        for p in prods:
            pd = dict(p)
            prod_status = pd.get("status", "")
            if prod_status not in products_by_status:
                products_by_status[prod_status] = []
            products_by_status[prod_status].append(pd)
        available_products[parts_number] = products_by_status
        
        current_loc = db.execute(
            "SELECT location FROM Product WHERE serial_number=?", (current_sn,)
        ).fetchone()
        current_yard = current_loc["location"] if current_loc else ""
        
        quote_items.append(
            {
                "parts_number": parts_number,
                "quantity": 1,
                "yard": current_yard,
            }
        )

    today = datetime.now().strftime("%Y-%m-%d")
    close_db()

    return templates.TemplateResponse(
        "packing_slips/edit.html",
        {
            "request": request,
            "pl": pl,
            "pl_items": pl_items,
            "quote_items": quote_items,
            "available_products": available_products,
            "locations": locations_list,
            "yards": yards_list,
            "today": today,
            "is_edit": True,
            "success": success,
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

    current_sns = [dict(r)["serial_number"] for r in db.execute(
        "SELECT serial_number FROM Packing_Slip_Items WHERE packing_slip_number=?", (pl_number,)
    ).fetchall()]

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
                db.execute(
                    "UPDATE Product SET status='Processing / Fulfillment', modified_by=?, modified_at=? WHERE serial_number=?",
                    (user, now, snum),
                )

    for old_sn in current_sns:
        still_selected = False
        if items:
            for item in items:
                if old_sn in item.get("serial_numbers", []):
                    still_selected = True
                    break
        if not still_selected:
            db.execute(
                "UPDATE Product SET status='In Stock', modified_by=?, modified_at=? WHERE serial_number=?",
                (user, now, old_sn),
            )

    db.commit()
    log_info(f"Updated PL: {pl_number} by {user}")
    close_db()

    return RedirectResponse(f"/packing-slips/{pl_number}/edit?success=1", status_code=303)


@router.get("/{pl_number}/mark-shipped")
def pl_mark_shipped(request: Request, pl_number: str):
    db = get_db()
    pl = db.execute("SELECT * FROM Packing_Slip WHERE packing_slip_number=?", (pl_number,)).fetchone()
    if not pl:
        close_db()
        return HTMLResponse("Packing slip not found", status_code=404)
    
    pl = dict(pl)
    
    if pl.get("status") == "SHIPPED":
        close_db()
        return RedirectResponse(f"/packing-slips/{pl_number}/edit", status_code=303)
    
    db.execute(
        "UPDATE Packing_Slip SET status=?, modified_at=? WHERE packing_slip_number=?",
        ("SHIPPED", datetime.now().isoformat(), pl_number),
    )
    
    items = db.execute(
        "SELECT serial_number FROM Packing_Slip_Items WHERE packing_slip_number=?", (pl_number,)
    ).fetchall()
    user = request.session.get("username", "unknown")
    now = datetime.now().isoformat()
    for item in items:
        db.execute(
            "UPDATE Product SET status='On Rent', modified_by=?, modified_at=? WHERE serial_number=?",
            (user, now, item["serial_number"]),
        )
    
    db.commit()
    close_db()
    
    return RedirectResponse(f"/packing-slips/{pl_number}/edit", status_code=303)


@router.get("/{pl_number}/create-invoice")
def pl_create_invoice(request: Request, pl_number: str):
    db = get_db()
    pl = db.execute("SELECT * FROM Packing_Slip WHERE packing_slip_number=?", (pl_number,)).fetchone()
    if not pl:
        close_db()
        return HTMLResponse("Packing slip not found", status_code=404)
    
    pl = dict(pl)
    
    po_number = ""
    if pl.get("po_number"):
        po_number = str(pl["po_number"]).strip()
    else:
        po_number = ""
    
    items = db.execute(
        "SELECT * FROM Packing_Slip_Items WHERE packing_slip_number=?", (pl_number,)
    ).fetchall()
    close_db()

    items_json = json.dumps([
        {
            "parts_number": i["parts_number"],
            "quantity": 1,
            "serial_number": i["serial_number"],
        }
        for i in items
    ])

    return RedirectResponse(
        f"/invoices/new?pl_number={pl_number}&client_id={pl.get('client_id', '')}&ship_to={pl.get('ship_to', '')}&items_json={items_json}&po_number={po_number}",
        status_code=303,
    )


_pdf_browser = None
_pdf_lock = None


def _get_pdf_lock():
    global _pdf_lock
    if _pdf_lock is None:
        import threading
        _pdf_lock = threading.Lock()
    return _pdf_lock


async def _get_pdf_browser():
    global _pdf_browser
    from playwright.async_api import async_playwright

    if _pdf_browser is None:
        p = await async_playwright().start()
        _pdf_browser = await p.chromium.launch(headless=True)
    elif not _pdf_browser.is_connected():
        p = await async_playwright().start()
        _pdf_browser = await p.chromium.launch(headless=True)
    return _pdf_browser


@router.get("/{pl_number}/pdf")
def pl_pdf(pl_number: str):
    try:
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
        
        pl_items = [
            dict(r)
            for r in db.execute(
                """SELECT pli.*, pn.description
                FROM Packing_Slip_Items pli 
                JOIN PartNumber pn ON pli.parts_number=pn.parts_number
                WHERE pli.packing_slip_number=?""",
                (pl_number,),
            ).fetchall()
        ]
        
        location = db.execute("SELECT * FROM Location WHERE name=?", (pl.get("ship_from"),)).fetchone()
        ship_from_addr = location["address"] if location else pl.get("ship_from") or ""
        
        close_db()
        
        from fastapi.templating import Jinja2Templates
        templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
        
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
                elif logo_path.suffix.lower() in [".jpg", ".jpeg"]:
                    logo_b64 = f"data:image/jpeg;base64,{logo_b64}"
        
        context = {
            "pl": pl,
            "client": client,
            "items": pl_items,
            "ship_from": ship_from_addr,
            "logo_data": logo_b64,
        }
        html_content = templates.get_template("packing_slips/pdf.html").render(context)
        
        import asyncio
        
        async def generate_pdf():
            browser = await _get_pdf_browser()
            if browser is None:
                raise Exception("Failed to get PDF browser")
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
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{pl_number}.pdf"'
            },
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return HTMLResponse(f"Error generating PDF: {e}", status_code=500)
