import datetime
import uuid

from app.models.user import UserBase
from app.schemas.user import RoleRead


class UserProfile(UserBase):
    id: uuid.UUID
    created_at: datetime.datetime
    role: RoleRead | None = None
