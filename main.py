from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.database import init_db
from app.routes.inventory import router as inv_router
from app.routes.quotes import router as q_router
from app.routes.packing_slips import router as pl_router
from app.routes.invoices import router as inv_doc_router
from app.routes.other import (
    clients_router,
    vendors_router,
    locations_router,
    txn_ext_router,
    txn_int_router,
)
from app.routes.pdf_api import router as pdf_api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Steel River Technologies — Inventory", lifespan=lifespan)

app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "app" / "static")),
    name="static",
)

app.mount(
    "/uploads",
    StaticFiles(directory=str(Path(__file__).parent / "data" / "uploads")),
    name="uploads",
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "app" / "templates"))

app.include_router(inv_router)
app.include_router(q_router)
app.include_router(pl_router)
app.include_router(inv_doc_router)
app.include_router(clients_router)
app.include_router(vendors_router)
app.include_router(locations_router)
app.include_router(txn_ext_router)
app.include_router(txn_int_router)
app.include_router(pdf_api_router)


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    from app.database import get_db

    db = get_db()
    stats = {
        "total_products": db.execute("SELECT COUNT(*) FROM Product").fetchone()[0],
        "available": db.execute(
            "SELECT COUNT(*) FROM Product WHERE status='Available'"
        ).fetchone()[0],
        "open_quotes": 0,
        "open_pls": 0,
        "open_invoices": 0,
        "total_clients": db.execute("SELECT COUNT(*) FROM Clients").fetchone()[0],
    }
    recent_quotes = []
    recent_pls = []
    db.close()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stats": stats,
            "recent_quotes": recent_quotes,
            "recent_pls": recent_pls,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
