from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pathlib import Path
import json
from datetime import datetime, timedelta
from app.database import get_db, next_doc_number
from app.services import pdf_service, email_service
from app.logger import log_info, log_error
import config

router = APIRouter(prefix="/quotes", tags=["quotes"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

PAYMENT_TERMS = ["COD", "Net 7", "Net 14", "Net 21", "Net 30", "Net 60"]


@router.get("/", response_class=HTMLResponse)
def quotes_list(request: Request):
    db = get_db()
    quotes = db.execute("""
        SELECT q.*, c.name as client_name
        FROM Quote q
        LEFT JOIN Clients c ON q.client_id = c.client_id
        ORDER BY q.quote_date DESC
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
        tax = item_subtotal * tax_rate
        discount = float(q.get("discount") or 0)
        shipping = float(q.get("shipping_cost") or 0)

        total = item_subtotal + tax - discount + shipping

        q["subtotal_value"] = item_subtotal
        q["discount_value"] = discount
        q["shipping_value"] = shipping
        q["total_value"] = total

    db.close()
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
            f"COALESCE(SUM(CASE WHEN p.location = '{y['name']}' AND p.status = 'Available' THEN 1 ELSE 0 END), 0) as {y['name'].lower().replace(' ', '_')}"
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

    partnumbers_json = [dict(p) for p in partnumbers]
    db.close()

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

        db.execute(
            """INSERT INTO Quote (quote_number, quote_type, quote_date, quote_expiration_date, payment_term, ship_to, ship_from, sales_tax_rate, rental_days, discount, shipping_cost, client_id, created_by, created_at, modified_by, modified_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                """INSERT INTO Quote_Items (quote_number,parts_number,quantity,quoted_price,lead_time, yard)
                          VALUES (?,?,?,?,?,?)""",
                (
                    qnum,
                    it["parts_number"],
                    qty,
                    price,
                    it.get("lead_time", ""),
                    it.get("yard", ""),
                ),
            )
        db.commit()
        log_info(f"Created Quote: {qnum} by {user}")
        db.close()
        return RedirectResponse(f"/quotes/{qnum}", status_code=303)
    except Exception as e:
        log_error(f"Failed to create quote: {e}")
        import traceback

        traceback.print_exc()
        return HTMLResponse(f"Error: {e}", status_code=400)


@router.get("/{quote_number}", response_class=HTMLResponse)
def quote_edit(request: Request, quote_number: str):
    db = get_db()

    quote = dict(
        db.execute(
            "SELECT * FROM Quote WHERE quote_number=?", (quote_number,)
        ).fetchone()
    )

    if not quote:
        db.close()
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

    items_query = db.execute(
        "SELECT * FROM Quote_Items WHERE quote_number=?", (quote_number,)
    ).fetchall()
    items = [dict(r) for r in items_query]

    partnumbers_json = [dict(p) for p in partnumbers]
    db.close()

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
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "total": total,
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
                discount=?, shipping_cost=?, client_id=?, modified_by=?, modified_at=?
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
                """INSERT INTO Quote_Items (quote_number,parts_number,quantity,quoted_price,lead_time, yard)
                          VALUES (?,?,?,?,?,?)""",
                (
                    quote_number,
                    it["parts_number"],
                    qty,
                    price,
                    it.get("lead_time", ""),
                    it.get("yard", ""),
                ),
            )

        db.commit()
        log_info(f"Updated Quote: {quote_number} by {user}")
        db.close()
        return RedirectResponse(f"/quotes/{quote_number}", status_code=303)
    except Exception as e:
        log_error(f"Failed to update quote {quote_number}: {e}")
        import traceback

        traceback.print_exc()
        return HTMLResponse(f"Error: {e}", status_code=400)


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
        db.close()

        # Calculate totals
        subtotal = sum(
            item.get("quantity", 0) * item.get("quoted_price", 0) for item in items
        )
        if quote.get("rental_days"):
            subtotal = subtotal * quote["rental_days"]
        tax_rate = quote.get("sales_tax_rate") or 0
        tax = subtotal * tax_rate
        discount = quote.get("discount") or 0
        shipping = quote.get("shipping_cost") or 0
        total = subtotal + tax - discount + shipping

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

        # Generate PDF using Playwright
        import asyncio

        async def generate_pdf():
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.set_content(html_content)
                await page.wait_for_load_state("networkidle")
                pdf = await page.pdf(
                    format="Letter",
                    print_background=True,
                    display_header_footer=False,
                )
                await browser.close()
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
        db.close()
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
    db.close()
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
    db.close()

    return {"ok": result["ok"], "error": result.get("error")}
