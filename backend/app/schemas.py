from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    created_at: datetime


class RegisterIn(BaseModel):
    email: EmailStr
    # Length + character-class rules enforced in security.validate_password so
    # all rejections share a single fixed error message. max_length here is
    # purely a DoS guard.
    password: str = Field(min_length=1, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TodoBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    due_at: datetime | None = None


class TodoCreate(TodoBase):
    pass


class TodoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    completed: bool | None = None
    due_at: datetime | None = None
    # Explicit flag so a client can clear due_at without ambiguity with "not provided".
    clear_due_at: bool = False


class TodoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    completed: bool
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    todo_id: UUID
    due_at_snapshot: datetime
    message: str
    created_at: datetime
    read_at: datetime | None
