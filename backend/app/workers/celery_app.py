from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "hiremesh",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
    include=[
        "app.workers.tasks.parse_resume",
        "app.workers.tasks.embed_candidate",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
