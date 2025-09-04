"""
Mock Authentication Module
Simula un usuario autenticado para desarrollo sin necesidad de login real
"""

from typing import Optional
from datetime import datetime
import uuid
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from database.connection import get_db

# ===== USUARIO SIMULADO =====
MOCK_USER = None  # Se llenará dinámicamente desde la BD

def get_or_create_mock_user(db: Session):
    """Obtiene o crea el usuario de prueba en la BD"""
    from models.user import User
    
    global MOCK_USER
    
    # Si ya tenemos el usuario en memoria, retornarlo
    if MOCK_USER:
        # Verificar que sigue existiendo en la BD
        user = db.query(User).filter(User.id == MOCK_USER.id).first()
        if user:
            return user
    
    # Buscar usuario existente por email
    user = db.query(User).filter(User.email == "demo@mediconnect.com").first()
    
    if not user:
        # Crear usuario si no existe
        # IMPORTANTE: Usar solo los campos que existen en tu modelo User
        user = User(
            id=str(uuid.uuid4()),
            email="demo@mediconnect.com",
            full_name="Dr. Demo",
            # NO usar hashed_password si no existe en el modelo
            # hashed_password="not_used_in_development",  # ELIMINADO
            password_hash="not_used_in_development",  # Usar el nombre correcto del campo
            plan_type="premium",
            is_active=True,
            is_verified=True,
            created_at=datetime.utcnow()
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
            print(f"✅ Usuario de prueba creado: {user.email} (ID: {user.id})")
        except Exception as e:
            db.rollback()
            # Si falla la creación, intentar con menos campos
            print(f"⚠️  Error creando usuario con todos los campos: {e}")
            print("Intentando crear usuario con campos mínimos...")
            
            # Crear usuario con campos mínimos
            user = User(
                email="demo@mediconnect.com",
                full_name="Dr. Demo"
            )
            # Establecer otros campos manualmente si existen
            if hasattr(user, 'password_hash'):
                user.password_hash = "not_used"
            if hasattr(user, 'plan_type'):
                user.plan_type = "premium"
            if hasattr(user, 'is_active'):
                user.is_active = True
            if hasattr(user, 'is_verified'):
                user.is_verified = True
                
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"✅ Usuario de prueba creado (mínimo): {user.email} (ID: {user.id})")
    else:
        print(f"✅ Usuario de prueba encontrado: {user.email} (ID: {user.id})")
    
    MOCK_USER = user
    return user

def get_current_user(db: Session = Depends(get_db)):
    """
    Función que simula obtener el usuario actual.
    Esta función reemplaza a la original de api.auth
    """
    user = get_or_create_mock_user(db)
    
    if not user:
        # Esto no debería pasar, pero por si acaso
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario de prueba no encontrado"
        )
    
    return user

# Alias para compatibilidad
mock_get_current_user = get_current_user

def inject_mock_auth(module):
    """
    Inyecta la autenticación simulada en un módulo de API.
    """
    # Guardar referencia al módulo para debuging
    module_name = module.__name__ if hasattr(module, '__name__') else str(module)
    
    # Intentar reemplazar get_current_user si existe
    if hasattr(module, 'get_current_user'):
        module._original_get_current_user = module.get_current_user
        module.get_current_user = get_current_user
        print(f"✅ Mock auth inyectado en {module_name}")
        return True
    
    # Si no tiene get_current_user, intentar agregarlo
    try:
        setattr(module, 'get_current_user', get_current_user)
        print(f"✅ Mock auth agregado a {module_name}")
        return True
    except Exception as e:
        print(f"⚠️  No se pudo inyectar mock auth en {module_name}: {e}")
        return False

def setup_mock_auth_globally():
    """
    Configura el mock auth globalmente para todas las APIs
    """
    import sys
    
    # Crear un módulo fake de api.auth si no existe
    if 'api.auth' not in sys.modules:
        import types
        auth_module = types.ModuleType('api.auth')
        auth_module.get_current_user = get_current_user
        sys.modules['api.auth'] = auth_module
        print("✅ Módulo api.auth simulado creado")
    else:
        # Si ya existe, reemplazar get_current_user
        sys.modules['api.auth'].get_current_user = get_current_user
        print("✅ api.auth.get_current_user reemplazado")
    
    # También reemplazar en el módulo real si está cargado
    try:
        from api import auth as real_auth
        if hasattr(real_auth, 'get_current_user'):
            real_auth.get_current_user = get_current_user
            print("✅ api.auth real reemplazado")
    except ImportError:
        pass
    
    return True

# ===== FUNCIONES DE UTILIDAD =====

def get_mock_user_id():
    """Obtiene el ID del usuario mock actual"""
    if MOCK_USER and hasattr(MOCK_USER, 'id'):
        return MOCK_USER.id
    
    # Si no hay usuario, intentar obtenerlo de la BD
    from database.connection import SessionLocal
    db = SessionLocal()
    try:
        user = get_or_create_mock_user(db)
        return user.id if user else None
    finally:
        db.close()

def reset_mock_user():
    """Resetea el usuario mock (útil para testing)"""
    global MOCK_USER
    MOCK_USER = None
    print("🔄 Usuario mock reseteado")

# ===== DECORADOR OPCIONAL =====
def requires_mock_auth(func):
    """
    Decorador que se puede usar en funciones que requieren autenticación.
    """
    def wrapper(*args, **kwargs):
        from database.connection import SessionLocal
        db = SessionLocal()
        try:
            user = get_or_create_mock_user(db)
            return func(*args, current_user=user, **kwargs)
        finally:
            db.close()
    return wrapper

# ===== INFORMACIÓN DE DEBUG =====
def print_mock_auth_info():
    """Imprime información sobre la autenticación mock"""
    print("\n" + "="*50)
    print("  MOCK AUTHENTICATION ACTIVE")
    print("="*50)
    print(f"  Usuario: Dr. Demo")
    print(f"  Email: demo@mediconnect.com")
    print(f"  Plan: premium")
    print(f"  ID: {MOCK_USER.id if MOCK_USER else 'Pendiente de crear'}")
    print("="*50 + "\n")

# ===== AUTO-SETUP AL IMPORTAR =====
# Configurar mock auth globalmente cuando se importa este módulo
if __name__ != "__main__":
    setup_mock_auth_globally()
    print_mock_auth_info()