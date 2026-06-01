from sqlalchemy import Column, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.database import Base

class Score(Base):
    __tablename__ = "scores"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    reference_patent_id = Column(UUID(as_uuid=True), ForeignKey("patents.id", ondelete="CASCADE"), nullable=False)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    # score = Column(Numeric(5, 2), default=0.0)
    score = Column("weighted_score", Numeric(5, 2), default=0.0)
    
    reference_patent = relationship("Patent", back_populates="scores")
    claim = relationship("Claim", back_populates="scores")
