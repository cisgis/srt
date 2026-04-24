from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json
import asyncio
from datetime import datetime, timedelta
from app.database import get_db, close_db, next_doc_number
from app.services import pdf_service, email_service
from app.logger import log_info, log_error
import config

router = APIRouter(prefix="/quotes", tags=["quotes"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

PAYMENT_TERMS = ["COD", "Net 7", "Net 14", "Net 21", "Net 30", "Net 60"]

# Cached browser for PDF generation
_pdf_browser = None
_pdf_playwright = None


async def get_pdf_browser():
    global _pdf_browser, _pdf_playwright
    from playwright.async_api import async_playwright

    if _pdf_browser is None or not _pdf_browser.is_connected():
        _pdf_playwright = await async_playwright().start()
        _pdf_browser = await _pdf_playwright.chromium.launch()
    return _pdf_browser


async def close_pdf_browser():
    global _pdf_browser, _pdf_playwright
    if _pdf_browser:
        await _pdf_browser.close()
        _pdf_browser = None
    if _pdf_playwright:
        await _pdf_playwright.stop()
        _pdf_playwright = None


@router.get("/", response_class=HTMLResponse)
def quotes_list(request: Request):
    db = get_db()
    quotes = db.execute("""
        SELECT q.*, c.name as client_name
        FROM Quote q
        LEFT JOIN Clients c ON q.client_id = c.client_id
        ORDER BY q.created_at DESC
    """).fetchall()
    quotes_list = [dict(q) for q in quotes]

    for q in quotes_list:
        items = db.execute(
            "SELECT SUM(quantity * quoted_price) as subtotal FROM Quote_Items WHERE quote_number = ?",
            (q["quote_number"],),
        ).fetchone()

        item_subtotal = float(items["subtotal"]) if items and items["subtotal"] else 0.0
        rental_days = int(q.get("rental_days") or 0)
        if rental_days:
            item_subtotal = item_subtotal * rental_days

        tax_rate = float(q.get("sales_tax_rate") or 0)
        discount = float(q.get("discount") or 0)
        shipping = float(q.get("shipping_cost") or 0)

        tax = (item_subtotal - discount) * tax_rate

        total = (item_subtotal - discount) * (1 + tax_rate) + shipping

        q["subtotal_value"] = item_subtotal
        q["discount_value"] = discount
        q["shipping_value"] = shipping
        q["total_value"] = total

    close_db()
    return templates.TemplateResponse(
        "quotes/list.html", {"request": request, "quotes": quotes_list}
    )


@router.get("/new", response_class=HTMLResponse)
def quote_new(request: Request):
    db = get_db()

    clients = db.execute(
        "SELECT client_id, name, company, site_address FROM Clients ORDER BY company, name"
    ).fetchall()

    clients_by_company = {}
    for c in clients:
        company = c["company"] or c["name"] or "Unknown"
        if company not in clients_by_company:
            clients_by_company[company] = []
        clients_by_company[company].append(
            {
                "client_id": c["client_id"],
                "name": c["name"],
                "site_address": c["site_address"] or "",
            }
        )

    yards = db.execute(
        "SELECT name FROM Location WHERE is_yard=1 ORDER BY name"
    ).fetchall()
    yards_list = [y["name"] for y in yards]

    yard_case = ", ".join(
        [
            f"COALESCE(SUM(CASE WHEN p.location = '{y['name']}' AND p.status = 'In Stock' THEN 1 ELSE 0 END), 0) as {y['name'].lower().replace(' ', '_')}_in_stock, "
            f"COALESCE(SUM(CASE WHEN p.location = '{y['name']}' AND p.status = 'Inbound in Transit' THEN 1 ELSE 0 END), 0) as {y['name'].lower().replace(' ', '_')}_in_transit"
            for y in yards
        ]
    )

    partnumbers = db.execute(f"""
        SELECT 
            pn.parts_number,
            pn.description,
            pn.resale_price,
            pn.rental_price,
            {yard_case}
        FROM PartNumber pn
        LEFT JOIN Product p ON pn.parts_number = p.parts_number
        GROUP BY pn.parts_number
        ORDER BY pn.parts_number
    """).fetchall()

    partnumbers_json = []
    for pn in partnumbers:
        pn_dict = dict(pn)
        avail = {}
        in_transit = {}
        for yard in yards_list:
            col_name = yard.lower().replace(" ", "_")
            avail[yard] = pn_dict.get(f"{col_name}_in_stock", 0)
            in_transit[yard] = pn_dict.get(f"{col_name}_in_transit", 0)
            for key in [f"{col_name}_in_stock", f"{col_name}_in_transit"]:
                if key in pn_dict:
                    del pn_dict[key]
        pn_dict["availability"] = avail
        pn_dict["in_transit"] = in_transit
        partnumbers_json.append(pn_dict)
    close_db()

    today = datetime.now().strftime("%Y-%m-%d")
    expiration = (datetime.now().date() + timedelta(days=14)).strftime("%Y-%m-%d")

    return templates.TemplateResponse(
        "quotes/form.html",
        {
            "request": request,
            "clients_by_company": clients_by_company,
            "clients_by_company_json": clients_by_company,
            "partnumbers": partnumbers_json,
            "partnumbers_json": partnumbers_json,
            "yards": yards_list,
            "yards_json": yards_list,
            "payment_terms": PAYMENT_TERMS,
            "today": today,
            "default_expiration": expiration,
        },
    )


@router.post("/new")
async def quote_create(
    request: Request,
    quote_type: str = Form("SALE"),
    quote_date: str = Form(...),
    quote_expiration_date: str = Form(""),
    payment_term: str = Form(""),
    ship_to: str = Form(""),
    ship_from: str = Form(""),
    sales_tax_rate: str = Form("0"),
    rental_days: str = Form(""),
    discount: str = Form("0"),
    shipping_cost: str = Form("0"),
    client_id: str = Form(""),
    contact_person: str = Form(""),
    items_json: str = Form("[]"),
):
    now = datetime.now().isoformat()
    user = request.session.get("username", "unknown")

    try:
        db = get_db()
        mmddyyyy = datetime.strptime(quote_date, "%Y-%m-%d").strftime("%m%d%Y")
        qnum = next_doc_number(db, "Q", mmddyyyy)

        # Add status column if it doesn't exist
        columns = [r[1] for r in db.execute("PRAGMA table_info(Quote)").fetchall()]
        if "status" not in columns:
            db.execute("""ALTER TABLE Quote ADD COLUMN status TEXT DEFAULT 'DRAFT'""")
        
        # Add status column to Quote_Items if it doesn't exist
        item_columns = [r[1] for r in db.execute("PRAGMA table_info(Quote_Items)").fetchall()]
        if "status" not in item_columns:
            db.execute("""ALTER TABLE Quote_Items ADD COLUMN status TEXT DEFAULT 'In Stock'""")
            db.commit()

        db.execute(
            """INSERT INTO Quote (quote_number, quote_type, quote_date, quote_expiration_date, payment_term, ship_to, ship_from, sales_tax_rate, rental_days, discount, shipping_cost, client_id, contact_person, status, created_by, created_at, modified_by, modified_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                qnum,
                quote_type,
                quote_date,
                quote_expiration_date or None,
                payment_term or None,
                ship_to or None,
                ship_from or None,
                float(sales_tax_rate or 0) / 100 if sales_tax_rate else 0,
                int(rental_days) if rental_days and rental_days.isdigit() else None,
                float(discount or 0) if discount else 0,
                float(shipping_cost or 0) if shipping_cost else 0,
                int(client_id) if client_id and client_id.isdigit() else None,
                contact_person or None,
                "DRAFT",
                user,
                now,
                user,
                now,
            ),
        )
        db.commit()

        try:
            items = json.loads(items_json)
        except (json.JSONDecodeError, TypeError):
            items = []

        for it in items:
            try:
                price = float(it.get("quoted_price") or 0)
            except (ValueError, TypeError):
                price = 0.0
            try:
                qty = int(it.get("quantity") or 1)
            except (ValueError, TypeError):
                qty = 1
            db.execute(
                """INSERT INTO Quote_Items (quote_number,parts_number,quantity,quoted_price,lead_time, yard, status)
                          VALUES (?,?,?,?,?,?,?)""",
                (
                    qnum,
                    it["parts_number"],
                    qty,
                    price,
                    it.get("lead_time", ""),
                    it.get("yard", ""),
                    it.get("status", "In Stock"),
                ),
            )
        db.commit()
        log_info(f"Created Quote: {qnum} by {user}")
        close_db()
        return RedirectResponse(f"/quotes/{qnum}", status_code=303)
    except Exception as e:
        log_error(f"Failed to create quote: {e}")
        import traceback

        traceback.print_exc()
        return HTMLResponse(f"Error: {e}", status_code=400)


@router.get("/{quote_number}", response_class=HTMLResponse)
def quote_edit(request: Request, quote_number: str, success: str = ""):
    db = get_db()

    quote = dict(
        db.execute(
            "SELECT * FROM Quote WHERE quote_number=?", (quote_number,)
        ).fetchone()
    )

    if not quote:
        close_db()
        return HTMLResponse("Quote not found", status_code=404)

    print(f"DEBUG: quote_number={quote_number}")

    clients = db.execute(
        "SELECT client_id, name, company, site_address FROM Clients ORDER BY company, name"
    ).fetchall()

    clients_by_company = {}
    for c in clients:
        company = c["company"] or c["name"] or "Unknown"
        if company not in clients_by_company:
            clients_by_company[company] = []
        clients_by_company[company].append(
            {
                "client_id": c["client_id"],
                "name": c["name"],
                "site_address": c["site_address"] or "",
            }
        )

    selected_company = ""
    contacts_for_selected = []
    if quote.get("client_id"):
        try:
            client_row = db.execute(
                "SELECT * FROM Clients WHERE client_id=?", (int(quote["client_id"]),)
            ).fetchone()
            if client_row:
                selected_company = client_row["company"] or client_row["name"] or ""
                if selected_company and selected_company in clients_by_company:
                    contacts_for_selected = clients_by_company[selected_company]
        except:
            pass

    locations = db.execute(
        "SELECT name FROM Location WHERE is_yard=1 ORDER BY name"
    ).fetchall()
    yards_list = [y["name"] for y in locations]

    partnumbers = db.execute("""
        SELECT pn.parts_number, pn.description, pn.resale_price, pn.rental_price
        FROM PartNumber pn ORDER BY pn.parts_number
    """).fetchall()

    # Get availability by parts_number and location from Product table
    availability = {}
    in_transit = {}
    for pn in partnumbers:
        pn_name = pn["parts_number"]
        availability[pn_name] = {}
        in_transit[pn_name] = {}
        for loc in locations:
            loc_name = loc["name"]
            in_stock_count = db.execute(
                """
                SELECT COUNT(*) as cnt FROM Product 
                WHERE parts_number=? AND location=? AND status='In Stock'
            """,
                (pn_name, loc_name),
            ).fetchone()["cnt"]
            transit_count = db.execute(
                """
                SELECT COUNT(*) as cnt FROM Product 
                WHERE parts_number=? AND location=? AND status='Inbound in Transit'
            """,
                (pn_name, loc_name),
            ).fetchone()["cnt"]
            availability[pn_name][loc_name] = in_stock_count
            in_transit[pn_name][loc_name] = transit_count

    items_query = db.execute(
        "SELECT * FROM Quote_Items WHERE quote_number=?", (quote_number,)
    ).fetchall()
    items = [dict(r) for r in items_query]

    # Group items by parts_number
    grouped_items = {}
    for item in items:
        pn = item.get("parts_number")
        if pn:
            if pn not in grouped_items:
                grouped_items[pn] = []
            grouped_items[pn].append(item)
    
    # Convert to list of groups for template
    grouped_items_list = [{"parts_number": pn, "items": item_list} for pn, item_list in grouped_items.items()] if grouped_items else []
    
    print(f"DEBUG: items={len(items)}, grouped={len(grouped_items_list)}")

    # Add availability to partnumbers_json
    partnumbers_json = []
    for pn in partnumbers:
        pn_dict = dict(pn)
        pn_dict["availability"] = availability.get(pn["parts_number"], {})
        pn_dict["in_transit"] = in_transit.get(pn["parts_number"], {})
        partnumbers_json.append(pn_dict)

    close_db()

    subtotal = sum(item["quantity"] * item["quoted_price"] for item in items)
    if quote.get("rental_days"):
        subtotal = subtotal * quote["rental_days"]
    tax_amount = subtotal * (quote.get("sales_tax_rate") or 0)
    discount = quote.get("discount") or 0
    shipping = quote.get("shipping_cost") or 0
    total = subtotal + tax_amount - discount + shipping

    return templates.TemplateResponse(
        "quotes/edit.html",
        {
            "request": request,
            "quote_number": quote_number,
            "quote": quote,
            "clients_by_company": clients_by_company,
            "clients_by_company_json": clients_by_company,
            "selected_company": selected_company,
            "contacts_for_selected": contacts_for_selected,
            "partnumbers": partnumbers_json,
            "partnumbers_json": partnumbers_json,
            "yards": yards_list,
            "yards_json": yards_list,
            "locations": [{"name": y} for y in yards_list],
            "payment_terms": PAYMENT_TERMS,
            "items": items,
            "grouped_items": grouped_items_list,
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "total": total,
            "success": success,
        },
    )


@router.post("/{quote_number}/edit")
async def quote_edit_submit(
    request: Request,
    quote_number: str,
    quote_type: str = Form("SALE"),
    quote_date: str = Form(...),
    quote_expiration_date: str = Form(""),
    payment_term: str = Form(""),
    ship_to: str = Form(""),
    ship_from: str = Form(""),
    sales_tax_rate: str = Form("0"),
    rental_days: str = Form(""),
    discount: str = Form("0"),
    shipping_cost: str = Form("0"),
    client_id: str = Form(""),
    contact_person: str = Form(""),
    items_json: str = Form("[]"),
):
    now = datetime.now().isoformat()
    user = request.session.get("username", "unknown")

    try:
        db = get_db()

        db.execute(
            """UPDATE Quote SET 
                quote_type=?, quote_date=?, quote_expiration_date=?, payment_term=?,
                ship_to=?, ship_from=?, sales_tax_rate=?, rental_days=?,
                discount=?, shipping_cost=?, client_id=?, contact_person=?, modified_by=?, modified_at=?
            WHERE quote_number=?""",
            (
                quote_type,
                quote_date,
                quote_expiration_date or None,
                payment_term or None,
                ship_to or None,
                ship_from or None,
                float(sales_tax_rate or 0) / 100 if sales_tax_rate else 0,
                int(rental_days) if rental_days and rental_days.isdigit() else None,
                float(discount or 0) if discount else 0,
                float(shipping_cost or 0) if shipping_cost else 0,
                int(client_id) if client_id and client_id.isdigit() else None,
                contact_person or None,
                user,
                now,
                quote_number,
            ),
        )

        db.execute("DELETE FROM Quote_Items WHERE quote_number=?", (quote_number,))

        try:
            items = json.loads(items_json)
        except (json.JSONDecodeError, TypeError):
            items = []

        for it in items:
            try:
                price = float(it.get("quoted_price") or 0)
            except (ValueError, TypeError):
                price = 0.0
            try:
                qty = int(it.get("quantity") or 1)
            except (ValueError, TypeError):
                qty = 1
            db.execute(
                """INSERT INTO Quote_Items (quote_number,parts_number,quantity,quoted_price,lead_time, yard, status)
                          VALUES (?,?,?,?,?,?,?)""",
                (
                    quote_number,
                    it["parts_number"],
                    qty,
                    price,
                    it.get("lead_time", ""),
                    it.get("yard", ""),
                    it.get("status", "In Stock"),
                ),
            )

        db.commit()
        log_info(f"Updated Quote: {quote_number} by {user}")
        close_db()
        return RedirectResponse(f"/quotes/{quote_number}?success=1", status_code=303)
    except Exception as e:
        log_error(f"Failed to update quote {quote_number}: {e}")
        import traceback

        traceback.print_exc()
        try:
            close_db()
        except:
            pass
        return HTMLResponse(f"Error: {e}", status_code=400)


@router.post("/{quote_number}/status")
async def quote_update_status(
    request: Request,
    quote_number: str,
    status: str = Form(...),
):
    user = request.session.get("username", "unknown")
    now = datetime.now().isoformat()

    db = get_db()
    db.execute(
        "UPDATE Quote SET status=?, modified_by=?, modified_at=? WHERE quote_number=?",
        (status, user, now, quote_number),
    )
    db.commit()
    close_db()
    log_info(f"Quote {quote_number} status changed to {status} by {user}")
    return RedirectResponse(f"/quotes/{quote_number}", status_code=303)


@router.get("/{quote_number}/create-packing-slip")
def quote_create_packing_slip(request: Request, quote_number: str):
    db = get_db()
    quote_row = db.execute(
        "SELECT * FROM Quote WHERE quote_number=?", (quote_number,)
    ).fetchone()
    if not quote_row:
        close_db()
        return HTMLResponse("Quote not found", status_code=404)

    quote = dict(quote_row)

    items = db.execute(
        "SELECT * FROM Quote_Items WHERE quote_number=?", (quote_number,)
    ).fetchall()
    close_db()

    items_list = [dict(i) for i in items]
    items_json = json.dumps(
        [
            {
                "parts_number": i["parts_number"],
                "quantity": i["quantity"],
                "yard": i.get("yard", ""),
                "status": i.get("status", "In Stock"),
            }
            for i in items_list
        ]
    )

    return RedirectResponse(
        f"/packing-slips/new?quote_number={quote_number}&client_id={quote.get('client_id')}&ship_to={quote.get('ship_to', '')}&items_json={items_json}",
        status_code=303,
    )


@router.get("/{quote_number}/pdf")
def quote_pdf(quote_number: str):
    try:
        db = get_db()
        quote = dict(
            db.execute(
                "SELECT * FROM Quote WHERE quote_number=?", (quote_number,)
            ).fetchone()
        )
        client = {}
        if quote.get("client_id"):
            row = db.execute(
                "SELECT * FROM Clients WHERE client_id=?", (quote["client_id"],)
            ).fetchone()
            if row:
                client = dict(row)
        items = [
            dict(r)
            for r in db.execute(
                """
            SELECT qi.*, pn.description
            FROM Quote_Items qi JOIN PartNumber pn ON qi.parts_number=pn.parts_number
            WHERE qi.quote_number=?
        """,
                (quote_number,),
            ).fetchall()
        ]
        close_db()

        # Calculate totals
        subtotal = sum(
            item.get("quantity", 0) * item.get("quoted_price", 0) for item in items
        )
        if quote.get("rental_days"):
            subtotal = subtotal * quote["rental_days"]
        tax_rate = quote.get("sales_tax_rate") or 0
        discount = quote.get("discount") or 0
        shipping = quote.get("shipping_cost") or 0
        tax = (subtotal - discount) * tax_rate
        total = subtotal - discount + tax + shipping

        # Convert logo to base64
        import base64

        logo_b64 = ""
        logo_path = config.LOGO_PATH
        if logo_path and logo_path.exists():
            with open(logo_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode("utf-8")
                # Determine content type
                if logo_path.suffix.lower() == ".png":
                    logo_b64 = f"data:image/png;base64,{logo_b64}"
                elif logo_path.suffix.lower() == ".webp":
                    logo_b64 = f"data:image/webp;base64,{logo_b64}"
                elif logo_path.suffix.lower() in [".jpg", ".jpeg"]:
                    logo_b64 = f"data:image/jpeg;base64,{logo_b64}"

        from fastapi.templating import Jinja2Templates
        from pathlib import Path

        TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
        templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

        context = {
            "quote": quote,
            "client": client,
            "items": items,
            "subtotal": subtotal,
            "tax": tax,
            "total": total,
            "logo_data": logo_b64,
        }

        html_content = templates.get_template("quotes/pdf.html").render(context)

        async def generate_pdf():
            browser = await get_pdf_browser()
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content(html_content)
            await page.wait_for_load_state("domcontentloaded")
            pdf = await page.pdf(
                format="Letter",
                print_background=True,
                display_header_footer=False,
                margin={"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"},
            )
            await page.close()
            await context.close()
            return pdf

        pdf_content = asyncio.run(generate_pdf())

        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{quote_number}.pdf"'
            },
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        return HTMLResponse(f"Error generating PDF: {e}", status_code=500)


@router.post("/{quote_number}/send")
async def quote_send(
    quote_number: str,
    to_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
):
    db = get_db()
    quote = db.execute(
        "SELECT * FROM Quote WHERE quote_number=?", (quote_number,)
    ).fetchone()
    if not quote:
        close_db()
        return {"ok": False, "error": f"Quote '{quote_number}' not found"}

    quote = dict(quote)
    client = {}
    if quote.get("client_id"):
        row = db.execute(
            "SELECT * FROM Clients WHERE client_id=?", (quote["client_id"],)
        ).fetchone()
        if row:
            client = dict(row)
    items = [
        dict(r)
        for r in db.execute(
            """
        SELECT qi.*, pn.description
        FROM Quote_Items qi JOIN PartNumber pn ON qi.parts_number=pn.parts_number
        WHERE qi.quote_number=?
    """,
            (quote_number,),
        ).fetchall()
    ]
    close_db()
    pdf = pdf_service.build_quote_pdf(quote, client, items)
    result = email_service.send_document_email(
        to_email, subject, body, pdf, f"{quote_number}.pdf"
    )

    db = get_db()
    db.execute(
        """INSERT INTO Email_Log (doc_type, doc_number, to_email, subject, status, error_message)
                  VALUES (?, ?, ?, ?, ?, ?)""",
        (
            "quote",
            quote_number,
            to_email,
            subject,
            "sent" if result["ok"] else "failed",
            result.get("error"),
        ),
    )
    db.commit()
    close_db()

    return {"ok": result["ok"], "error": result.get("error")}
