from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

from app.database import get_db, close_db, init_db
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
from app.logger import log_info, log_error, log_warning


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Steel River Technologies — Inventory", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key="srt-dev-key")

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


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error},
    )


@app.post("/login")
def login_submit(
    request: Request, username: str = Form(...), password: str = Form(...)
):
    db = get_db()
    user = db.execute(
        "SELECT * FROM Users WHERE username=? AND password=? AND is_active=1",
        (username, password),
    ).fetchone()
    close_db()

    if user:
        request.session["authenticated"] = True
        request.session["username"] = username
        log_info(f"User logged in: {username}")
        return RedirectResponse("/", status_code=303)
    log_warning(f"Failed login attempt: {username}")
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Invalid credentials"},
    )


@app.get("/logout")
def logout(request: Request):
    user = request.session.get("username", "unknown")
    request.session.clear()
    log_info(f"User logged out: {user}")
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if not request.session.get("authenticated"):
        return RedirectResponse("/login", status_code=303)

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
    close_db()

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

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, workers=1)
