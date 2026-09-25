from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..services.changelog import render_changelog

router = APIRouter(include_in_schema=False)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@router.get("/get-started", response_class=HTMLResponse)
async def get_started(request: Request):
    return templates.TemplateResponse(request, "get-started.html", {"request": request})


@router.get("/self-host", response_class=HTMLResponse)
async def self_host(request: Request):
    return templates.TemplateResponse(request, "self-host.html", {"request": request})


@router.get("/changelog", response_class=HTMLResponse)
async def changelog(request: Request):
    return templates.TemplateResponse(
        request, "changelog.html", {"request": request, "changelog_html": render_changelog()}
    )
