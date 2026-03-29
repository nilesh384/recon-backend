import datetime
import uuid

from app.models.user import UserBase


class UserProfile(UserBase):
    id: uuid.UUID
    created_at: datetime.datetime
