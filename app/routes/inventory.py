from fastapi import APIRouter, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from datetime import date, datetime
import shutil
import config
from app.database import get_db
from app.logger import log_info, log_error

router = APIRouter(prefix="/inventory", tags=["inventory"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def get_status_options():
    db = get_db()
    rows = db.execute("SELECT name FROM Status ORDER BY display_order").fetchall()
    db.close()
    return [r["name"] for r in rows]


def get_yard_locations():
    db = get_db()
    rows = db.execute(
        "SELECT name FROM Location WHERE is_yard=1 ORDER BY name"
    ).fetchall()
    db.close()
    return [r["name"] for r in rows]


@router.get("/api/check-sn/{serial_number}")
def check_sn(serial_number: str):
    db = get_db()
    exists = (
        db.execute(
            "SELECT 1 FROM Product WHERE serial_number=?", (serial_number,)
        ).fetchone()
        is not None
    )
    db.close()
    return {"exists": exists}


@router.get("/", response_class=HTMLResponse)
def inventory_overview(
    request: Request,
    search: str = "",
    location: str = "",
    status: str = "",
    vendor: str = "",
):
    db = get_db()

    q = """
        SELECT 
            pn.parts_number,
            pn.description,
            pn.cost_price,
            pn.resale_price,
            pn.rental_price,
            v.name as vendor_name,
            COUNT(p.serial_number) as total_products,
            SUM(CASE WHEN p.status = 'Available' THEN 1 ELSE 0 END) as available_count,
            SUM(CASE WHEN p.status = 'Sold' THEN 1 ELSE 0 END) as sold_count,
            SUM(CASE WHEN p.status = 'On Loan' THEN 1 ELSE 0 END) as on_loan_count,
            SUM(CASE WHEN p.status = 'Pending Cert' THEN 1 ELSE 0 END) as pending_count,
            SUM(CASE WHEN p.status = 'Damaged' THEN 1 ELSE 0 END) as damaged_count,
            SUM(CASE WHEN p.status = 'In Repair' THEN 1 ELSE 0 END) as in_repair_count,
            SUM(CASE WHEN p.status = 'Retired / Decommissioned' THEN 1 ELSE 0 END) as retired_count,
            SUM(CASE WHEN p.status = 'Lost' THEN 1 ELSE 0 END) as lost_count,
            GROUP_CONCAT(DISTINCT p.location) as locations
        FROM PartNumber pn
        LEFT JOIN Product p ON pn.parts_number = p.parts_number
        LEFT JOIN Vendor v ON pn.vendor_name = v.name
        WHERE 1=1
    """
    args = []
    if search:
        q += " AND pn.parts_number LIKE ?"
        args.append(f"%{search}%")
    if location:
        q += " AND p.location LIKE ?"
        args.append(f"%{location}%")
    if status:
        q += " AND p.status = ?"
        args.append(status)
    if vendor:
        q += " AND v.name = ?"
        args.append(vendor)
    q += " GROUP BY pn.parts_number ORDER BY pn.parts_number"

    partnumbers = db.execute(q, args).fetchall()
    vendors = db.execute("SELECT * FROM Vendor ORDER BY name").fetchall()
    locations = db.execute("SELECT * FROM Location ORDER BY name").fetchall()
    db.close()

    return templates.TemplateResponse(
        "inventory/list.html",
        {
            "request": request,
            "partnumbers": partnumbers,
            "vendors": vendors,
            "locations": locations,
            "status_options": get_status_options(),
            "search": search,
            "filter_location": location,
            "filter_status": status,
            "filter_vendor": vendor,
        },
    )


@router.get("/part-number/new", response_class=HTMLResponse)
def partnumber_new(request: Request):
    db = get_db()
    vendors = db.execute("SELECT * FROM Vendor ORDER BY name").fetchall()
    db.close()
    return templates.TemplateResponse(
        "inventory/partnumber_form.html",
        {
            "request": request,
            "partnumber": None,
            "vendors": vendors,
        },
    )


@router.post("/part-number/new")
async def partnumber_create(
    request: Request,
    parts_number: str = Form(...),
    description: str = Form(""),
    cost_price: str = Form(""),
    resale_price: str = Form(""),
    rental_price: str = Form(""),
    weight: str = Form(""),
    dimensions: str = Form(""),
    vendor_name: str = Form(""),
):
    def _f(v):
        return float(v) if v else None

    from datetime import datetime

    now = datetime.now().isoformat()
    user = request.session.get("username", "unknown")

    db = get_db()
    try:
        db.execute(
            """INSERT INTO PartNumber VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                parts_number,
                description,
                _f(cost_price),
                _f(resale_price),
                _f(rental_price),
                _f(weight),
                dimensions or None,
                vendor_name or None,
                user,
                now,
                user,
                now,
            ),
        )
        db.commit()
        log_info(f"Created PartNumber: {parts_number} by {user}")
    except Exception as e:
        db.close()
        log_error(f"Failed to create PartNumber {parts_number}: {e}")
        return HTMLResponse(f"Error: {e}", status_code=400)
    db.close()
    return RedirectResponse("/inventory/", status_code=303)


@router.get("/part-number/{parts_number}", response_class=HTMLResponse)
def partnumber_detail(request: Request, parts_number: str):
    db = get_db()
    partnumber = db.execute(
        """SELECT pn.*, v.name as vendor_name 
           FROM PartNumber pn 
           LEFT JOIN Vendor v ON pn.vendor_name = v.name 
           WHERE pn.parts_number=?""",
        (parts_number,),
    ).fetchone()

    products = db.execute(
        """SELECT p.*,
           (SELECT COUNT(*) FROM Transaction_External_Items WHERE parts_number = p.serial_number) as txn_count
           FROM Product p
           WHERE p.parts_number = ?
           ORDER BY p.serial_number""",
        (parts_number,),
    ).fetchall()

    vendors = db.execute("SELECT * FROM Vendor ORDER BY name").fetchall()
    locations = db.execute("SELECT * FROM Location ORDER BY name").fetchall()
    db.close()

    from datetime import date, timedelta

    today_str = date.today().isoformat()
    today_30_str = (date.today() + timedelta(days=30)).isoformat()

    return templates.TemplateResponse(
        "inventory/partnumber_detail.html",
        {
            "request": request,
            "partnumber": partnumber,
            "products": products,
            "vendors": vendors,
            "locations": locations,
            "status_options": get_status_options(),
            "today": today_str,
            "today_30": today_30_str,
        },
    )


@router.get("/part-number/{parts_number}/edit", response_class=HTMLResponse)
def partnumber_edit_page(request: Request, parts_number: str):
    db = get_db()
    partnumber = db.execute(
        "SELECT * FROM PartNumber WHERE parts_number=?", (parts_number,)
    ).fetchone()
    vendors = db.execute("SELECT * FROM Vendor ORDER BY name").fetchall()
    db.close()
    return templates.TemplateResponse(
        "inventory/partnumber_form.html",
        {
            "request": request,
            "partnumber": partnumber,
            "vendors": vendors,
        },
    )


@router.post("/part-number/{parts_number}/edit")
async def partnumber_edit(
    request: Request,
    parts_number: str,
    description: str = Form(""),
    cost_price: str = Form(""),
    resale_price: str = Form(""),
    rental_price: str = Form(""),
    weight: str = Form(""),
    dimensions: str = Form(""),
    vendor_name: str = Form(""),
):
    def _f(v):
        return float(v) if v else None

    now = datetime.now().isoformat()
    user = request.session.get("username", "unknown")

    db = get_db()
    db.execute(
        """UPDATE PartNumber SET
        description=?, cost_price=?, resale_price=?, rental_price=?,
        weight=?, dimensions=?, vendor_name=?, modified_by=?, modified_at=?
        WHERE parts_number=?""",
        (
            description,
            _f(cost_price),
            _f(resale_price),
            _f(rental_price),
            _f(weight),
            dimensions or None,
            vendor_name or None,
            user,
            now,
            parts_number,
        ),
    )
    db.commit()
    log_info(f"Updated PartNumber: {parts_number} by {user}")
    db.close()
    return RedirectResponse(f"/inventory/part-number/{parts_number}", status_code=303)


@router.get("/product/new", response_class=HTMLResponse)
def product_new(request: Request, parts_number: str = ""):
    db = get_db()
    partnumbers = db.execute(
        "SELECT * FROM PartNumber ORDER BY parts_number"
    ).fetchall()
    all_locations = db.execute("SELECT * FROM Location ORDER BY name").fetchall()
    yard_locations = db.execute(
        "SELECT name FROM Location WHERE is_yard=1 ORDER BY name"
    ).fetchall()
    db.close()

    suggested_serial = ""
    if parts_number:
        suggested_serial = f"{parts_number}-????"

    return templates.TemplateResponse(
        "inventory/product_form.html",
        {
            "request": request,
            "product": None,
            "partnumbers": partnumbers,
            "preselected_parts_number": parts_number,
            "fixed_parts_number": parts_number if parts_number else None,
            "suggested_serial": suggested_serial,
            "status_options": get_status_options(),
            "locations": yard_locations,
        },
    )


@router.post("/product/new")
async def product_create(
    request: Request,
    serial_number: str = Form(...),
    parts_number: str = Form(...),
    status: str = Form("Available"),
    location: str = Form(""),
    receiving_date: str = Form(""),
    certification_expiration_date: str = Form(""),
    mtr_file: UploadFile = File(None),
    drawing_file: UploadFile = File(None),
):
    def save_file(upload_file, prefix):
        if not upload_file or not upload_file.filename:
            return None
        fn = f"{prefix}_{serial_number}_{upload_file.filename}"
        dest = config.UPLOAD_DIR / fn
        with open(dest, "wb") as f:
            shutil.copyfileobj(upload_file.file, f)
        return fn

    mtr_fn = save_file(mtr_file, "mtr")
    drawing_fn = save_file(drawing_file, "drw")

    now = datetime.now().isoformat()
    user = request.session.get("username", "unknown")

    db = get_db()

    existing = db.execute(
        "SELECT serial_number FROM Product WHERE serial_number=?", (serial_number,)
    ).fetchone()
    if existing:
        db.close()
        return HTMLResponse(
            f"""<!DOCTYPE html>
<html><head><title>Error</title><link rel="stylesheet" href="/static/css/main.css"></head>
<body style="display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
<div style="background:#2a2020;border:1px solid #6a3030;border-radius:8px;padding:24px;max-width:400px;text-align:center;">
<h3 style="color:#e07070;margin:0 0 8px;">Serial Number Exists</h3>
<p style="color:#aaa;margin:0;">{serial_number} is already in the system.</p>
</div></body></html>""",
            status_code=400,
        )

    try:
        db.execute(
            "INSERT INTO Product VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                serial_number,
                parts_number,
                status,
                location or None,
                receiving_date or None,
                certification_expiration_date or None,
                mtr_fn,
                drawing_fn,
                user,
                now,
                user,
                now,
            ),
        )
        db.commit()
        log_info(f"Created Product: {serial_number} by {user}")
    except Exception as e:
        db.close()
        log_error(f"Failed to create Product {serial_number}: {e}")
        return HTMLResponse(f"Error: {e}", status_code=400)
    db.close()
    return RedirectResponse(f"/inventory/part-number/{parts_number}", status_code=303)


@router.get("/product/{serial_number}", response_class=HTMLResponse)
def product_detail(request: Request, serial_number: str):
    db = get_db()
    product = db.execute(
        """SELECT p.*, pn.description as parts_description, pn.cost_price as purchase_price, pn.resale_price, pn.rental_price, v.name as vendor_name
           FROM Product p
           LEFT JOIN PartNumber pn ON p.parts_number = pn.parts_number
           LEFT JOIN Vendor v ON pn.vendor_name = v.name
           WHERE p.serial_number=?""",
        (serial_number,),
    ).fetchone()

    ext_txns = db.execute(
        """
        SELECT te.*, ps.packing_slip_number, c.name as customer_name
        FROM Transaction_External te
        JOIN Packing_Slip ps ON te.packing_slip_id=ps.packing_slip_number
        LEFT JOIN Clients c ON ps.client_id=c.client_id
        WHERE te.transaction_ext_id IN (
            SELECT transaction_ext_id FROM Transaction_External_Items WHERE serial_number=?
        ) ORDER BY te.outbound_date DESC
    """,
        (serial_number,),
    ).fetchall()

    int_txns = db.execute(
        """
        SELECT ti.* FROM Transaction_Internal ti
        WHERE ti.transaction_int_id IN (
            SELECT transaction_int_id FROM Transaction_Internal_Items WHERE serial_number=?
        ) ORDER BY ti.move_date DESC
    """,
        (serial_number,),
    ).fetchall()

    lifecycle = db.execute(
        """SELECT * FROM Product_Lifecycle 
           WHERE serial_number=? 
           ORDER BY change_date DESC, id DESC""",
        (serial_number,),
    ).fetchall()

    lifecycle_asc = db.execute(
        """SELECT * FROM Product_Lifecycle 
           WHERE serial_number=? 
           ORDER BY change_date ASC, id ASC""",
        (serial_number,),
    ).fetchall()

    from datetime import datetime, date

    total_on_loan_days = 0
    on_loan_start = None
    for entry in lifecycle_asc:
        if entry["new_status"] == "On Loan":
            on_loan_start = entry["change_date"]
        elif (
            entry["old_status"] == "On Loan" and on_loan_start and entry["change_date"]
        ):
            start = datetime.strptime(on_loan_start, "%Y-%m-%d").date()
            end = datetime.strptime(entry["change_date"], "%Y-%m-%d").date()
            total_on_loan_days += (end - start).days
            on_loan_start = None
    if on_loan_start:
        start = datetime.strptime(on_loan_start, "%Y-%m-%d").date()
        total_on_loan_days += (date.today() - start).days

    min_change_date = None
    if lifecycle and lifecycle[0]["change_date"]:
        min_change_date = lifecycle[0]["change_date"]

    end_statuses = ["Sold", "Lost", "Retired / Decommissioned"]
    updates_disabled = product["status"] in end_statuses if product else False

    purchase_price = product["purchase_price"] if product else None
    resale_price = product["resale_price"] if product else None
    rental_price = product["rental_price"] if product else None

    locations = db.execute("SELECT * FROM Location ORDER BY name").fetchall()
    db.close()
    return templates.TemplateResponse(
        "inventory/product_detail.html",
        {
            "request": request,
            "product": product,
            "product_status": product["status"] if product else None,
            "product_location": product["location"] if product else None,
            "status_options": get_status_options(),
            "ext_txns": ext_txns,
            "int_txns": int_txns,
            "lifecycle": lifecycle,
            "locations": locations,
            "purchase_price": purchase_price,
            "resale_price": resale_price,
            "rental_price": rental_price,
            "min_change_date": min_change_date,
            "updates_disabled": updates_disabled,
            "total_on_loan_days": total_on_loan_days,
        },
    )


@router.post("/product/{serial_number}/edit")
async def product_edit(
    request: Request,
    serial_number: str,
    status: str = Form(""),
    location: str = Form(""),
    change_date: str = Form(""),
    receiving_date: str = Form(""),
    certification_expiration_date: str = Form(""),
    mtr_file: UploadFile = File(None),
    drawing_file: UploadFile = File(None),
):
    def save_file(upload_file, prefix):
        if not upload_file or not upload_file.filename:
            return None
        fn = f"{prefix}_{serial_number}_{upload_file.filename}"
        dest = config.UPLOAD_DIR / fn
        with open(dest, "wb") as f:
            shutil.copyfileobj(upload_file.file, f)
        return fn

    now = datetime.now().isoformat()
    user = request.session.get("username", "unknown")

    db = get_db()

    existing = db.execute(
        """SELECT p.*, pn.rental_price 
           FROM Product p 
           LEFT JOIN PartNumber pn ON p.parts_number = pn.parts_number
           WHERE p.serial_number=?""",
        (serial_number,),
    ).fetchone()

    if not existing:
        db.close()
        return RedirectResponse(f"/inventory/product/{serial_number}", status_code=303)

    new_mtr_fn = save_file(mtr_file, "mtr") or existing["mtr_filename"]
    new_drawing_fn = save_file(drawing_file, "drw") or existing["drawing_filename"]

    upd_receiving_date = (
        receiving_date if receiving_date else existing["receiving_date"]
    )
    upd_cert_date = (
        certification_expiration_date
        if certification_expiration_date
        else existing["certification_expiration_date"]
    )

    old_status = existing["status"]
    old_location = existing["location"]

    new_status = status if status else old_status
    new_location = location if location else old_location

    today = change_date if change_date else str(date.today())

    status_changed = status and status != old_status
    location_changed = location and location != old_location

    if status_changed or location_changed:
        if today and today.strip():
            latest = db.execute(
                """SELECT change_date FROM Product_Lifecycle 
                   WHERE serial_number=? 
                   ORDER BY change_date DESC LIMIT 1""",
                (serial_number,),
            ).fetchone()

            if latest and latest["change_date"] and latest["change_date"] > today:
                db.close()
                return HTMLResponse(
                    f"Error: Change date cannot be earlier than the last recorded date ({latest['change_date']}). History chain would be broken.",
                    status_code=400,
                )

        yard_locs = get_yard_locations()
        is_yard = lambda loc: loc and loc in yard_locs

        if location_changed:
            txn_type = (
                "INTERNAL"
                if (is_yard(old_location) and is_yard(new_location))
                else "EXTERNAL"
            )
        else:
            all_statuses = get_status_options()
            txn_type = (
                "INTERNAL"
                if (old_status in all_statuses and new_status in all_statuses)
                else "EXTERNAL"
            )

        db.execute(
            """INSERT INTO Product_Lifecycle 
            (serial_number, change_date, old_status, new_status, old_location, new_location, transaction_type)
            VALUES (?,?,?,?,?,?,?)""",
            (
                serial_number,
                today,
                old_status if status_changed else None,
                new_status if status_changed else None,
                old_location if location_changed else None,
                new_location if location_changed else None,
                txn_type,
            ),
        )

        if txn_type == "INTERNAL" and location_changed:
            db.execute(
                """INSERT INTO Transaction_Internal 
                    (from_location, to_location, move_date, created_by, created_at)
                    VALUES (?,?,?,?,?)""",
                (old_location, new_location, today, user, now),
            )
            txn_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute(
                """INSERT INTO Transaction_Internal_Items 
                    (transaction_int_id, serial_number)
                    VALUES (?,?)""",
                (txn_id, serial_number),
            )

    db.execute(
        """UPDATE Product SET
        status=?, location=?, receiving_date=?,
        certification_expiration_date=?, mtr_filename=?, drawing_filename=?,
        modified_by=?, modified_at=?
        WHERE serial_number=?""",
        (
            new_status,
            new_location,
            upd_receiving_date,
            upd_cert_date,
            new_mtr_fn,
            new_drawing_fn,
            user,
            now,
            serial_number,
        ),
    )

    db.commit()
    log_info(f"Updated Product: {serial_number} by {user}")
    db.close()
    return RedirectResponse(f"/inventory/product/{serial_number}", status_code=303)
