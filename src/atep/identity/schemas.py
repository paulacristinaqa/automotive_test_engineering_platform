from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int


class RefreshTokenCommand(BaseModel):
    refresh_token: SecretStr = Field(min_length=32, max_length=512)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str
    is_active: bool
    roles: list[str]
    permissions: list[str]


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: SecretStr = Field(min_length=12, max_length=256)


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserPage(BaseModel):
    items: list[UserResponse]
    total: int
    limit: int
    offset: int
