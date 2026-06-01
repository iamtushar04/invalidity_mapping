from sqlalchemy import Column, String, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
import uuid

from app.database import Base

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject_patent_id = Column(UUID(as_uuid=True), ForeignKey("patents.id", ondelete="SET NULL"), nullable=True)
    selected_claim_ids = Column(ARRAY(UUID(as_uuid=True)), default=[], nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="projects")
    patents = relationship("Patent", back_populates="project", foreign_keys="[Patent.project_id]", cascade="all, delete-orphan")
    analysis_jobs = relationship("AnalysisJob", back_populates="project", cascade="all, delete-orphan")
    claim_charts = relationship("ClaimChart", back_populates="project", cascade="all, delete-orphan")
    # newly added
    mappings = relationship("Mapping", back_populates="project", cascade="all, delete-orphan")

