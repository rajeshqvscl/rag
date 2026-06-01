from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.db.session import Base

class PitchDeck(Base):
    __tablename__ = "pitch_deck_library"

    id = Column(Integer, primary_key=True, index=True)
    company = Column(String, index=True)
    status = Column(String, default="processing")
    summary = Column(Text)
    email_draft = Column(Text)
    verdict = Column(String)
    score = Column(Float)
    insights = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archived_reason = Column(String, nullable=True)

class JobRecord(Base):
    """
    Persistent job queue for async pipeline execution.

    States:
      queued -> processing -> completed
                          -> degraded -> completed
                                       -> retrying -> processing
                                                    -> failed
                          -> failed
      Or direct: queued -> cancelled
    """
    __tablename__ = "job_queue"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String, default="queued", index=True)  # queued|processing|degraded|retrying|completed|failed|cancelled
    stage = Column(String, default="")
    progress = Column(Integer, default=0)
    error = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    file_name = Column(String, nullable=True)
    file_size = Column(Integer, default=0)
    result_id = Column(Integer, nullable=True)  # FK to pitch_deck_library.id
    pipeline_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class ClientRevert(Base):
    __tablename__ = "client_reverts"

    id = Column(Integer, primary_key=True, index=True)
    company = Column(String, index=True)
    type = Column(String, default="client")
    sender = Column(String)
    subject = Column(String)
    body = Column(Text)
    status = Column(String, default="pending")
    processed_at = Column(DateTime(timezone=True), nullable=True)
    document_path = Column(String, nullable=True)

    intent = Column(String)
    confidence = Column(Float)
    signals = Column(Text)

    next_step = Column(Text)
    priority = Column(String)
    reasoning = Column(Text)

    score = Column(Float)
    cheque_size = Column(String)
    sector = Column(String)
    urgency_level = Column(String)
    query_type = Column(String)

    email_draft = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archived_reason = Column(String, nullable=True)
