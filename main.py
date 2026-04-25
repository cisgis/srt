from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
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
from config import DB_PATH


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
    "/data/uploads",
    StaticFiles(directory=str(Path(__file__).parent / "data" / "uploads")),
    name="uploads",
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "app" / "templates"))

# Health check endpoint
@app.get("/health")
def health_check():
    """Health check endpoint for monitoring"""
    import os
    db_exists = os.path.exists("srt.db")
    db_size = os.path.getsize("srt.db") if db_exists else 0
    return {"status": "healthy", "database": db_exists, "db_size_bytes": db_size}

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and show friendly error page"""
    log_error(f"Unhandled exception: {exc}")
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "error": str(exc)[:200],
            "path": request.url.path,
        },
        status_code=500,
    )

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

# Database setup on startup
@app.on_event("startup")
async def startup():
    init_db()


@app.on_event("shutdown")
async def shutdown():
    close_db()


# Manual backup endpoint
import shutil


@app.get("/backup")
def manual_backup():
    """Manual backup endpoint"""
    db_path = DB_PATH
    backup_dir = Path(__file__).parent / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"srt_{timestamp}.db"
        shutil.copy2(db_path, backup_file)

        # Keep only last 10 backups
        backups = sorted(backup_dir.glob("srt_*.db"), reverse=True)
        for old in backups[10:]:
            old.unlink()

        print(f"Database backed up: {backup_file}")

    return {"ok": True, "message": "Database backed up"}


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    if not request.session.get("authenticated"):
        return RedirectResponse("/login", status_code=303)

    db = get_db()
    try:
        db.execute("ALTER TABLE Invoice ADD COLUMN status TEXT DEFAULT 'OPEN'")
    except:
        pass
    try:
        db.execute("ALTER TABLE Invoice ADD COLUMN pl_attachment_path TEXT")
    except:
        pass
    try:
        db.execute("ALTER TABLE Quote ADD COLUMN status TEXT DEFAULT 'DRAFT'")
    except:
        pass
    try:
        db.execute("ALTER TABLE Packing_Slip ADD COLUMN status TEXT DEFAULT 'DRAFT'")
    except:
        pass

    stats = {
        "total_products": db.execute("SELECT COUNT(*) FROM Product").fetchone()[0],
        "available": db.execute(
            "SELECT COUNT(*) FROM Product WHERE status='In Stock'"
        ).fetchone()[0],
        "open_quotes": db.execute(
            "SELECT COUNT(*) FROM Quote WHERE status != 'CLOSED'"
        ).fetchone()[0],
        "open_pls": db.execute(
            "SELECT COUNT(*) FROM Packing_Slip WHERE status = 'DRAFT'"
        ).fetchone()[0],
        "open_invoices": db.execute(
            "SELECT COUNT(*) FROM Invoice WHERE status != 'PAID'"
        ).fetchone()[0],
        "total_clients": db.execute("SELECT COUNT(*) FROM Clients").fetchone()[0],
    }
    recent_quotes = db.execute(
        "SELECT q.quote_number, q.quote_date, c.name as customer_name FROM Quote q LEFT JOIN Clients c ON q.client_id=c.client_id ORDER BY q.created_at DESC LIMIT 5"
    ).fetchall()
    recent_pls = db.execute(
        "SELECT pl.packing_slip_number, pl.packing_slip_date, c.name as customer_name FROM Packing_Slip pl LEFT JOIN Clients c ON pl.client_id=c.client_id ORDER BY pl.created_at DESC LIMIT 5"
    ).fetchall()
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, workers=1)