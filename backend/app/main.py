from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.api.ask import router as ask_router
from app.api.auth import router as auth_router
from app.api.candidates import router as candidates_router
from app.api.clients import router as clients_router
from app.api.jobs import router as jobs_router
from app.api.notes import router as notes_router
from app.api.pipeline import jobs_pipeline as pipeline_jobs_router
from app.api.pipeline import links as pipeline_links_router
from app.api.resumes import router as resumes_router
from app.api.search import router as search_router
from app.api.stages import router as stages_router
from app.api.users import router as users_router
from app.core import db as db_module
from app.services.stages import seed_default_template_if_needed
from app.services.users import bootstrap_admin_if_needed


@asynccontextmanager
async def lifespan(_: FastAPI):
    with db_module.SessionLocal() as db:
        bootstrap_admin_if_needed(db)
        seed_default_template_if_needed(db)
    yield


app = FastAPI(title="Hiremesh API", version="0.1.0", lifespan=lifespan)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(stages_router)
app.include_router(clients_router)
app.include_router(jobs_router)
app.include_router(candidates_router)
app.include_router(notes_router)
app.include_router(resumes_router)
app.include_router(pipeline_jobs_router)
app.include_router(pipeline_links_router)
app.include_router(search_router)
app.include_router(ask_router)
app.include_router(admin_router)
