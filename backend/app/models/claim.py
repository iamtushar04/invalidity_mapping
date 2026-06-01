from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.database import Base

# class Claim(Base):
#     __tablename__ = "claims"
    
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     patent_id = Column(UUID(as_uuid=True), ForeignKey("patents.id", ondelete="CASCADE"), nullable=False)
#     claim_number = Column(Integer, nullable=False)
#     claim_text = Column(String, nullable=False)
#     claim_type = Column(String, default="independent") # independent, dependent
#     parent_claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="SET NULL"), nullable=True)
    
#     patent = relationship("Patent", back_populates="claims")
#     # dependents = relationship("Claim", backref=relationship("Claim", remote_side=[id]))
#     parent = relationship(
#     "Claim",
#     remote_side=[id],
#     backref="dependents"
# )
#     elements = relationship("ClaimElement", back_populates="claim", cascade="all, delete-orphan")
#     mappings = relationship("Mapping", back_populates="claim", cascade="all, delete-orphan")
#     scores = relationship("Score", back_populates="claim", cascade="all, delete-orphan")

class Claim(Base):
    __tablename__ = "claims"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    patent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("patents.id", ondelete="CASCADE"),
        nullable=False
    )

    claim_number = Column(Integer, nullable=False)

    claim_text = Column(String, nullable=False)

    claim_type = Column(String, default="independent")

    parent_claim_id = Column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="SET NULL"),
        nullable=True
    )

    patent = relationship("Patent", back_populates="claims")

    parent = relationship(
        "Claim",
        remote_side=[id],
        backref="dependents"
    )

    elements = relationship(
        "ClaimElement",
        back_populates="claim",
        cascade="all, delete-orphan"
    )

    mappings = relationship(
        "Mapping",
        back_populates="claim",
        cascade="all, delete-orphan"
    )

    scores = relationship(
        "Score",
        back_populates="claim",
        cascade="all, delete-orphan"
    )