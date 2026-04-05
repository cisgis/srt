from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa
from pathlib import Path
import io
import config

router = APIRouter(prefix="/api/pdf", tags=["pdf"])

# ── Jinja2 Setup ────────────────────────────────────────────
templates_dir = Path(__file__).parent.parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(templates_dir)))


# ── Request Models ──────────────────────────────────────────
class LineItem(BaseModel):
    parts_number: str
    description: str
    quantity: int
    weight_dimension: Optional[str] = ""


class PackingSlipData(BaseModel):
    packing_slip_number: str
    date: str
    customer_name: str
    billing_address: Optional[str] = ""
    well_address: Optional[str] = ""
    ship_from: Optional[str] = "SRT Warehouse"
    ship_via: Optional[str] = ""
    po_number: Optional[str] = ""
    quote_number: Optional[str] = ""
    payment_term: Optional[str] = ""
    items: list[LineItem]


# ── PDF Generation Endpoint ─────────────────────────────────
@router.post("/packing-slip")
async def generate_packing_slip_pdf(data: PackingSlipData):
    """
    Generate a packing slip PDF from JSON data.

    Example request body:
    {
        "packing_slip_number": "PL03152026-001",
        "date": "03/15/26",
        "customer_name": "NEXTIER COMPLETION SOLUTIONS",
        "billing_address": "1902 S Midland Dr, Midland, TX 79703",
        "well_address": "NEXTIER GN",
        "ship_from": "SRT Warehouse",
        "ship_via": "Company Truck",
        "po_number": "PO-12345",
        "quote_number": "20260307-2",
        "payment_term": "Net 60",
        "items": [
            {
                "parts_number": "FLANGE6-4THREAD",
                "description": "6\" FLANGE REDUCED TO 4\" THREAD",
                "quantity": 120,
                "weight_dimension": "50 lbs / 12x12x6"
            }
        ]
    }
    """
    # Load template
    template = jinja_env.get_template("packing_slip_pdf.html")

    # Render HTML
    html_content = template.render(
        packing_slip_number=data.packing_slip_number,
        date=data.date,
        customer_name=data.customer_name,
        billing_address=data.billing_address,
        well_address=data.well_address,
        ship_from=data.ship_from,
        ship_via=data.ship_via,
        po_number=data.po_number,
        quote_number=data.quote_number,
        payment_term=data.payment_term,
        items=[item.model_dump() for item in data.items],
        logo_path=config.LOGO_PATH.as_uri() if config.LOGO_PATH.exists() else None,
    )

    # Generate PDF using xhtml2pdf
    pdf_buf = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_content, dest=pdf_buf)

    if pisa_status.err:
        return Response(
            content="Error generating PDF",
            status_code=500,
        )

    pdf_buf.seek(0)

    return Response(
        content=pdf_buf.read(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{data.packing_slip_number}.pdf"'
        },
    )
