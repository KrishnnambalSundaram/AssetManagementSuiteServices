from sqlalchemy import Boolean, Column, String, ForeignKey
from sqlalchemy.orm import relationship

from src.utils.database import BaseSchema


class UserOrganization(BaseSchema):
    __tablename__ = "user_organizations"

    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), default="member", index=True)  # 'admin', 'member', 'viewer'
    is_active = Column(Boolean, default=True, index=True)

    # Relationships
    user = relationship("User", back_populates="user_organizations")
    organization = relationship("Organization", back_populates="user_organizations")
