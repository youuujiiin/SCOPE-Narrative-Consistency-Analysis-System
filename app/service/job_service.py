
"""진행 중 분석 작업 조회 및 고착 작업 복구."""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChapterStatus, User
from app.repository.analysis_repo import AnalysisRepository
from app.repository.chapter_repo import ChapterRepository
from app.schemas.job import ActiveJob, ActiveJobsOut
from app.service.chapter_service import ChapterService

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = [
    ChapterStatus.extracting.value,
    ChapterStatus.reviewing.value,
]


class JobService:
    def __init__(self, session: AsyncSession) -> None:
        self.s = session
        self.chapters = ChapterRepository(session)

    async def _recover_stale(self, chapter_id) -> bool:
        """고착된 회차를 실패 처리한다. 성공 시 True."""

        # 동일 회차에 대한 동시 변경 방지
        chapter = await self.chapters.lock(chapter_id)

        if chapter is None:
            await self.s.rollback()
            return False

        # 잠금 이후 최신 상태를 다시 확인
        if chapter.status not in ACTIVE_STATUSES:
            await self.s.rollback()
            return False

        if not ChapterService.is_stale(chapter):
            await self.s.rollback()
            return False

        stage = (
            "review"
            if chapter.status == ChapterStatus.reviewing.value
            else "extract"
        )

        analysis = AnalysisRepository(self.s)

        row = await analysis.get_latest(chapter.id)
        if row is None:
            row = await analysis.create_pending(chapter.id)

        await analysis.save_failure(
            row,
            "분석 제한 시간 초과 또는 워커 비정상 종료",
            stage=stage,
        )

        chapter.status = ChapterStatus.failed.value
        await self.s.commit()

        logger.warning(
            "stale job recovered: project=%s chapter=%s stage=%s",
            chapter.project_id,
            chapter.chapter_no,
            stage,
        )

        return True

    async def list_active(self, user: User) -> ActiveJobsOut:
        """진행 중 작업을 조회하고 고착된 작업을 복구한다."""

        rows = await self.chapters.list_active_for_owner(
            user.id, ACTIVE_STATUSES
        )

        # 고착된 작업만 처리
        for chapter, _, _ in rows:
            if ChapterService.is_stale(chapter):
                try:
                    await self._recover_stale(chapter.id)
                except Exception:
                    await self.s.rollback()
                    logger.exception(
                        "stale job recovery failed: chapter=%s",
                        chapter.id,
                    )

        # 복구 후 DB를 다시 조회하여 실제 진행 중인 작업만 반환
        rows = await self.chapters.list_active_for_owner(
            user.id, ACTIVE_STATUSES
        )

        now = dt.datetime.now(dt.timezone.utc)

        return ActiveJobsOut(
            items=[
                ActiveJob(
                    project_id=chapter.project_id,
                    project_name=project_name,
                    chapter_no=chapter.chapter_no,
                    title=chapter.title,
                    status=chapter.status,
                    progress=progress,
                    started_at=chapter.updated_at,
                    stale=ChapterService.is_stale(chapter, now),
                )
                for chapter, project_name, progress in rows
            ]
        )
