from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ResearchJob, ResearchReport


class ResearchRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_job(self, *, user_id: str, stock_code: str, depth: str, risk_profile: str) -> ResearchJob:
        job = ResearchJob(user_id=user_id, stock_code=stock_code, depth=depth, risk_profile=risk_profile)
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_job(self, *, job_id: str, user_id: str) -> ResearchJob | None:
        return await self.session.scalar(
            select(ResearchJob).where(ResearchJob.id == job_id, ResearchJob.user_id == user_id)
        )

    async def get_job_for_worker(self, job_id: str) -> ResearchJob | None:
        return await self.session.get(ResearchJob, job_id)

    async def claim_job(self, job_id: str) -> ResearchJob | None:
        result = await self.session.execute(
            update(ResearchJob)
            .where(ResearchJob.id == job_id, ResearchJob.status.in_(("pending", "queued")))
            .values(status="running", progress=10, started_at=datetime.now(timezone.utc))
        )
        if result.rowcount != 1:
            return None
        await self.session.flush()
        return await self.session.get(ResearchJob, job_id)

    async def list_jobs(self, *, user_id: str, limit: int = 50) -> list[ResearchJob]:
        rows = await self.session.scalars(
            select(ResearchJob)
            .where(ResearchJob.user_id == user_id)
            .order_by(ResearchJob.created_at.desc())
            .limit(limit)
        )
        return list(rows)

    async def save(self, job: ResearchJob) -> None:
        await self.session.flush()

    async def get_report(self, *, job_id: str, user_id: str) -> ResearchReport | None:
        return await self.session.scalar(
            select(ResearchReport)
            .join(ResearchJob)
            .where(ResearchReport.job_id == job_id, ResearchJob.user_id == user_id)
        )

    async def create_report(self, report: ResearchReport) -> ResearchReport:
        self.session.add(report)
        await self.session.flush()
        return report
