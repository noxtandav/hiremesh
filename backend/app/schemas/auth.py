from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Role = Literal["admin", "recruiter", "client"]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    role: Role
    must_change_password: bool
    is_active: bool
    # Set when role='client'; null otherwise.
    client_id: int | None = None

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)
    role: Role = "recruiter"
    # Required when role='client'; rejected for admin/recruiter.
    client_id: int | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=255)


class UpdateUserRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: Role | None = None
    is_active: bool | None = None
    # Set/clear with role changes; validation runs in the endpoint.
    client_id: int | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=255)
