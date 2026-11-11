from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import config
from errors import register_error_handlers
from routers import catalogues, farms, plots


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Resolve DATABASE_URL once, so a bad value stops startup instead of failing every request.
    app.state.database_url = config.database_url()
    yield


app = FastAPI(title="AgroPilot registry-service", version="0.1.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(farms.router)
app.include_router(plots.router)
app.include_router(catalogues.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
