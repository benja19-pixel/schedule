from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict
from datetime import datetime, date, time
import uuid
from database.connection import get_db
from models.user import User
from models.horarios import HorarioTemplate, HorarioException, get_day_name
from models.consultorio import Consultorio
from api.auth import get_current_user
from services.horarios_service import HorariosService
from services.capacidad_service import CapacidadService

router = APIRouter()

# Pydantic models for requests/responses
class TimeBlock(BaseModel):
    start: str  # "09:00"
    end: str    # "14:00"
    type: str   # "consultation", "lunch", "break", etc.
    
    @validator('end')
    def validate_time_order(cls, v, values):
        if 'start' in values and v <= values['start']:
            raise ValueError('El horario de fin debe ser posterior al de inicio')
        return v

class HorarioTemplateRequest(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    is_active: bool = True
    opens_at: Optional[str] = None
    closes_at: Optional[str] = None
    time_blocks: List[TimeBlock] = []
    consultorio_id: Optional[str] = None  # NEW: Consultorio específico para el día
    
    @validator('closes_at')
    def validate_schedule_times(cls, v, values):
        if 'opens_at' in values and values['opens_at'] and v:
            if v <= values['opens_at']:
                raise ValueError('El horario de cierre debe ser posterior al de apertura')
        return v
    
    @validator('time_blocks')
    def validate_time_blocks(cls, v, values):
        if not v:
            return v
            
        opens_at = values.get('opens_at')
        closes_at = values.get('closes_at')
        
        if opens_at and closes_at:
            # Check if blocks are within working hours
            for block in v:
                if block.start < opens_at or block.end > closes_at:
                    raise ValueError(f'El bloque {block.start}-{block.end} está fuera del horario de trabajo')
            
            # Check for overlaps
            for i, block1 in enumerate(v):
                for j, block2 in enumerate(v[i+1:], i+1):
                    if block1.start < block2.end and block1.end > block2.start:
                        raise ValueError(f'Los bloques {block1.start}-{block1.end} y {block2.start}-{block2.end} se superponen')
        
        return v

class BulkHorarioTemplateRequest(BaseModel):
    templates: List[HorarioTemplateRequest]

class HorarioExceptionRequest(BaseModel):
    date: date
    is_working_day: bool = True
    is_special_open: bool = False
    is_vacation: bool = False  # New field for vacation
    vacation_group_id: Optional[str] = None  # Group ID for vacation periods
    opens_at: Optional[str] = None
    closes_at: Optional[str] = None
    time_blocks: List[TimeBlock] = []
    reason: Optional[str] = None
    consultorio_id: Optional[str] = None  # NEW: Consultorio para día especial
    
    @validator('closes_at')
    def validate_exception_times(cls, v, values):
        if values.get('is_working_day') and values.get('opens_at') and v:
            if v <= values['opens_at']:
                raise ValueError('El horario de cierre debe ser posterior al de apertura')
        return v

class HorarioTemplateResponse(BaseModel):
    id: str
    day_of_week: int
    day_name: str
    is_active: bool
    opens_at: Optional[str]
    closes_at: Optional[str]
    time_blocks: List[Dict]
    consultorio_id: Optional[str]  # NEW
    consultorio: Optional[Dict] = None  # NEW: Include consultorio details

class HorarioExceptionResponse(BaseModel):
    id: str
    date: str
    is_working_day: bool
    is_special_open: bool
    is_vacation: bool
    vacation_group_id: Optional[str]
    opens_at: Optional[str]
    closes_at: Optional[str]
    time_blocks: List[Dict]
    reason: Optional[str]
    consultorio_id: Optional[str]  # NEW
    consultorio: Optional[Dict] = None  # NEW: Include consultorio details
    sync_source: Optional[str] = None
    external_calendar_id: Optional[str] = None


# Horario Templates Endpoints
@router.get("/templates")
async def get_horario_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener todos los templates de horario del usuario"""
    templates = db.query(HorarioTemplate).filter(
        HorarioTemplate.user_id == current_user.id
    ).order_by(HorarioTemplate.day_of_week).all()
    
    # Si no existen templates, crear los default
    if not templates:
        for day in range(7):
            is_active = day < 5  # Activo Lunes-Viernes
            template = HorarioTemplate(
                user_id=current_user.id,
                day_of_week=day,
                is_active=is_active,
                opens_at=datetime.strptime("09:00", "%H:%M").time() if is_active else None,
                closes_at=datetime.strptime("19:00", "%H:%M").time() if is_active else None,
                time_blocks=[],
                consultorio_id=None
            )
            db.add(template)
            templates.append(template)
        
        db.commit()
    
    # Build response with consultorio info
    response_templates = []
    for template in templates:
        template_dict = {
            "id": str(template.id),
            "day_of_week": template.day_of_week,
            "day_name": get_day_name(template.day_of_week),
            "is_active": template.is_active,
            "opens_at": template.opens_at.strftime("%H:%M") if template.opens_at else None,
            "closes_at": template.closes_at.strftime("%H:%M") if template.closes_at else None,
            "time_blocks": template.time_blocks or [],
            "consultorio_id": str(template.consultorio_id) if template.consultorio_id else None,
            "consultorio": None
        }
        
        # Add consultorio details if exists
        if template.consultorio_id:
            consultorio = db.query(Consultorio).filter(
                Consultorio.id == template.consultorio_id,
                Consultorio.activo == True
            ).first()
            if consultorio:
                template_dict["consultorio"] = {
                    "id": str(consultorio.id),
                    "nombre": consultorio.nombre,
                    "direccion": consultorio.get_short_address(),
                    "es_principal": consultorio.es_principal
                }
        
        response_templates.append(template_dict)
    
    return {
        "templates": response_templates
    }


@router.post("/templates")
async def create_or_update_horario_template(
    request: HorarioTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear o actualizar template de horario para un día específico"""
    
    # Validate consultorio if provided
    if request.consultorio_id:
        consultorio = db.query(Consultorio).filter(
            Consultorio.id == request.consultorio_id,
            Consultorio.user_id == current_user.id,
            Consultorio.activo == True
        ).first()
        if not consultorio:
            raise HTTPException(status_code=404, detail="Consultorio no encontrado o inactivo")
    
    # Additional validation by service
    service = HorariosService(db)
    
    # Validate time blocks don't overlap and are within schedule
    if request.opens_at and request.closes_at and request.time_blocks:
        is_valid, error_msg = service.validate_horario_times(
            request.opens_at, 
            request.closes_at, 
            [block.dict() for block in request.time_blocks]
        )
        if not is_valid:
            raise HTTPException(status_code=422, detail=error_msg)
    
    # Buscar template existente
    existing = db.query(HorarioTemplate).filter(
        HorarioTemplate.user_id == current_user.id,
        HorarioTemplate.day_of_week == request.day_of_week
    ).first()
    
    if existing:
        # Actualizar existente
        existing.is_active = request.is_active
        existing.opens_at = datetime.strptime(request.opens_at, "%H:%M").time() if request.opens_at else None
        existing.closes_at = datetime.strptime(request.closes_at, "%H:%M").time() if request.closes_at else None
        existing.time_blocks = [block.dict() for block in request.time_blocks]
        existing.consultorio_id = request.consultorio_id
        existing.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(existing)
        return {"message": "Horario actualizado", "template_id": str(existing.id)}
    else:
        # Crear nuevo
        template = HorarioTemplate(
            user_id=current_user.id,
            day_of_week=request.day_of_week,
            is_active=request.is_active,
            opens_at=datetime.strptime(request.opens_at, "%H:%M").time() if request.opens_at else None,
            closes_at=datetime.strptime(request.closes_at, "%H:%M").time() if request.closes_at else None,
            time_blocks=[block.dict() for block in request.time_blocks],
            consultorio_id=request.consultorio_id
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        
        return {"message": "Horario creado", "template_id": str(template.id)}


@router.post("/templates/bulk")
async def bulk_update_templates(
    request: BulkHorarioTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Actualización masiva de templates de horario"""
    updated_count = 0
    created_count = 0
    service = HorariosService(db)
    
    # Validate all consultorios first
    consultorio_ids = set()
    for template_data in request.templates:
        if template_data.consultorio_id:
            consultorio_ids.add(template_data.consultorio_id)
    
    if consultorio_ids:
        valid_consultorios = db.query(Consultorio).filter(
            Consultorio.id.in_(consultorio_ids),
            Consultorio.user_id == current_user.id,
            Consultorio.activo == True
        ).all()
        valid_ids = {str(c.id) for c in valid_consultorios}
        
        for cid in consultorio_ids:
            if cid not in valid_ids:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Consultorio {cid} no encontrado o inactivo"
                )
    
    for template_data in request.templates:
        # Validate each template
        if template_data.opens_at and template_data.closes_at and template_data.time_blocks:
            is_valid, error_msg = service.validate_horario_times(
                template_data.opens_at,
                template_data.closes_at,
                [block.dict() for block in template_data.time_blocks]
            )
            if not is_valid:
                raise HTTPException(
                    status_code=422, 
                    detail=f"Error en día {template_data.day_of_week}: {error_msg}"
                )
        
        existing = db.query(HorarioTemplate).filter(
            HorarioTemplate.user_id == current_user.id,
            HorarioTemplate.day_of_week == template_data.day_of_week
        ).first()
        
        if existing:
            existing.is_active = template_data.is_active
            existing.opens_at = datetime.strptime(template_data.opens_at, "%H:%M").time() if template_data.opens_at else None
            existing.closes_at = datetime.strptime(template_data.closes_at, "%H:%M").time() if template_data.closes_at else None
            existing.time_blocks = [block.dict() for block in template_data.time_blocks]
            existing.consultorio_id = template_data.consultorio_id
            existing.updated_at = datetime.utcnow()
            updated_count += 1
        else:
            template = HorarioTemplate(
                user_id=current_user.id,
                day_of_week=template_data.day_of_week,
                is_active=template_data.is_active,
                opens_at=datetime.strptime(template_data.opens_at, "%H:%M").time() if template_data.opens_at else None,
                closes_at=datetime.strptime(template_data.closes_at, "%H:%M").time() if template_data.closes_at else None,
                time_blocks=[block.dict() for block in template_data.time_blocks],
                consultorio_id=template_data.consultorio_id
            )
            db.add(template)
            created_count += 1
    
    db.commit()
    
    return {
        "message": "Actualización masiva completada",
        "created": created_count,
        "updated": updated_count
    }


# Horario Exceptions Endpoints
@router.get("/exceptions")
async def get_horario_exceptions(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener excepciones de horario en un rango de fechas"""
    query = db.query(HorarioException).filter(
        HorarioException.user_id == current_user.id
    )
    
    if start_date:
        query = query.filter(HorarioException.date >= start_date)
    if end_date:
        query = query.filter(HorarioException.date <= end_date)
    
    exceptions = query.order_by(HorarioException.date).all()
    
    # Build response with consultorio info
    response_exceptions = []
    for exc in exceptions:
        exc_dict = {
            "id": str(exc.id),
            "date": exc.date.isoformat(),
            "is_working_day": exc.is_working_day,
            "is_special_open": getattr(exc, 'is_special_open', False),
            "is_vacation": getattr(exc, 'is_vacation', False),
            "vacation_group_id": str(exc.vacation_group_id) if getattr(exc, 'vacation_group_id', None) else None,
            "opens_at": exc.opens_at.strftime("%H:%M") if exc.opens_at else None,
            "closes_at": exc.closes_at.strftime("%H:%M") if exc.closes_at else None,
            "time_blocks": exc.time_blocks or [],
            "reason": exc.reason,
            "consultorio_id": str(exc.consultorio_id) if exc.consultorio_id else None,
            "consultorio": None,
            "sync_source": exc.sync_source,
            "external_calendar_id": exc.external_calendar_id
        }
        
        # Add consultorio details if exists
        if exc.consultorio_id:
            consultorio = db.query(Consultorio).filter(
                Consultorio.id == exc.consultorio_id,
                Consultorio.activo == True
            ).first()
            if consultorio:
                exc_dict["consultorio"] = {
                    "id": str(consultorio.id),
                    "nombre": consultorio.nombre,
                    "direccion": consultorio.get_short_address(),
                    "es_principal": consultorio.es_principal
                }
        
        response_exceptions.append(exc_dict)
    
    return {
        "exceptions": response_exceptions
    }


@router.post("/exceptions")
async def create_horario_exception(
    request: HorarioExceptionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear excepción de horario con validaciones simplificadas"""
    
    # FIXED: Auto-assign principal consultorio if working day and no consultorio specified
    consultorio_id_to_use = request.consultorio_id
    
    # If it's a working day (special-hours or special-open) and no consultorio specified
    if request.is_working_day and not request.consultorio_id:
        # Get principal consultorio
        principal = Consultorio.get_principal_for_user(db, current_user.id)
        if principal:
            consultorio_id_to_use = str(principal.id)
    
    # Validate consultorio if specified
    if consultorio_id_to_use:
        consultorio = db.query(Consultorio).filter(
            Consultorio.id == consultorio_id_to_use,
            Consultorio.user_id == current_user.id,
            Consultorio.activo == True
        ).first()
        if not consultorio:
            raise HTTPException(status_code=404, detail="Consultorio no encontrado o inactivo")
    
    # Verificar si ya existe excepción para esta fecha
    existing = db.query(HorarioException).filter(
        HorarioException.user_id == current_user.id,
        HorarioException.date == request.date
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail="Ya existe un evento para esta fecha. Elimínalo primero si deseas crear uno nuevo."
        )
    
    # Initialize service for validations
    service = HorariosService(db)
    
    # Validar horarios si es día laboral
    if request.is_working_day and request.opens_at and request.closes_at:
        if request.time_blocks:
            is_valid, error_msg = service.validate_horario_times(
                request.opens_at,
                request.closes_at,
                [block.dict() for block in request.time_blocks]
            )
            if not is_valid:
                raise HTTPException(status_code=422, detail=error_msg)
    
    # Crear nueva excepción
    exception = HorarioException(
        user_id=current_user.id,
        date=request.date,
        is_working_day=request.is_working_day,
        opens_at=datetime.strptime(request.opens_at, "%H:%M").time() if request.opens_at else None,
        closes_at=datetime.strptime(request.closes_at, "%H:%M").time() if request.closes_at else None,
        time_blocks=[block.dict() for block in request.time_blocks],
        reason=request.reason,
        consultorio_id=consultorio_id_to_use  # Use the consultorio_id (either specified or principal)
    )
    
    # Set special fields
    if hasattr(exception, 'is_special_open'):
        exception.is_special_open = request.is_special_open
    
    if hasattr(exception, 'is_vacation'):
        exception.is_vacation = request.is_vacation
        if request.is_vacation and request.vacation_group_id:
            exception.vacation_group_id = request.vacation_group_id
    
    db.add(exception)
    db.commit()
    db.refresh(exception)
    
    return {"message": "Excepción creada", "exception_id": str(exception.id)}


@router.delete("/exceptions/{exception_id}")
async def delete_horario_exception(
    exception_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eliminar excepción de horario"""
    # FIXED: Try to parse the exception_id as UUID first
    try:
        # Validate it's a proper UUID format
        exception_uuid = uuid.UUID(exception_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de excepción inválido")
    
    exception = db.query(HorarioException).filter(
        HorarioException.id == exception_uuid,
        HorarioException.user_id == current_user.id
    ).first()
    
    if not exception:
        raise HTTPException(status_code=404, detail="Excepción no encontrada")
    
    db.delete(exception)
    db.commit()
    
    return {"message": "Excepción eliminada"}


# Capacidad Endpoint
@router.get("/capacidad")
async def get_capacidad_semanal(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener capacidad semanal basada en horarios y servicios"""
    service = CapacidadService(db)
    capacidad = service.calcular_capacidad_semanal(current_user.id)
    
    return capacidad


# FIXED: Get available consultorios without duplicating principal
@router.get("/consultorios-disponibles")
async def get_consultorios_disponibles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener consultorios disponibles para configuración de horarios"""
    consultorios = db.query(Consultorio).filter(
        Consultorio.user_id == current_user.id,
        Consultorio.activo == True
    ).order_by(
        Consultorio.es_principal.desc(),
        Consultorio.nombre
    ).all()
    
    # FIXED: Return all consultorios but mark which one is principal
    # The frontend will handle the display logic to avoid duplication
    return {
        "consultorios": [
            {
                "id": str(c.id),
                "nombre": c.nombre,
                "direccion": c.get_short_address(),
                "es_principal": c.es_principal,
                "foto_principal": c.foto_principal
            }
            for c in consultorios
        ],
        "principal_id": next((str(c.id) for c in consultorios if c.es_principal), None)
    }