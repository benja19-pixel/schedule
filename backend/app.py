from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from config import settings
from database.connection import engine, Base

# Import original APIs (keeping as backup)
from api import auth, user, subscription, verification, webhooks, patients
# from api import schedule  # COMMENTED - Using new separated APIs

# Import NEW separated APIs
from api import horarios, servicios

# Import NEW Consultorios API
from api import consultorios

# Import NEW Calendar Sync API
from api import external_calendar_sync

# Import models to create tables
from models.patient import Patient, PatientAppointment, MedicalRecord, Payment
from models.horarios import HorarioTemplate, HorarioException
from models.servicios import ServicioMedico
from models.consultorio import Consultorio
from models.calendar_sync import CalendarConnection, SyncedEvent, CalendarSyncLog, CalendarWebhook

import os

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="AI Hallucination Detector - Verify and correct AI-generated content",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with actual domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")
app.mount("/public", StaticFiles(directory="../frontend/public"), name="public")

# Templates
templates = Jinja2Templates(directory="../frontend/templates")

# Include API routers - ORIGINAL (keeping for compatibility)
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(user.router, prefix="/api/user", tags=["User"])
app.include_router(subscription.router, prefix="/api/subscription", tags=["Subscription"])
app.include_router(verification.router, prefix="/api/verification", tags=["Verification"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])
# app.include_router(schedule.router, prefix="/api/schedule", tags=["Schedule"])  # COMMENTED
app.include_router(patients.router, prefix="/api/patients", tags=["Patients"])

# Include NEW SEPARATED API routers
app.include_router(horarios.router, prefix="/api/horarios", tags=["Horarios"])
app.include_router(servicios.router, prefix="/api/servicios", tags=["Servicios Médicos"])

# Include NEW CONSULTORIOS API router
app.include_router(consultorios.router, prefix="/api/consultorios", tags=["Consultorios"])

# Include NEW CALENDAR SYNC API router
app.include_router(external_calendar_sync.router, prefix="/api/calendar-sync", tags=["Calendar Sync"])

# Root endpoint
@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "stripe_publishable_key": settings.stripe_publishable_key,
        "google_client_id": settings.google_client_id
    })

# Dashboard endpoint
@app.get("/dashboard")
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# Login page
@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# Pricing page
@app.get("/pricing")
async def pricing_page(request: Request):
    return templates.TemplateResponse("pricing.html", {
        "request": request,
        "stripe_publishable_key": settings.stripe_publishable_key,
        "google_client_id": settings.google_client_id
    })

# Account page
@app.get("/account")
async def account_page(request: Request):
    return templates.TemplateResponse("account.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# NEW: Mis Consultorios page
@app.get("/mis-consultorios")
async def mis_consultorios_page(request: Request):
    return templates.TemplateResponse("mis-consultorios.html", {
        "request": request,
        "google_client_id": settings.google_client_id,
        "google_maps_api_key": settings.google_maps_api_key  # Pass Google Maps API key
    })

# Configure Schedule page - USES NEW SEPARATED LOGIC
@app.get("/configurar-horario")
async def configurar_horario_page(request: Request):
    return templates.TemplateResponse("configurar-horario.html", {
        "request": request,
        "google_client_id": settings.google_client_id,
        "calendar_sync_enabled": settings.calendar_sync_enabled,  # NEW: Pass feature flag
        "apple_calendar_enabled": settings.FEATURE_APPLE_CALENDAR  # NEW: Pass Apple Calendar flag
    })

# Configure Services page - NEW ROUTE
@app.get("/configurar-servicios")
async def configurar_servicios_page(request: Request):
    return templates.TemplateResponse("configurar-servicios.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# Mi Agenda page
@app.get("/miagenda")
async def miagenda_page(request: Request):
    return templates.TemplateResponse("miagenda.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# Patients page
@app.get("/patients")
async def patients_page(request: Request):
    return templates.TemplateResponse("patients.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# AI Assistant page
@app.get("/ai-assistant")
async def ai_assistant_page(request: Request):
    return templates.TemplateResponse("ai_assistant.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# Smart Notes page
@app.get("/smart-notes")
async def smart_notes_page(request: Request):
    return templates.TemplateResponse("smart_notes.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# Virtual Secretary page
@app.get("/virtual-secretary")
async def virtual_secretary_page(request: Request):
    return templates.TemplateResponse("virtual_secretary.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# Appointments page
@app.get("/appointments")
async def appointments_page(request: Request):
    return templates.TemplateResponse("appointments.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# Settings page
@app.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# Analytics page
@app.get("/analytics")
async def analytics_page(request: Request):
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# Prescriptions page
@app.get("/prescriptions")
async def prescriptions_page(request: Request):
    return templates.TemplateResponse("prescriptions.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# Reports page
@app.get("/reports")
async def reports_page(request: Request):
    return templates.TemplateResponse("reports.html", {
        "request": request,
        "google_client_id": settings.google_client_id
    })

# NEW: Calendar Sync OAuth Callback Handler
@app.get("/calendar-sync-success")
async def calendar_sync_success(request: Request):
    """Success page after calendar connection"""
    return templates.TemplateResponse("calendar_sync_success.html", {
        "request": request,
        "message": "Calendario conectado exitosamente"
    })

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "app": settings.app_name,
        "features": {
            "calendar_sync": settings.calendar_sync_enabled,
            "google_calendar": True,
            "apple_calendar": settings.FEATURE_APPLE_CALENDAR,
            "consultorios": True  # NEW: Add consultorios feature flag
        }
    }

if __name__ == "__main__":
    import uvicorn
    import sys
    
    # Check if --reload flag is passed
    reload = "--reload" in sys.argv
    
    if reload:
        # Con reload pero solo monitoreando tu código
        uvicorn.run(
            "app:app", 
            host="0.0.0.0", 
            port=8000, 
            reload=True,
            reload_dirs=[
                "./api",
                "./core", 
                "./database", 
                "./models", 
                "./services", 
                "./utils"
            ],
            reload_includes=["*.py", "*.html", "*.css", "*.js"],
            reload_excludes=["venv/*", "__pycache__/*", "*.pyc", ".env", ".git/*", "alembic/versions/*"]
        )
    else:
        # Sin reload para desarrollo estable
        uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)