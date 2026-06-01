from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.database import Base

class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    reference_patent_id = Column(UUID(as_uuid=True), ForeignKey("patents.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, default="pending") # pending, running, completed, failed
    error_message = Column(String, nullable=True)
    
    project = relationship("Project", back_populates="analysis_jobs")
