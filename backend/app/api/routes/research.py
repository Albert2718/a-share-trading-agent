from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import CurrentUser, DbSession
from app.repositories.research_repository import ResearchRepository
from app.repositories.outbox_repository import OutboxRepository
from app.schemas.research import ResearchJobCreate, ResearchJobResponse, ResearchReportResponse
from app.services.research_service import ResearchService


router = APIRouter(prefix="/research", tags=["research"])


@router.post("/jobs", response_model=ResearchJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(payload: ResearchJobCreate, current_user: CurrentUser, session: DbSession):
    service = ResearchService(ResearchRepository(session), OutboxRepository(session))
    job = await service.submit(user_id=current_user.id, **payload.model_dump())
    return ResearchJobResponse.model_validate(job)


@router.get("/jobs", response_model=list[ResearchJobResponse])
async def list_jobs(current_user: CurrentUser, session: DbSession):
    jobs = await ResearchRepository(session).list_jobs(user_id=current_user.id)
    return [ResearchJobResponse.model_validate(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=ResearchJobResponse)
async def get_job(job_id: str, current_user: CurrentUser, session: DbSession):
    job = await ResearchRepository(session).get_job(job_id=job_id, user_id=current_user.id)
    if job is None:
        raise HTTPException(status_code=404, detail="研究任务不存在")
    return ResearchJobResponse.model_validate(job)


@router.get("/jobs/{job_id}/report", response_model=ResearchReportResponse)
async def get_report(job_id: str, current_user: CurrentUser, session: DbSession):
    report = await ResearchRepository(session).get_report(job_id=job_id, user_id=current_user.id)
    if report is None:
        raise HTTPException(status_code=404, detail="研究报告尚未生成")
    return ResearchReportResponse(
        id=report.id,
        job_id=report.job_id,
        action=report.action,
        confidence=float(report.confidence),
        rank_score=report.rank_score,
        summary=report.summary,
        report_payload=report.report_payload,
        created_at=report.created_at,
    )
