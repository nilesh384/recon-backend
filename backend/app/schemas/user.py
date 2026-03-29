import datetime
import uuid

from pydantic import EmailStr
from sqlmodel import SQLModel

from app.models.user import UserBase


class UserCreate(UserBase):
    email: EmailStr
    password: str


class UserRead(UserBase):
    id: uuid.UUID
    created_at: datetime.datetime


class UserUpdate(SQLModel):
    email: EmailStr | None = None
    username: str | None = None
    password: str | None = None
    is_active: bool | None = None
