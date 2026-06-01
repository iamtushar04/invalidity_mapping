# from sqlalchemy import Column, String, Numeric, ForeignKey
# from sqlalchemy.dialects.postgresql import UUID
# from sqlalchemy.orm import relationship
# import uuid

# from app.database import Base

# class ClaimElement(Base):
#     __tablename__ = "claim_elements"
    
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
#     element_id = Column(String, nullable=False) # e.g. 1A, 1B
#     label = Column(String, nullable=True) # e.g. Preamble, Step 1
#     text = Column(String, nullable=False)
#     weight = Column(Numeric(5, 2), default=0.0) # percentage weight
    
#     claim = relationship("Claim", back_populates="elements")
#     mappings = relationship("Mapping", back_populates="element", cascade="all, delete-orphan")

# class Mapping(Base):
#     __tablename__ = "mappings"
    
#     id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
#     claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
#     # element_id = Column(UUID(as_uuid=True), ForeignKey("claim_elements.id", ondelete="CASCADE"), nullable=False)
#     element_id = Column("claim_element_id", UUID(as_uuid=True), ForeignKey("claim_elements.id", ondelete="CASCADE"), nullable=False)
#     cited_passage = Column("cited_passages", String, nullable=True)
#     rationale = Column("llm_rationale", String, nullable=True)
#     reference_patent_id = Column(UUID(as_uuid=True), ForeignKey("patents.id", ondelete="CASCADE"), nullable=False)
#     classification = Column(String, default="N") # Y, Partial, Obviousness, N
#     analyst_classification = Column(String, nullable=True) # overrides classification
#     # cited_passage = Column(String, nullable=True)
#     analyst_override = Column(String, nullable=True) # overrides cited passage
#     # rationale = Column(String, nullable=True)
#     para_ref = Column(String, nullable=True)
#     fig_ref = Column(String, nullable=True)
    
#     claim = relationship("Claim", back_populates="mappings")
#     element = relationship("ClaimElement", back_populates="mappings")
#     reference_patent = relationship("Patent", back_populates="mappings", foreign_keys=[reference_patent_id])
from sqlalchemy import Column, String, ForeignKey, Numeric, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class ClaimElement(Base):
    __tablename__ = "claim_elements"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    element_id = Column(String, nullable=False)
    label = Column(String, nullable=True)
    text = Column(String, nullable=False)
    weight = Column(Numeric(5, 2), default=0.0)
    comment = Column(String, nullable=True)
    is_custom = Column(Boolean, default=False)
    
    
    claim = relationship("Claim", back_populates="elements")
    mappings = relationship("Mapping", back_populates="element", cascade="all, delete-orphan")
    project = relationship("Project")
    user = relationship("User")


class Mapping(Base):
    __tablename__ = "mappings"
    
    # NOT NULL in DB
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    element_id = Column("claim_element_id", UUID(as_uuid=True), ForeignKey("claim_elements.id", ondelete="CASCADE"), nullable=False)
    reference_patent_id = Column(UUID(as_uuid=True), ForeignKey("patents.id", ondelete="CASCADE"), nullable=False)

    # NULLABLE in DB
    claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), nullable=True)
    classification = Column(String, nullable=True, default="N")
    cited_passage = Column("cited_passages", JSONB, nullable=True)
    rationale = Column("llm_rationale", String, nullable=True)
    analyst_override = Column(String, nullable=True)
    analyst_classification = Column(String, nullable=True)
    para_ref = Column(String, nullable=True)
    fig_ref = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    claim = relationship("Claim", back_populates="mappings")
    element = relationship("ClaimElement", back_populates="mappings")
    reference_patent = relationship("Patent", back_populates="mappings", foreign_keys=[reference_patent_id])
    project = relationship("Project", back_populates="mappings")
    user = relationship("User")