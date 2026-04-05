from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import shutil
from app.database import get_db
import config

router = APIRouter(prefix="/inventory", tags=["inventory"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

STATUS_OPTIONS = [
    "Available",
    "Pending Certification",
    "On Loan",
    "Sold",
    "Damaged",
    "In Repair",
    "Retired / Decommissioned",
    "Lost",
]


@router.get("/", response_class=HTMLResponse)
def inventory_list(
    request: Request, search: str = "", status: str = "", location: str = ""
):
    db = get_db()
    q = "SELECT p.*, v.vendor_name FROM Product p LEFT JOIN Vendor v ON p.vendor_id=v.vendor_id WHERE 1=1"
    args = []
    if search:
        q += " AND (p.parts_number LIKE ? OR p.product_service_description LIKE ?)"
        args += [f"%{search}%", f"%{search}%"]
    if status:
        q += " AND p.status=?"
        args.append(status)
    if location:
        q += " AND p.location LIKE ?"
        args.append(f"%{location}%")
    q += " ORDER BY p.parts_number"
    products = db.execute(q, args).fetchall()
    vendors = db.execute("SELECT * FROM Vendor ORDER BY vendor_name").fetchall()
    db.close()
    return templates.TemplateResponse(
        "inventory/list.html",
        {
            "request": request,
            "products": products,
            "vendors": vendors,
            "status_options": STATUS_OPTIONS,
            "search": search,
            "filter_status": status,
            "filter_location": location,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def inventory_new(request: Request):
    db = get_db()
    vendors = db.execute("SELECT * FROM Vendor ORDER BY vendor_name").fetchall()
    db.close()
    return templates.TemplateResponse(
        "inventory/form.html",
        {
            "request": request,
            "product": None,
            "vendors": vendors,
            "status_options": STATUS_OPTIONS,
        },
    )


@router.post("/new")
async def inventory_create(
    parts_number: str = Form(...),
    product_service_description: str = Form(""),
    cost_price: str = Form(""),
    resale_price: str = Form(""),
    list_price: str = Form(""),
    purchase_date: str = Form(""),
    resale_date: str = Form(""),
    recertification_date: str = Form(""),
    certification_expiration_date: str = Form(""),
    weight: str = Form(""),
    dimensions: str = Form(""),
    status: str = Form("Available"),
    location: str = Form(""),
    vendor_id: str = Form(""),
    mtr_file: UploadFile = File(None),
    drawing_file: UploadFile = File(None),
):
    def _f(v):
        return float(v) if v else None

    mtr_fn = drawing_fn = None
    if mtr_file and mtr_file.filename:
        mtr_fn = f"mtr_{parts_number}_{mtr_file.filename}"
        dest = config.UPLOAD_DIR / mtr_fn
        with open(dest, "wb") as f:
            shutil.copyfileobj(mtr_file.file, f)
    if drawing_file and drawing_file.filename:
        drawing_fn = f"drw_{parts_number}_{drawing_file.filename}"
        dest = config.UPLOAD_DIR / drawing_fn
        with open(dest, "wb") as f:
            shutil.copyfileobj(drawing_file.file, f)

    db = get_db()
    db.execute(
        """INSERT INTO Product VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            parts_number,
            product_service_description,
            _f(cost_price),
            _f(resale_price),
            _f(list_price),
            purchase_date or None,
            resale_date or None,
            recertification_date or None,
            certification_expiration_date or None,
            mtr_fn,
            drawing_fn,
            _f(weight),
            dimensions or None,
            status,
            _f(cost_price),
            location or None,
            vendor_id or None,
        ),
    )
    db.commit()
    db.close()
    return RedirectResponse("/inventory/", status_code=303)


@router.get("/{parts_number}", response_class=HTMLResponse)
def inventory_detail(request: Request, parts_number: str):
    db = get_db()
    product = db.execute(
        "SELECT p.*, v.vendor_name FROM Product p LEFT JOIN Vendor v ON p.vendor_id=v.vendor_id WHERE p.parts_number=?",
        (parts_number,),
    ).fetchone()
    vendors = db.execute("SELECT * FROM Vendor ORDER BY vendor_name").fetchall()
    ext_txns = db.execute(
        """
        SELECT te.*, ps.packing_slip_number, c.customer_name
        FROM Transaction_External te
        JOIN Packing_Slip ps ON te.packing_slip_id=ps.packing_slip_number
        LEFT JOIN Clients c ON ps.client_id=c.client_id
        WHERE te.transaction_ext_id IN (
            SELECT transaction_ext_id FROM Transaction_External_Items WHERE parts_number=?
        ) ORDER BY te.outbound_date DESC
    """,
        (parts_number,),
    ).fetchall()
    int_txns = db.execute(
        """
        SELECT ti.* FROM Transaction_Internal ti
        WHERE ti.transaction_int_id IN (
            SELECT transaction_int_id FROM Transaction_Internal_Items WHERE parts_number=?
        ) ORDER BY ti.move_date DESC
    """,
        (parts_number,),
    ).fetchall()
    db.close()
    return templates.TemplateResponse(
        "inventory/detail.html",
        {
            "request": request,
            "product": product,
            "vendors": vendors,
            "status_options": STATUS_OPTIONS,
            "ext_txns": ext_txns,
            "int_txns": int_txns,
        },
    )


@router.post("/{parts_number}/edit")
async def inventory_edit(
    parts_number: str,
    product_service_description: str = Form(""),
    cost_price: str = Form(""),
    resale_price: str = Form(""),
    list_price: str = Form(""),
    purchase_date: str = Form(""),
    resale_date: str = Form(""),
    recertification_date: str = Form(""),
    certification_expiration_date: str = Form(""),
    weight: str = Form(""),
    dimensions: str = Form(""),
    status: str = Form("Available"),
    location: str = Form(""),
    vendor_id: str = Form(""),
    mtr_file: UploadFile = File(None),
    drawing_file: UploadFile = File(None),
):
    def _f(v):
        return float(v) if v else None

    db = get_db()
    existing = db.execute(
        "SELECT * FROM Product WHERE parts_number=?", (parts_number,)
    ).fetchone()

    mtr_fn = existing["mtr_filename"]
    drawing_fn = existing["drawing_filename"]
    if mtr_file and mtr_file.filename:
        mtr_fn = f"mtr_{parts_number}_{mtr_file.filename}"
        with open(config.UPLOAD_DIR / mtr_fn, "wb") as f:
            shutil.copyfileobj(mtr_file.file, f)
    if drawing_file and drawing_file.filename:
        drawing_fn = f"drw_{parts_number}_{drawing_file.filename}"
        with open(config.UPLOAD_DIR / drawing_fn, "wb") as f:
            shutil.copyfileobj(drawing_file.file, f)

    db.execute(
        """UPDATE Product SET
        product_service_description=?, cost_price=?, resale_price=?, list_price=?,
        purchase_date=?, resale_date=?, recertification_date=?,
        certification_expiration_date=?, mtr_filename=?, drawing_filename=?,
        weight=?, dimensions=?, status=?, location=?, vendor_id=?
        WHERE parts_number=?""",
        (
            product_service_description,
            _f(cost_price),
            _f(resale_price),
            _f(list_price),
            purchase_date or None,
            resale_date or None,
            recertification_date or None,
            certification_expiration_date or None,
            mtr_fn,
            drawing_fn,
            _f(weight),
            dimensions or None,
            status,
            location or None,
            vendor_id or None,
            parts_number,
        ),
    )
    db.commit()
    db.close()
    return RedirectResponse(f"/inventory/{parts_number}", status_code=303)


@router.get("/file/{filename}")
def serve_file(filename: str):
    upload_root = config.UPLOAD_DIR.resolve()
    path = (config.UPLOAD_DIR / filename).resolve()
    if not str(path).startswith(str(upload_root)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(path))
