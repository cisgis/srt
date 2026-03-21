from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import sys, json, sqlite3
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from app.database import get_db

# ── Clients ──────────────────────────────────────────────────
clients_router = APIRouter(prefix="/clients", tags=["clients"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

@clients_router.get("/", response_class=HTMLResponse)
def clients_list(request: Request):
    db = get_db()
    clients = db.execute("SELECT * FROM Clients ORDER BY customer_name").fetchall()
    db.close()
    return templates.TemplateResponse("clients/list.html", {"request": request, "clients": clients})

@clients_router.post("/new")
async def client_create(
    client_id: str = Form(...), customer_name: str = Form(...),
    well_name: str = Form(""), well_address: str = Form(""),
    billing_address: str = Form(""),
):
    db = get_db()
    db.execute("INSERT INTO Clients VALUES (?,?,?,?,?)",
               (client_id, customer_name, well_name or None, well_address or None, billing_address or None))
    db.commit(); db.close()
    return RedirectResponse("/clients/", status_code=303)

@clients_router.post("/{client_id}/edit")
async def client_edit(
    client_id: str,
    customer_name: str = Form(...), well_name: str = Form(""),
    well_address: str = Form(""), billing_address: str = Form(""),
):
    db = get_db()
    db.execute("UPDATE Clients SET customer_name=?, well_name=?, well_address=?, billing_address=? WHERE client_id=?",
               (customer_name, well_name or None, well_address or None, billing_address or None, client_id))
    db.commit(); db.close()
    return RedirectResponse("/clients/", status_code=303)

@clients_router.post("/{client_id}/delete")
async def client_delete(client_id: str):
    # FIX (Bug 6): Previously this crashed with a raw 500 when the client had
    # associated quotes, packing slips, or invoices (FK constraint violation).
    # Now returns a 409 with a human-readable error message instead.
    db = get_db()
    try:
        db.execute("DELETE FROM Clients WHERE client_id=?", (client_id,))
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return JSONResponse(
            status_code=409,
            content={"error": f"Cannot delete client '{client_id}' because they have associated quotes, packing slips, or invoices. Remove those records first."}
        )
    db.close()
    return RedirectResponse("/clients/", status_code=303)


# ── Vendors ──────────────────────────────────────────────────
vendors_router = APIRouter(prefix="/vendors", tags=["vendors"])

@vendors_router.get("/", response_class=HTMLResponse)
def vendors_list(request: Request):
    db = get_db()
    vendors = db.execute("""
        SELECT v.*, COUNT(p.parts_number) as product_count
        FROM Vendor v LEFT JOIN Product p ON v.vendor_id=p.vendor_id
        GROUP BY v.vendor_id ORDER BY v.vendor_name
    """).fetchall()
    db.close()
    return templates.TemplateResponse("vendors/list.html", {"request": request, "vendors": vendors})

@vendors_router.post("/new")
async def vendor_create(vendor_id: str = Form(...), vendor_name: str = Form(...)):
    db = get_db()
    db.execute("INSERT INTO Vendor VALUES (?,?)", (vendor_id, vendor_name))
    db.commit(); db.close()
    return RedirectResponse("/vendors/", status_code=303)

@vendors_router.post("/{vendor_id}/edit")
async def vendor_edit(vendor_id: str, vendor_name: str = Form(...)):
    db = get_db()
    db.execute("UPDATE Vendor SET vendor_name=? WHERE vendor_id=?", (vendor_name, vendor_id))
    db.commit(); db.close()
    return RedirectResponse("/vendors/", status_code=303)

@vendors_router.post("/{vendor_id}/delete")
async def vendor_delete(vendor_id: str):
    # FIX (Bug 6): Same FK crash fix as client_delete above.
    # A vendor with products assigned cannot be deleted without first
    # reassigning or removing those products.
    db = get_db()
    try:
        db.execute("DELETE FROM Vendor WHERE vendor_id=?", (vendor_id,))
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return JSONResponse(
            status_code=409,
            content={"error": f"Cannot delete vendor '{vendor_id}' because they have products assigned. Reassign or remove those products first."}
        )
    db.close()
    return RedirectResponse("/vendors/", status_code=303)


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
    return templates.TemplateResponse("transactions/customer_list.html", {"request": request, "txns": txns})

@txn_ext_router.get("/new", response_class=HTMLResponse)
def txn_ext_new(request: Request):
    db = get_db()
    pls      = db.execute("SELECT ps.*, c.customer_name FROM Packing_Slip ps LEFT JOIN Clients c ON ps.client_id=c.client_id ORDER BY ps.packing_slip_date DESC").fetchall()
    products = db.execute("SELECT parts_number, product_service_description, status FROM Product ORDER BY parts_number").fetchall()
    db.close()
    return templates.TemplateResponse("transactions/customer_form.html", {
        "request": request, "pls": pls, "products": products,
    })

@txn_ext_router.post("/new")
async def txn_ext_create(
    request: Request,
    packing_slip_id: str = Form(...),
    outbound_date: str = Form(""), inbound_date: str = Form(""),
    signature: str = Form(""), delivered_by: str = Form(""),
    discount: str = Form("0"),
):
    form = await request.form()
    # FIX (Bug 4): Wrap json.loads to avoid a 500 if parts_json is missing
    # or malformed (e.g. JS didn't run, empty submission).
    try:
        parts_list = json.loads(form.get("parts_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        parts_list = []

    db = get_db()
    cur = db.execute("""INSERT INTO Transaction_External
        (packing_slip_id, outbound_date, inbound_date, signature, delivered_by, discount)
        VALUES (?,?,?,?,?,?)""",
        (packing_slip_id, outbound_date or None, inbound_date or None,
         signature or None, delivered_by or None, float(discount or 0)))
    tid = cur.lastrowid
    for pn in parts_list:
        db.execute("INSERT INTO Transaction_External_Items (transaction_ext_id, parts_number) VALUES (?,?)", (tid, pn))
        db.execute("UPDATE Product SET status='On Loan' WHERE parts_number=?", (pn,))
    db.commit(); db.close()
    return RedirectResponse("/transactions/customer/", status_code=303)

@txn_ext_router.post("/{txn_id}/return")
async def txn_ext_return(txn_id: int, inbound_date: str = Form(...)):
    db = get_db()
    db.execute("UPDATE Transaction_External SET inbound_date=? WHERE transaction_ext_id=?", (inbound_date, txn_id))
    parts = db.execute("SELECT parts_number FROM Transaction_External_Items WHERE transaction_ext_id=?", (txn_id,)).fetchall()
    for p in parts:
        db.execute("UPDATE Product SET status='Available' WHERE parts_number=?", (p["parts_number"],))
    db.commit(); db.close()
    return RedirectResponse("/transactions/customer/", status_code=303)


# ── Internal Transactions ─────────────────────────────────────
txn_int_router = APIRouter(prefix="/transactions/internal", tags=["transactions"])

@txn_int_router.get("/", response_class=HTMLResponse)
def txn_int_list(request: Request):
    db = get_db()
    txns = db.execute("SELECT * FROM Transaction_Internal ORDER BY move_date DESC").fetchall()
    db.close()
    return templates.TemplateResponse("transactions/internal_list.html", {"request": request, "txns": txns})

@txn_int_router.get("/new", response_class=HTMLResponse)
def txn_int_new(request: Request):
    db = get_db()
    products   = db.execute("SELECT parts_number, product_service_description, location, status FROM Product ORDER BY parts_number").fetchall()
    warehouses = db.execute("SELECT * FROM Warehouse").fetchall()
    db.close()
    return templates.TemplateResponse("transactions/internal_form.html", {
        "request": request, "products": products, "warehouses": warehouses,
    })

@txn_int_router.post("/new")
async def txn_int_create(
    request: Request,
    from_location: str = Form(""), to_location: str = Form(""),
    move_date: str = Form(""), receive_date: str = Form(""),
    moved_by: str = Form(""), reason: str = Form(""),
):
    form = await request.form()
    # FIX (Bug 4): Same json.loads safety fix as txn_ext_create above.
    try:
        parts_list = json.loads(form.get("parts_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        parts_list = []

    db = get_db()
    cur = db.execute("""INSERT INTO Transaction_Internal
        (from_location, to_location, move_date, receive_date, moved_by, reason)
        VALUES (?,?,?,?,?,?)""",
        (from_location or None, to_location or None,
         move_date or None, receive_date or None,
         moved_by or None, reason or None))
    tid = cur.lastrowid
    for pn in parts_list:
        db.execute("INSERT INTO Transaction_Internal_Items (transaction_int_id, parts_number) VALUES (?,?)", (tid, pn))
        db.execute("UPDATE Product SET location=? WHERE parts_number=?", (to_location, pn))
    db.commit(); db.close()
    return RedirectResponse("/transactions/internal/", status_code=303)