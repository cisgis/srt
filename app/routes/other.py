from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json, sqlite3
from app.database import get_db

# ── Clients ──────────────────────────────────────────────────
clients_router = APIRouter(prefix="/clients", tags=["clients"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@clients_router.get("/", response_class=HTMLResponse)
def clients_list(request: Request):
    db = get_db()
    clients = db.execute("SELECT * FROM Clients ORDER BY company, name").fetchall()
    db.close()
    return templates.TemplateResponse(
        "clients/list.html", {"request": request, "clients": clients}
    )


@clients_router.post("/new")
async def client_create(
    name: str = Form(...),
    department: str = Form(""),
    company: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    site_address: str = Form(""),
    billing_address: str = Form(""),
):
    db = get_db()
    db.execute(
        "INSERT INTO Clients (name, department, company, phone, email, site_address, billing_address) VALUES (?,?,?,?,?,?,?)",
        (
            name,
            department or None,
            company or None,
            phone or None,
            email or None,
            site_address or None,
            billing_address or None,
        ),
    )
    db.commit()
    db.close()
    return RedirectResponse("/clients/", status_code=303)


@clients_router.post("/{client_id}/edit")
async def client_edit(
    client_id: int,
    name: str = Form(...),
    department: str = Form(""),
    company: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    site_address: str = Form(""),
    billing_address: str = Form(""),
):
    db = get_db()
    db.execute(
        "UPDATE Clients SET name=?, department=?, company=?, phone=?, email=?, site_address=?, billing_address=? WHERE client_id=?",
        (
            name,
            department or None,
            company or None,
            phone or None,
            email or None,
            site_address or None,
            billing_address or None,
            client_id,
        ),
    )
    db.commit()
    db.close()
    return RedirectResponse("/clients/", status_code=303)


@clients_router.post("/{client_id}/delete")
async def client_delete(client_id: int):
    db = get_db()
    try:
        db.execute("DELETE FROM Clients WHERE client_id=?", (client_id,))
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return JSONResponse(
            status_code=409,
            content={
                "error": f"Cannot delete this client because they have associated quotes, packing slips, or invoices. Remove those records first."
            },
        )
    db.close()
    return RedirectResponse("/clients/", status_code=303)


# ── Vendors ──────────────────────────────────────────────────
vendors_router = APIRouter(prefix="/vendors", tags=["vendors"])


@vendors_router.get("/", response_class=HTMLResponse)
def vendors_list(request: Request):
    db = get_db()
    vendors = db.execute("""
        SELECT v.name, COUNT(pn.parts_number) as product_count
        FROM Vendor v LEFT JOIN PartNumber pn ON v.name=pn.vendor_name
        GROUP BY v.name ORDER BY v.name
    """).fetchall()
    db.close()
    return templates.TemplateResponse(
        "vendors/list.html", {"request": request, "vendors": vendors}
    )


@vendors_router.post("/new")
async def vendor_create(name: str = Form(...)):
    db = get_db()
    db.execute("INSERT INTO Vendor VALUES (?)", (name,))
    db.commit()
    db.close()
    return RedirectResponse("/vendors/", status_code=303)


@vendors_router.post("/{name}/edit")
async def vendor_edit(name: str, new_name: str = Form(...)):
    db = get_db()
    db.execute("UPDATE Vendor SET name=? WHERE name=?", (new_name, name))
    db.execute(
        "UPDATE PartNumber SET vendor_name=? WHERE vendor_name=?", (new_name, name)
    )
    db.commit()
    db.close()
    return RedirectResponse("/vendors/", status_code=303)


@vendors_router.post("/{name}/delete")
async def vendor_delete(name: str):
    db = get_db()
    try:
        db.execute("DELETE FROM Vendor WHERE name=?", (name,))
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return JSONResponse(
            status_code=409,
            content={
                "error": f"Cannot delete vendor '{name}' because they have products assigned. Reassign or remove those products first."
            },
        )
    db.close()
    return RedirectResponse("/vendors/", status_code=303)


# ── Locations ──────────────────────────────────────────────────
locations_router = APIRouter(prefix="/locations", tags=["locations"])


@locations_router.get("/", response_class=HTMLResponse)
def locations_list(request: Request):
    db = get_db()
    locations = db.execute("SELECT * FROM Location ORDER BY name").fetchall()
    db.close()
    return templates.TemplateResponse(
        "locations/list.html", {"request": request, "locations": locations}
    )


@locations_router.post("/new")
async def location_create(
    name: str = Form(...),
    address: str = Form(""),
    is_yard: str = Form(""),
):
    db = get_db()
    try:
        db.execute(
            "INSERT INTO Location VALUES (?,?,?)",
            (name, address or None, 1 if is_yard == "1" else 0),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return JSONResponse(
            status_code=409,
            content={"error": f"Location '{name}' already exists."},
        )
    db.close()
    return RedirectResponse("/locations/", status_code=303)


@locations_router.post("/{name}/delete")
async def location_delete(name: str):
    db = get_db()
    db.execute("DELETE FROM Location WHERE name=?", (name,))
    db.commit()
    db.close()
    return RedirectResponse("/locations/", status_code=303)


@locations_router.post("/{name}/edit")
async def location_edit(
    name: str,
    new_name: str = Form(...),
    address: str = Form(""),
    is_yard: str = Form(""),
):
    db = get_db()
    db.execute(
        "UPDATE Location SET name=?, address=?, is_yard=? WHERE name=?",
        (new_name, address or None, 1 if is_yard == "1" else 0, name),
    )
    db.commit()
    db.close()
    return RedirectResponse("/locations/", status_code=303)


# ── Customer Transactions ─────────────────────────────────────
txn_ext_router = APIRouter(prefix="/transactions/customer", tags=["transactions"])


@txn_ext_router.get("/", response_class=HTMLResponse)
def txn_ext_list(request: Request):
    db = get_db()
    txns = db.execute("""
        SELECT te.*, ps.packing_slip_number as pl_num, c.customer_name
        FROM Transaction_External te
        LEFT JOIN Packing_Slip ps ON te.packing_slip_id=ps.packing_slip_number
        LEFT JOIN Clients c ON ps.client_id=c.client_id
        ORDER BY te.outbound_date DESC
    """).fetchall()
    db.close()
    return templates.TemplateResponse(
        "transactions/customer_list.html", {"request": request, "txns": txns}
    )


@txn_ext_router.get("/new", response_class=HTMLResponse)
def txn_ext_new(request: Request):
    db = get_db()
    pls = db.execute(
        "SELECT ps.*, c.customer_name FROM Packing_Slip ps LEFT JOIN Clients c ON ps.client_id=c.client_id ORDER BY ps.packing_slip_date DESC"
    ).fetchall()
    products = db.execute(
        """SELECT p.serial_number, p.parts_number, pn.description, p.status 
           FROM Product p 
           JOIN PartNumber pn ON p.parts_number = pn.parts_number 
           ORDER BY p.serial_number"""
    ).fetchall()
    db.close()
    return templates.TemplateResponse(
        "transactions/customer_form.html",
        {
            "request": request,
            "pls": pls,
            "products": products,
        },
    )


@txn_ext_router.post("/new")
async def txn_ext_create(
    request: Request,
    packing_slip_id: str = Form(...),
    outbound_date: str = Form(""),
    inbound_date: str = Form(""),
    signature: str = Form(""),
    delivered_by: str = Form(""),
    discount: str = Form("0"),
):
    form = await request.form()
    parts_json_raw = form.get("parts_json", "[]")
    if hasattr(parts_json_raw, "filename"):
        parts_json = "[]"
    else:
        parts_json = str(parts_json_raw) if parts_json_raw else "[]"
    try:
        parts_list = json.loads(parts_json)
    except (json.JSONDecodeError, TypeError):
        parts_list = []

    db = get_db()
    cur = db.execute(
        """INSERT INTO Transaction_External
        (packing_slip_id, outbound_date, inbound_date, signature, delivered_by, discount)
        VALUES (?,?,?,?,?,?)""",
        (
            packing_slip_id,
            outbound_date or None,
            inbound_date or None,
            signature or None,
            delivered_by or None,
            float(discount or 0),
        ),
    )
    tid = cur.lastrowid
    for sn in parts_list:
        db.execute(
            "INSERT INTO Transaction_External_Items (transaction_ext_id, serial_number) VALUES (?,?)",
            (tid, sn),
        )
        db.execute("UPDATE Product SET status='On Loan' WHERE serial_number=?", (sn,))
    db.commit()
    db.close()
    return RedirectResponse("/transactions/customer/", status_code=303)


@txn_ext_router.post("/{txn_id}/return")
async def txn_ext_return(txn_id: int, inbound_date: str = Form(...)):
    db = get_db()
    db.execute(
        "UPDATE Transaction_External SET inbound_date=? WHERE transaction_ext_id=?",
        (inbound_date, txn_id),
    )
    parts = db.execute(
        "SELECT serial_number FROM Transaction_External_Items WHERE transaction_ext_id=?",
        (txn_id,),
    ).fetchall()
    for p in parts:
        db.execute(
            "UPDATE Product SET status='Available' WHERE serial_number=?",
            (p["serial_number"],),
        )
    db.commit()
    db.close()
    return RedirectResponse("/transactions/customer/", status_code=303)


# ── Internal Transactions ─────────────────────────────────────
txn_int_router = APIRouter(prefix="/transactions/internal", tags=["transactions"])


@txn_int_router.get("/", response_class=HTMLResponse)
def txn_int_list(request: Request):
    db = get_db()
    txns = db.execute(
        "SELECT * FROM Transaction_Internal ORDER BY move_date DESC"
    ).fetchall()
    db.close()
    return templates.TemplateResponse(
        "transactions/internal_list.html", {"request": request, "txns": txns}
    )


@txn_int_router.get("/new", response_class=HTMLResponse)
def txn_int_new(request: Request):
    db = get_db()
    products = db.execute(
        """SELECT p.serial_number, p.parts_number, pn.description, p.location, p.status 
           FROM Product p 
           JOIN PartNumber pn ON p.parts_number = pn.parts_number 
           ORDER BY p.serial_number"""
    ).fetchall()
    warehouses = db.execute("SELECT * FROM Warehouse").fetchall()
    db.close()
    return templates.TemplateResponse(
        "transactions/internal_form.html",
        {
            "request": request,
            "products": products,
            "warehouses": warehouses,
        },
    )


@txn_int_router.post("/new")
async def txn_int_create(
    request: Request,
    from_location: str = Form(""),
    to_location: str = Form(""),
    move_date: str = Form(""),
    receive_date: str = Form(""),
    moved_by: str = Form(""),
    reason: str = Form(""),
):
    form = await request.form()
    parts_json_raw = form.get("parts_json", "[]")
    if hasattr(parts_json_raw, "filename"):
        parts_json = "[]"
    else:
        parts_json = str(parts_json_raw) if parts_json_raw else "[]"
    try:
        parts_list = json.loads(parts_json)
    except (json.JSONDecodeError, TypeError):
        parts_list = []

    db = get_db()
    cur = db.execute(
        """INSERT INTO Transaction_Internal
        (from_location, to_location, move_date, receive_date, moved_by, reason)
        VALUES (?,?,?,?,?,?)""",
        (
            from_location or None,
            to_location or None,
            move_date or None,
            receive_date or None,
            moved_by or None,
            reason or None,
        ),
    )
    tid = cur.lastrowid
    for sn in parts_list:
        db.execute(
            "INSERT INTO Transaction_Internal_Items (transaction_int_id, serial_number) VALUES (?,?)",
            (tid, sn),
        )
        db.execute(
            "UPDATE Product SET location=? WHERE serial_number=?", (to_location, sn)
        )
    db.commit()
    db.close()
    return RedirectResponse("/transactions/internal/", status_code=303)
