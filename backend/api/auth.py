"""
Mock Auth API Module
Este archivo simula el módulo de autenticación que las APIs esperan encontrar.
En producción, este archivo contendría la lógica real de autenticación con JWT.
En desarrollo, simplemente retorna el usuario de prueba.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database.connection import get_db
from datetime import datetime
import uuid

router = APIRouter()

# ===== MOCK USER FUNCTION =====
def get_current_user(db: Session = Depends(get_db)):
    """
    Función que retorna el usuario actual.
    En desarrollo, siempre retorna el usuario de prueba.
    """
    from models.user import User
    
    # Buscar el usuario de prueba
    user = db.query(User).filter(User.email == "demo@mediconnect.com").first()
    
    if not user:
        # Crear el usuario si no existe
        user = User(
            id=str(uuid.uuid4()),
            email="demo@mediconnect.com",
            full_name="Dr. Demo",
            hashed_password="not_used",
            plan_type="premium",
            is_active=True,
            is_verified=True,
            created_at=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"✅ Usuario de prueba creado en auth.py: {user.id}")
    
    return user

# ===== MOCK ENDPOINTS =====
@router.get("/me")
async def read_users_me(current_user = Depends(get_current_user)):
    """Retorna el usuario actual (siempre el de prueba)"""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "plan_type": current_user.plan_type,
        "is_active": current_user.is_active,
        "is_verified": current_user.is_verified
    }

@router.post("/login")
async def mock_login():
    """Login simulado - siempre exitoso"""
    return {
        "access_token": "mock-token-desarrollo",
        "token_type": "bearer",
        "message": "Login simulado exitoso"
    }

@router.post("/logout")
async def mock_logout():
    """Logout simulado"""
    return {"message": "Logout simulado"}

# ===== EXPORTS =====
__all__ = ['get_current_user', 'router']