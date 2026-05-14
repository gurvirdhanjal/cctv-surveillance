"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from vms.api.routes import health, persons

app = FastAPI(title="VMS API", version="0.1.0")

app.include_router(health.router, prefix="/api")
app.include_router(persons.router, prefix="/api")
