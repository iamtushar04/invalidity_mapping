from sqlalchemy import Column, String, DateTime, func, ForeignKey, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.database import Base

class Patent(Base):
    __tablename__ = "patents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    patent_number = Column(String, index=True, nullable=False)
    title = Column(String, nullable=True)
    abstract = Column(String, nullable=True)
    assignee = Column(String, nullable=True)
    is_reference = Column(Boolean, default=False)
    fetch_status = Column(String, default="pending") # pending, success, failed
    structured_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    project = relationship("Project", back_populates="patents", foreign_keys=[project_id])
    claims = relationship("Claim", back_populates="patent", cascade="all, delete-orphan", lazy="selectin")
    mappings = relationship("Mapping", back_populates="reference_patent", foreign_keys="[Mapping.reference_patent_id]", cascade="all, delete-orphan")
    scores = relationship("Score", back_populates="reference_patent", cascade="all, delete-orphan")
