from sqlalchemy import Column, String, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import uuid

class ElementWeight(Base):
    __tablename__ = "element_weights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    element_id = Column(String, nullable=False)
    text = Column(String, nullable=True)
    weight = Column(Float, nullable=False, default=0.0)
