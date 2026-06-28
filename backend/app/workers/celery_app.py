from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "medarchive",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_default_queue="medarchive",
    task_routes={"app.workers.*": {"queue": "medarchive"}},
)

