from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    username : str
    email    : EmailStr
    password : str


class UserResponse(BaseModel):
    user_id    : str
    username   : str
    email      : str
    role       : str
    is_active  : bool
    is_approved        : bool
    email_otp_verified : bool
    created_at : datetime

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username : str
    password : str


class TokenResponse(BaseModel):
    access_token : str
    token_type   : str = "bearer"
