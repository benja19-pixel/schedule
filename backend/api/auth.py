"""
API Auth Module - Versión Mock para Desarrollo
Este archivo reemplaza el auth.py original y usa autenticación simulada
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database.connection import get_db
from models.user import User
from datetime import datetime
import uuid

router = APIRouter()

# ===== MOCK USER =====
def get_current_user(db: Session = Depends(get_db)):
    """
    Obtiene el usuario actual (simulado para desarrollo)
    En producción esto verificaría el JWT token
    """
    # Buscar o crear usuario de prueba
    user = db.query(User).filter(User.email == "demo@mediconnect.com").first()
    
    if not user:
        # Crear usuario si no existe
        # Intentar primero con todos los campos
        try:
            user_data = {
                "email": "demo@mediconnect.com",
                "full_name": "Dr. Demo",
                "plan_type": "premium",
                "is_active": True,
                "is_verified": True
            }
            
            # Agregar el campo de password según cómo se llame en tu modelo
            # Intentar diferentes nombres posibles
            password_field_names = ['password_hash', 'hashed_password', 'password']
            
            # Obtener las columnas del modelo User
            from sqlalchemy import inspect
            mapper = inspect(User)
            columns = [c.key for c in mapper.columns]
            
            # Buscar el campo de password correcto
            for field_name in password_field_names:
                if field_name in columns:
                    user_data[field_name] = "not_used_in_development"
                    break
            
            user = User(**user_data)
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"✅ Usuario de prueba creado: {user.email}")
            
        except Exception as e:
            print(f"⚠️  Error creando usuario: {e}")
            db.rollback()
            
            # Crear con campos mínimos
            user = User(
                email="demo@mediconnect.com",
                full_name="Dr. Demo"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"✅ Usuario de prueba creado (mínimo): {user.email}")
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario de prueba no encontrado"
        )
    
    return user

# ===== ENDPOINTS MOCK =====

@router.post("/login")
async def login():
    """Endpoint de login simulado"""
    return {
        "access_token": "mock-token-development",
        "token_type": "bearer",
        "user": {
            "email": "demo@mediconnect.com",
            "full_name": "Dr. Demo",
            "plan_type": "premium"
        }
    }

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Obtener información del usuario actual"""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "plan_type": getattr(current_user, 'plan_type', 'premium'),
        "is_active": getattr(current_user, 'is_active', True),
        "is_verified": getattr(current_user, 'is_verified', True)
    }

@router.post("/logout")
async def logout():
    """Endpoint de logout simulado"""
    return {"message": "Logged out successfully"}

@router.post("/refresh")
async def refresh_token():
    """Refresh token simulado"""
    return {
        "access_token": "mock-token-refreshed",
        "token_type": "bearer"
    }

# ===== EXPORT =====
# Esto es importante para que otros módulos puedan importar get_current_user
__all__ = ['router', 'get_current_user']