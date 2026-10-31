from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import register_exception_handlers
from app.core.i18n import install_jinja
from app.routers import pages

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()
register_exception_handlers(app)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
install_jinja(templates.env)
app.state.templates = templates

app.include_router(pages.router)


@app.get("/health")
async def health(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}
