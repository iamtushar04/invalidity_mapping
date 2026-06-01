from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.database import Base

class ClaimChart(Base):
    __tablename__ = "claim_charts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    reference_patent_id = Column(UUID(as_uuid=True), ForeignKey("patents.id", ondelete="CASCADE"), nullable=False)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    chart_rows = Column(JSON, nullable=True)
    exported_at = Column(DateTime(timezone=True), nullable=True)
    export_format = Column(String, nullable=True)
    
    project = relationship("Project", back_populates="claim_charts")
