from celery import Celery

from app.core.config import get_settings


settings = get_settings()
celery_app = Celery(
    "ashare_research",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    beat_schedule={
        "dispatch-transactional-outbox": {
            "task": "outbox.dispatch",
            "schedule": 3.0,
        }
    },
)
