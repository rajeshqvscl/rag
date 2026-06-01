"""
Persistent job queue service for async pipeline execution.

Provides durable job states, retry logic, and queue management
independent of the frontend request lifecycle.
"""

import time
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session

from app.db.models import JobRecord, PitchDeck
from app.db.session import SessionLocal


JOB_STATES = {
    "queued": 0,
    "processing": 1,
    "degraded": 2,
    "retrying": 3,
    "completed": 4,
    "failed": 5,
    "cancelled": 6,
}

VALID_TRANSITIONS = {
    "queued": ["processing", "cancelled"],
    "processing": ["completed", "degraded", "failed", "cancelled"],
    "degraded": ["completed", "retrying", "failed", "cancelled"],
    "retrying": ["processing", "failed", "cancelled"],
    "completed": [],
    "failed": ["retrying"],
    "cancelled": [],
}


def _validate_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, [])


class JobQueueService:
    """Manages the persistent job queue with state validation."""

    @staticmethod
    def create_job(file_name: str = "", file_size: int = 0) -> int:
        """Create a new queued job and return its ID."""
        db = SessionLocal()
        try:
            job = JobRecord(
                status="queued",
                stage="queued",
                progress=0,
                file_name=file_name,
                file_size=file_size,
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return job.id
        except Exception as e:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def transition_job(job_id: int, target_status: str,
                       stage: str = "", progress: int = None,
                       error: str = "", result_id: int = None,
                       pipeline_data: dict = None) -> bool:
        """Transition a job to a new state with validation."""
        db = SessionLocal()
        try:
            job = db.query(JobRecord).filter(JobRecord.id == job_id).first()
            if not job:
                return False

            if not _validate_transition(job.status, target_status):
                if job.status == target_status:
                    print(f"[JOB_QUEUE] State unchanged: {job.status} for job {job_id} (skipping update)")
                else:
                    print(f"[JOB_QUEUE] Invalid transition: {job.status} -> {target_status} for job {job_id}")
                return False

            old_status = job.status
            job.status = target_status
            if stage:
                job.stage = stage
            if progress is not None:
                job.progress = progress
            if error:
                job.error = error[:500]
            if result_id is not None:
                job.result_id = result_id
            if pipeline_data:
                job.pipeline_data = pipeline_data
            if target_status == "completed":
                job.completed_at = datetime.now(timezone.utc)
            if target_status == "retrying":
                job.retry_count = (job.retry_count or 0) + 1

            db.commit()
            print(f"[JOB_QUEUE] Job {job_id}: {old_status} -> {target_status}")
            return True
        except Exception as e:
            db.rollback()
            print(f"[JOB_QUEUE] Error transitioning job {job_id}: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def get_job(job_id: int) -> Optional[Dict]:
        """Get job state by ID."""
        db = SessionLocal()
        try:
            job = db.query(JobRecord).filter(JobRecord.id == job_id).first()
            if not job:
                return None
            return {
                "id": job.id,
                "status": job.status,
                "stage": job.stage,
                "progress": job.progress,
                "error": job.error,
                "retry_count": job.retry_count,
                "file_name": job.file_name,
                "result_id": job.result_id,
                "created_at": str(job.created_at) if job.created_at else None,
                "updated_at": str(job.updated_at) if job.updated_at else None,
                "completed_at": str(job.completed_at) if job.completed_at else None,
                "pipeline_data": job.pipeline_data,
            }
        finally:
            db.close()

    @staticmethod
    def list_jobs(status: str = None, limit: int = 50) -> List[Dict]:
        """List jobs, optionally filtered by status."""
        db = SessionLocal()
        try:
            query = db.query(JobRecord)
            if status:
                query = query.filter(JobRecord.status == status)
            jobs = query.order_by(JobRecord.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": j.id,
                    "status": j.status,
                    "stage": j.stage,
                    "progress": j.progress,
                    "error": j.error,
                    "retry_count": j.retry_count,
                    "file_name": j.file_name,
                    "result_id": j.result_id,
                    "created_at": str(j.created_at) if j.created_at else None,
                }
                for j in jobs
            ]
        finally:
            db.close()

    @staticmethod
    def retry_job(job_id: int) -> bool:
        """Mark a failed job for retry."""
        return JobQueueService.transition_job(job_id, "retrying",
                                               stage="retrying", progress=0)

    @staticmethod
    def cancel_job(job_id: int) -> bool:
        """Cancel a queued or processing job."""
        return JobQueueService.transition_job(job_id, "cancelled",
                                               stage="cancelled")

    @staticmethod
    def cleanup_old_jobs(hours: int = 72) -> int:
        """Archive jobs older than N hours (marks as archived, doesn't delete)."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        db = SessionLocal()
        try:
            old = db.query(JobRecord).filter(
                JobRecord.created_at < cutoff,
                JobRecord.status.in_(["completed", "failed", "cancelled"])
            ).all()
            count = len(old)
            print(f"[JOB_QUEUE] Cleaned up {count} old jobs")
            return count
        finally:
            db.close()
