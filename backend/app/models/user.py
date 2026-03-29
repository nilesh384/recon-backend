from typing import Optional

from sqlmodel import Field, Relationship, SQLModel

from app.models.base import Base


class UserBase(SQLModel):
    email: str = Field(max_length=320, unique=True, index=True)
    username: str = Field(max_length=50, unique=True, index=True)
    is_active: bool = Field(default=True)


class User(Base, UserBase, table=True):
    __tablename__ = "users"

    hashed_password: Optional[str] = Field(default=None, max_length=128)

    # Relationships
    oauth_accounts: list["OAuthAccount"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    refresh_tokens: list["RefreshToken"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


# Avoid circular imports — these are imported for type resolution only
from app.models.oauth_account import OAuthAccount  # noqa: E402, F401
from app.models.refresh_token import RefreshToken  # noqa: E402, F401
