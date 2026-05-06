# models/user.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserRegister(BaseModel):
    nombre_completo: str
    email: str  # ← Cambiado de EmailStr a str
    password: str

class UserLogin(BaseModel):
    email: str  # ← Cambiado de EmailStr a str
    password: str

class UserResponse(BaseModel):
    id: int
    nombre_completo: str
    email: str
    created_at: Optional[datetime] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse