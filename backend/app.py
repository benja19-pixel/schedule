from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from config import settings
from database.connection import engine, Base

# ===== IMPORTS DE APIS NECESARIAS =====
# Solo las APIs que necesitamos para las páginas funcionales
from api import patients  # Gestión de pacientes
from api import horarios  # Configuración de horarios
from api import servicios  # Servicios médicos
from api import consultorios  # Gestión de consultorios
from api import external_calendar_sync  # Sincronización de calendarios

# ===== IMPORTS COMENTADOS (Referencias para el freelancer) =====
# Estas APIs no se usan pero se mantienen como referencia
# from api import auth  # DESHABILITADO - No necesario para desarrollo
# from api import user  # DESHABILITADO - Usuario simulado
# from api import subscription  # DESHABILITADO - No necesario
# from api import verification  # DESHABILITADO - No necesario
# from api import webhooks  # DESHABILITADO - No necesario

# Mock auth para simular usuario autenticado
from mock_auth import mock_get_current_user, inject_mock_auth

# ===== IMPORTAR MODELOS NECESARIOS =====
# Solo los modelos que usamos en las páginas funcionales
from models.patient import Patient, PatientAppointment, MedicalRecord, Payment
from models.horarios import HorarioTemplate, HorarioException
from models.servicios import ServicioMedico
from models.consultorio import Consultorio
from models.calendar_sync import CalendarConnection, SyncedEvent, CalendarSyncLog, CalendarWebhook

import os

# Crear tablas en la base de datos
Base.metadata.create_all(bind=engine)

# ===== INICIALIZAR FASTAPI =====
app = FastAPI(
    title=settings.app_name,
    description="MediConnect - Sistema de Gestión Médica (Versión Desarrollo)",
    version="1.0.0-dev"
)

# ===== CONFIGURAR CORS =====
# Permitir todo en desarrollo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios exactos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== MONTAR ARCHIVOS ESTÁTICOS =====
app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")
app.mount("/public", StaticFiles(directory="../frontend/public"), name="public")

# Templates
templates = Jinja2Templates(directory="../frontend/templates")

# ===== INYECTAR MOCK AUTH EN LAS APIS =====
# Esto hace que todas las rutas usen el usuario simulado
inject_mock_auth(patients)
inject_mock_auth(horarios)
inject_mock_auth(servicios)
inject_mock_auth(consultorios)
inject_mock_auth(external_calendar_sync)

# ===== INCLUIR ROUTERS DE API =====
# Solo las APIs necesarias para las páginas funcionales

# APIs principales
app.include_router(patients.router, prefix="/api/patients", tags=["Patients"])
app.include_router(horarios.router, prefix="/api/horarios", tags=["Horarios"])
app.include_router(servicios.router, prefix="/api/servicios", tags=["Servicios Médicos"])
app.include_router(consultorios.router, prefix="/api/consultorios", tags=["Consultorios"])
app.include_router(external_calendar_sync.router, prefix="/api/calendar-sync", tags=["Calendar Sync"])

# ===== RUTAS COMENTADAS (Referencias) =====
# Estas rutas están deshabilitadas pero se mantienen como referencia
# app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
# app.include_router(user.router, prefix="/api/user", tags=["User"])
# app.include_router(subscription.router, prefix="/api/subscription", tags=["Subscription"])
# app.include_router(verification.router, prefix="/api/verification", tags=["Verification"])
# app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])

# ===== ENDPOINT RAÍZ - REDIRIGE AL DASHBOARD =====
@app.get("/")
async def root(request: Request):
    """Redirigir al dashboard principal"""
    return templates.TemplateResponse("dashboard_simple.html", {
        "request": request,
        "user_name": "Dr. Demo",  # Usuario simulado
        "stripe_publishable_key": "",  # No necesario en dev
        "google_client_id": settings.google_client_id or ""
    })

# ===== DASHBOARD SIMPLIFICADO =====
@app.get("/dashboard")
async def dashboard(request: Request):
    """Dashboard con enlaces a las páginas funcionales"""
    return templates.TemplateResponse("dashboard_simple.html", {
        "request": request,
        "user_name": "Dr. Demo",
        "google_client_id": settings.google_client_id or ""
    })

# ===== PÁGINAS FUNCIONALES =====

# Pacientes
@app.get("/patients")
async def patients_page(request: Request):
    """Página de gestión de pacientes"""
    return templates.TemplateResponse("patients.html", {
        "request": request,
        "google_client_id": settings.google_client_id or ""
    })

# Mi Agenda
@app.get("/miagenda")
async def miagenda_page(request: Request):
    """Página de agenda/calendario"""
    return templates.TemplateResponse("miagenda.html", {
        "request": request,
        "google_client_id": settings.google_client_id or ""
    })

# Configurar Horario
@app.get("/configurar-horario")
async def configurar_horario_page(request: Request):
    """Página de configuración de horarios"""
    return templates.TemplateResponse("configurar-horario.html", {
        "request": request,
        "google_client_id": settings.google_client_id or "",
        "calendar_sync_enabled": settings.calendar_sync_enabled,
        "apple_calendar_enabled": settings.FEATURE_APPLE_CALENDAR
    })

# Configurar Servicios
@app.get("/configurar-servicios")
async def configurar_servicios_page(request: Request):
    """Página de configuración de servicios médicos"""
    return templates.TemplateResponse("configurar-servicios.html", {
        "request": request,
        "google_client_id": settings.google_client_id or ""
    })

# Mis Consultorios
@app.get("/mis-consultorios")
async def mis_consultorios_page(request: Request):
    """Página de gestión de consultorios/sedes"""
    return templates.TemplateResponse("mis-consultorios.html", {
        "request": request,
        "google_client_id": settings.google_client_id or "",
        "google_maps_api_key": settings.google_maps_api_key or ""
    })

# ===== PÁGINAS NO FUNCIONALES (Referencias) =====
# Estas páginas están deshabilitadas pero se mantienen como referencia

# @app.get("/login")
# async def login_page(request: Request):
#     """DESHABILITADO - No necesario en desarrollo"""
#     return {"message": "Login deshabilitado - Usuario simulado activo"}

# @app.get("/pricing")
# async def pricing_page(request: Request):
#     """DESHABILITADO - No necesario en desarrollo"""
#     return {"message": "Pricing deshabilitado - Plan Premium simulado"}

# @app.get("/account")
# async def account_page(request: Request):
#     """DESHABILITADO - Cuenta simulada"""
#     return {"message": "Cuenta: Dr. Demo (demo@mediconnect.com)"}

# ===== CALENDARIO - SUCCESS CALLBACK =====
@app.get("/calendar-sync-success")
async def calendar_sync_success(request: Request):
    """Página de éxito después de conectar calendario"""
    return templates.TemplateResponse("calendar_sync_success.html", {
        "request": request,
        "message": "Calendario conectado exitosamente"
    })

# ===== HEALTH CHECK =====
@app.get("/health")
async def health_check():
    """Verificar que la aplicación está funcionando"""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "environment": "development",
        "features": {
            "calendar_sync": settings.calendar_sync_enabled,
            "google_calendar": True,
            "apple_calendar": settings.FEATURE_APPLE_CALENDAR,
            "consultorios": True,
            "mock_auth": True,  # Indicador de que estamos usando autenticación simulada
            "user": "Dr. Demo (demo@mediconnect.com)"
        }
    }

# ===== ENDPOINT ESPECIAL PARA EL FREELANCER =====
@app.get("/api/dev-info")
async def dev_info():
    """Información útil para el desarrollador"""
    return {
        "message": "Información de desarrollo",
        "mock_user": {
            "id": "usuario-demo-id",
            "email": "demo@mediconnect.com",
            "name": "Dr. Demo",
            "plan": "premium"
        },
        "functional_pages": [
            "/patients - Gestión de pacientes",
            "/miagenda - Calendario de citas",
            "/configurar-horario - Configuración de horarios",
            "/configurar-servicios - Servicios médicos",
            "/mis-consultorios - Gestión de consultorios"
        ],
        "api_endpoints": [
            "/api/patients - CRUD de pacientes",
            "/api/horarios - Gestión de horarios",
            "/api/servicios - Servicios médicos",
            "/api/consultorios - Consultorios",
            "/api/calendar-sync - Sincronización de calendarios"
        ],
        "notes": [
            "La autenticación está simulada - todas las operaciones usan el usuario Dr. Demo",
            "La base de datos es PostgreSQL local (mediconnect_dev)",
            "Las API keys de Google están deshabilitadas por defecto",
            "Revisa mock_auth.py para entender cómo se simula el usuario"
        ]
    }

# ===== MOCK AUTH ENDPOINT =====
@app.get("/api/auth/me")
async def get_current_user_info():
    """Endpoint simulado para obtener información del usuario actual"""
    return {
        "id": "usuario-demo-id",
        "email": "demo@mediconnect.com",
        "full_name": "Demo",
        "plan_type": "premium",
        "is_active": True,
        "is_verified": True
    }

# ===== MAIN - EJECUTAR APLICACIÓN =====
if __name__ == "__main__":
    import uvicorn
    import sys
    
    print("\n" + "="*50)
    print("  MediConnect - Modo Desarrollo")
    print("="*50)
    print("\n📌 Usuario simulado activo: Dr. Demo")
    print("📌 Email: demo@mediconnect.com")
    print("📌 Plan: Premium (todas las funciones habilitadas)")
    print("\n🔗 Páginas disponibles:")
    print("  • http://localhost:8000/patients")
    print("  • http://localhost:8000/miagenda")
    print("  • http://localhost:8000/configurar-horario")
    print("  • http://localhost:8000/configurar-servicios")
    print("  • http://localhost:8000/mis-consultorios")
    print("\n⚙️  Iniciando servidor...")
    print("-"*50 + "\n")
    
    # Verificar si se pasó --reload
    reload = "--reload" in sys.argv
    
    if reload:
        # Con reload para desarrollo activo
        uvicorn.run(
            "app:app", 
            host="0.0.0.0", 
            port=8000, 
            reload=True,
            reload_dirs=[
                "./api",
                "./models", 
                "./services", 
                "./database"
            ]
        )
    else:
        # Sin reload para desarrollo estable
        uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)