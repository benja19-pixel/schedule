from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date, time, timedelta
import uuid
from database.connection import get_db
from models.user import User
from models.schedule import (
    ScheduleTemplate, ScheduleException, AppointmentType, 
    Appointment, ScheduleSettings, DayOfWeek, BlockType,
    is_time_available, get_day_name, get_appointment_color
)
from api.auth import get_current_user
from services.schedule_service import ScheduleService
import json

router = APIRouter()

# Pydantic models for requests/responses
class TimeBlock(BaseModel):
    start: str  # "09:00"
    end: str    # "14:00"
    type: str   # "consultation", "lunch", etc.

class ScheduleTemplateRequest(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    is_active: bool = True
    opens_at: Optional[str] = None
    closes_at: Optional[str] = None
    default_duration: int = 30
    buffer_time: int = 0
    time_blocks: List[TimeBlock] = []

class BulkScheduleTemplateRequest(BaseModel):
    templates: List[ScheduleTemplateRequest]

class ScheduleExceptionRequest(BaseModel):
    date: date
    is_working_day: bool = True
    opens_at: Optional[str] = None
    closes_at: Optional[str] = None
    time_blocks: List[TimeBlock] = []
    reason: Optional[str] = None

class AppointmentTypeRequest(BaseModel):
    name: str
    duration: int
    color: str = "#3B82F6"
    suggested_price: Optional[int] = None
    requires_preparation: bool = False
    preparation_time: int = 0
    display_order: Optional[int] = None

class AppointmentTypeUpdateRequest(BaseModel):
    name: Optional[str] = None
    duration: Optional[int] = None
    color: Optional[str] = None
    suggested_price: Optional[int] = None
    requires_preparation: Optional[bool] = None
    preparation_time: Optional[int] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None

class AppointmentRequest(BaseModel):
    patient_name: str
    patient_phone: str
    patient_email: Optional[str] = None
    appointment_date: date
    start_time: str
    appointment_type_id: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    source: str = "manual"
    
    @validator('start_time')
    def validate_time_format(cls, v):
        try:
            datetime.strptime(v, "%H:%M")
            return v
        except ValueError:
            raise ValueError('Time must be in HH:MM format')

class RescheduleAppointmentRequest(BaseModel):
    appointment_date: date
    start_time: str
    notify_patient: bool = True
    reschedule_reason: Optional[str] = None

class AppointmentStatusRequest(BaseModel):
    status: str
    reason: Optional[str] = None

class ScheduleSettingsRequest(BaseModel):
    timezone: str = "America/Mexico_City"
    default_duration: int = 30
    buffer_time: int = 0
    min_advance_booking: int = 60
    max_advance_booking: int = 30
    auto_confirm: bool = True
    confirmation_hours_before: int = 24
    allow_patient_cancellation: bool = True
    cancellation_hours_limit: int = 24
    max_patients_per_day: int = 20
    waiting_list: bool = False
    allow_overbooking: bool = False
    max_overbooking_per_day: int = 0
    sync_google_calendar: bool = False
    google_calendar_id: Optional[str] = None
    confirmation_message: Optional[str] = None
    reminder_message: Optional[str] = None
    # AI Settings
    enable_ai_secretary: bool = False
    ai_can_schedule: bool = True
    ai_can_reschedule: bool = True
    ai_can_cancel: bool = False
    ai_requires_confirmation: bool = True

class EmergencyClosureRequest(BaseModel):
    date: date
    reason: str
    message: Optional[str] = None
    reschedule_appointments: bool = True

class AIScheduleRequest(BaseModel):
    """Request from AI Secretary to schedule appointment"""
    patient_name: str
    patient_phone: str
    preferred_dates: List[date]
    preferred_times: List[str]  # ["morning", "afternoon", "evening", "specific:14:00"]
    appointment_type: Optional[str] = None
    reason: Optional[str] = None
    whatsapp_session_id: str
    ai_confidence_score: int = Field(..., ge=0, le=100)

class TimeSlotResponse(BaseModel):
    start_time: str
    end_time: str
    available: bool
    appointment_type_fits: List[str]  # Which appointment types fit in this slot

# Schedule Template Endpoints
@router.get("/templates")
async def get_schedule_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all schedule templates for the current user"""
    templates = db.query(ScheduleTemplate).filter(
        ScheduleTemplate.user_id == current_user.id
    ).order_by(ScheduleTemplate.day_of_week).all()
    
    # If no templates exist, create default ones
    if not templates:
        # Create default templates for Monday-Friday (9 AM - 7 PM)
        for day in range(7):  # 0-6 for all days
            is_active = day < 5  # Active Monday-Friday (0-4)
            template = ScheduleTemplate(
                user_id=current_user.id,
                day_of_week=day,
                is_active=is_active,
                opens_at=datetime.strptime("09:00", "%H:%M").time() if is_active else None,
                closes_at=datetime.strptime("19:00", "%H:%M").time() if is_active else None,
                default_duration=30,
                buffer_time=0,
                time_blocks=[]
            )
            db.add(template)
            templates.append(template)
        
        db.commit()
    
    return {
        "templates": [
            {
                "id": str(template.id),
                "day_of_week": template.day_of_week,
                "day_name": get_day_name(template.day_of_week),
                "is_active": template.is_active,
                "opens_at": template.opens_at.strftime("%H:%M") if template.opens_at else None,
                "closes_at": template.closes_at.strftime("%H:%M") if template.closes_at else None,
                "default_duration": template.default_duration,
                "buffer_time": template.buffer_time,
                "time_blocks": template.time_blocks or []
            }
            for template in templates
        ]
    }

@router.post("/templates")
async def create_schedule_template(
    request: ScheduleTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create or update a schedule template for a specific day"""
    
    # Check if template already exists for this day
    existing = db.query(ScheduleTemplate).filter(
        ScheduleTemplate.user_id == current_user.id,
        ScheduleTemplate.day_of_week == request.day_of_week
    ).first()
    
    if existing:
        # Update existing template
        existing.is_active = request.is_active
        existing.opens_at = datetime.strptime(request.opens_at, "%H:%M").time() if request.opens_at else None
        existing.closes_at = datetime.strptime(request.closes_at, "%H:%M").time() if request.closes_at else None
        existing.default_duration = request.default_duration
        existing.buffer_time = request.buffer_time
        existing.time_blocks = [block.dict() for block in request.time_blocks]
        existing.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(existing)
        return {"message": "Schedule template updated", "template_id": str(existing.id)}
    else:
        # Create new template
        template = ScheduleTemplate(
            user_id=current_user.id,
            day_of_week=request.day_of_week,
            is_active=request.is_active,
            opens_at=datetime.strptime(request.opens_at, "%H:%M").time() if request.opens_at else None,
            closes_at=datetime.strptime(request.closes_at, "%H:%M").time() if request.closes_at else None,
            default_duration=request.default_duration,
            buffer_time=request.buffer_time,
            time_blocks=[block.dict() for block in request.time_blocks]
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        
        return {"message": "Schedule template created", "template_id": str(template.id)}

@router.post("/templates/bulk")
async def bulk_update_templates(
    request: BulkScheduleTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk update schedule templates"""
    updated_count = 0
    created_count = 0
    
    for template_data in request.templates:
        existing = db.query(ScheduleTemplate).filter(
            ScheduleTemplate.user_id == current_user.id,
            ScheduleTemplate.day_of_week == template_data.day_of_week
        ).first()
        
        if existing:
            existing.is_active = template_data.is_active
            existing.opens_at = datetime.strptime(template_data.opens_at, "%H:%M").time() if template_data.opens_at else None
            existing.closes_at = datetime.strptime(template_data.closes_at, "%H:%M").time() if template_data.closes_at else None
            existing.default_duration = template_data.default_duration
            existing.buffer_time = template_data.buffer_time
            existing.time_blocks = [block.dict() for block in template_data.time_blocks]
            existing.updated_at = datetime.utcnow()
            updated_count += 1
        else:
            template = ScheduleTemplate(
                user_id=current_user.id,
                day_of_week=template_data.day_of_week,
                is_active=template_data.is_active,
                opens_at=datetime.strptime(template_data.opens_at, "%H:%M").time() if template_data.opens_at else None,
                closes_at=datetime.strptime(template_data.closes_at, "%H:%M").time() if template_data.closes_at else None,
                default_duration=template_data.default_duration,
                buffer_time=template_data.buffer_time,
                time_blocks=[block.dict() for block in template_data.time_blocks]
            )
            db.add(template)
            created_count += 1
    
    db.commit()
    
    return {
        "message": "Bulk update completed",
        "created": created_count,
        "updated": updated_count
    }

@router.delete("/templates/{day_of_week}")
async def delete_schedule_template(
    day_of_week: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a schedule template"""
    template = db.query(ScheduleTemplate).filter(
        ScheduleTemplate.user_id == current_user.id,
        ScheduleTemplate.day_of_week == day_of_week
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Schedule template not found")
    
    db.delete(template)
    db.commit()
    
    return {"message": "Schedule template deleted"}

# Schedule Exception Endpoints
@router.get("/exceptions")
async def get_schedule_exceptions(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get schedule exceptions for a date range"""
    query = db.query(ScheduleException).filter(
        ScheduleException.user_id == current_user.id
    )
    
    if start_date:
        query = query.filter(ScheduleException.date >= start_date)
    if end_date:
        query = query.filter(ScheduleException.date <= end_date)
    
    exceptions = query.order_by(ScheduleException.date).all()
    
    return {
        "exceptions": [
            {
                "id": str(exc.id),
                "date": exc.date.isoformat(),
                "is_working_day": exc.is_working_day,
                "opens_at": exc.opens_at.strftime("%H:%M") if exc.opens_at else None,
                "closes_at": exc.closes_at.strftime("%H:%M") if exc.closes_at else None,
                "time_blocks": exc.time_blocks or [],
                "reason": exc.reason
            }
            for exc in exceptions
        ]
    }

@router.post("/exceptions")
async def create_schedule_exception(
    request: ScheduleExceptionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create or update a schedule exception for a specific date"""
    
    # Check if exception already exists for this date
    existing = db.query(ScheduleException).filter(
        ScheduleException.user_id == current_user.id,
        ScheduleException.date == request.date
    ).first()
    
    if existing:
        # Update existing exception
        existing.is_working_day = request.is_working_day
        existing.opens_at = datetime.strptime(request.opens_at, "%H:%M").time() if request.opens_at else None
        existing.closes_at = datetime.strptime(request.closes_at, "%H:%M").time() if request.closes_at else None
        existing.time_blocks = [block.dict() for block in request.time_blocks]
        existing.reason = request.reason
        existing.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(existing)
        return {"message": "Schedule exception updated", "exception_id": str(existing.id)}
    else:
        # Create new exception
        exception = ScheduleException(
            user_id=current_user.id,
            date=request.date,
            is_working_day=request.is_working_day,
            opens_at=datetime.strptime(request.opens_at, "%H:%M").time() if request.opens_at else None,
            closes_at=datetime.strptime(request.closes_at, "%H:%M").time() if request.closes_at else None,
            time_blocks=[block.dict() for block in request.time_blocks],
            reason=request.reason
        )
        
        db.add(exception)
        db.commit()
        db.refresh(exception)
        
        return {"message": "Schedule exception created", "exception_id": str(exception.id)}

@router.delete("/exceptions/{exception_id}")
async def delete_schedule_exception(
    exception_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a schedule exception"""
    exception = db.query(ScheduleException).filter(
        ScheduleException.id == exception_id,
        ScheduleException.user_id == current_user.id
    ).first()
    
    if not exception:
        raise HTTPException(status_code=404, detail="Schedule exception not found")
    
    db.delete(exception)
    db.commit()
    
    return {"message": "Schedule exception deleted"}

# Appointment Type Endpoints
@router.get("/appointment-types")
async def get_appointment_types(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all appointment types for the current user"""
    types = db.query(AppointmentType).filter(
        AppointmentType.user_id == current_user.id,
        AppointmentType.is_active == True
    ).order_by(AppointmentType.display_order, AppointmentType.created_at).all()
    
    # CHANGED: Create only ONE default type if none exist
    if not types:
        # Create only "Consulta inicial" with 60 minutes duration
        appointment_type = AppointmentType(
            user_id=current_user.id,
            name="Consulta inicial",
            duration=60,
            color="#9333ea",
            display_order=0
        )
        db.add(appointment_type)
        types.append(appointment_type)
        db.commit()
    
    return {
        "appointment_types": [
            {
                "id": str(type.id),
                "name": type.name,
                "duration": type.duration,
                "color": type.color,
                "suggested_price": type.suggested_price,
                "requires_preparation": type.requires_preparation,
                "preparation_time": type.preparation_time,
                "display_order": type.display_order if hasattr(type, 'display_order') else i
            }
            for i, type in enumerate(types)
        ]
    }

@router.post("/appointment-types")
async def create_appointment_type(
    request: AppointmentTypeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new appointment type"""
    
    # Get max display order
    max_order = db.query(func.max(AppointmentType.display_order)).filter(
        AppointmentType.user_id == current_user.id
    ).scalar() or 0
    
    appointment_type = AppointmentType(
        user_id=current_user.id,
        name=request.name,
        duration=request.duration,
        color=request.color,
        suggested_price=request.suggested_price,
        requires_preparation=request.requires_preparation,
        preparation_time=request.preparation_time,
        display_order=request.display_order if request.display_order is not None else max_order + 1
    )
    
    db.add(appointment_type)
    db.commit()
    db.refresh(appointment_type)
    
    return {
        "message": "Appointment type created",
        "appointment_type": {
            "id": str(appointment_type.id),
            "name": appointment_type.name,
            "duration": appointment_type.duration,
            "color": appointment_type.color,
            "display_order": appointment_type.display_order
        }
    }

@router.put("/appointment-types/{type_id}")
async def update_appointment_type(
    type_id: str,
    request: AppointmentTypeUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing appointment type"""
    appointment_type = db.query(AppointmentType).filter(
        AppointmentType.id == type_id,
        AppointmentType.user_id == current_user.id
    ).first()
    
    if not appointment_type:
        raise HTTPException(status_code=404, detail="Appointment type not found")
    
    # Update only provided fields
    if request.name is not None:
        appointment_type.name = request.name
    if request.duration is not None:
        appointment_type.duration = request.duration
    if request.color is not None:
        appointment_type.color = request.color
    if request.suggested_price is not None:
        appointment_type.suggested_price = request.suggested_price
    if request.requires_preparation is not None:
        appointment_type.requires_preparation = request.requires_preparation
    if request.preparation_time is not None:
        appointment_type.preparation_time = request.preparation_time
    if request.display_order is not None:
        appointment_type.display_order = request.display_order
    if request.is_active is not None:
        appointment_type.is_active = request.is_active
    
    appointment_type.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(appointment_type)
    
    return {
        "message": "Appointment type updated",
        "appointment_type": {
            "id": str(appointment_type.id),
            "name": appointment_type.name,
            "duration": appointment_type.duration,
            "color": appointment_type.color,
            "display_order": appointment_type.display_order
        }
    }

@router.delete("/appointment-types/{type_id}")
async def delete_appointment_type(
    type_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an appointment type"""
    appointment_type = db.query(AppointmentType).filter(
        AppointmentType.id == type_id,
        AppointmentType.user_id == current_user.id
    ).first()
    
    if not appointment_type:
        raise HTTPException(status_code=404, detail="Appointment type not found")
    
    # CHANGED: Check if this is the last appointment type
    active_types_count = db.query(func.count(AppointmentType.id)).filter(
        AppointmentType.user_id == current_user.id,
        AppointmentType.is_active == True
    ).scalar()
    
    if active_types_count <= 1:
        raise HTTPException(
            status_code=400,
            detail="No puedes eliminar el último tipo de consulta. Debe existir al menos uno."
        )
    
    # Check if there are appointments using this type
    appointments_count = db.query(func.count(Appointment.id)).filter(
        Appointment.appointment_type_id == type_id
    ).scalar()
    
    if appointments_count > 0:
        # Soft delete - just mark as inactive
        appointment_type.is_active = False
        db.commit()
        return {"message": "Appointment type deactivated (has existing appointments)"}
    else:
        # Hard delete if no appointments
        db.delete(appointment_type)
        db.commit()
        return {"message": "Appointment type deleted"}

# Appointment Endpoints
@router.get("/appointments")
async def get_appointments(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get appointments for a date range"""
    query = db.query(Appointment).filter(
        Appointment.user_id == current_user.id
    )
    
    if start_date:
        query = query.filter(Appointment.appointment_date >= start_date)
    if end_date:
        query = query.filter(Appointment.appointment_date <= end_date)
    if status:
        query = query.filter(Appointment.status == status)
    
    appointments = query.order_by(
        Appointment.appointment_date,
        Appointment.start_time
    ).all()
    
    return {
        "appointments": [
            {
                "id": str(apt.id),
                "patient_name": apt.patient_name,
                "patient_phone": apt.patient_phone,
                "patient_email": apt.patient_email,
                "appointment_date": apt.appointment_date.isoformat(),
                "start_time": apt.start_time.strftime("%H:%M"),
                "end_time": apt.end_time.strftime("%H:%M"),
                "appointment_type": {
                    "id": str(apt.appointment_type.id),
                    "name": apt.appointment_type.name,
                    "color": apt.appointment_type.color,
                    "duration": apt.appointment_type.duration
                } if apt.appointment_type else None,
                "status": apt.status,
                "reason": apt.reason,
                "notes": apt.notes,
                "source": apt.source,
                "auto_scheduled": apt.auto_scheduled,
                "confirmed_at": apt.confirmed_at.isoformat() if apt.confirmed_at else None,
                "reminder_sent": apt.reminder_sent,
                "rescheduled_count": apt.rescheduled_count
            }
            for apt in appointments
        ]
    }

@router.get("/appointments/{appointment_id}")
async def get_appointment_details(
    appointment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific appointment"""
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.user_id == current_user.id
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    return {
        "id": str(appointment.id),
        "patient_name": appointment.patient_name,
        "patient_phone": appointment.patient_phone,
        "patient_email": appointment.patient_email,
        "appointment_date": appointment.appointment_date.isoformat(),
        "start_time": appointment.start_time.strftime("%H:%M"),
        "end_time": appointment.end_time.strftime("%H:%M"),
        "appointment_type": {
            "id": str(appointment.appointment_type.id),
            "name": appointment.appointment_type.name,
            "color": appointment.appointment_type.color,
            "duration": appointment.appointment_type.duration
        } if appointment.appointment_type else None,
        "status": appointment.status,
        "reason": appointment.reason,
        "notes": appointment.notes,
        "source": appointment.source,
        "auto_scheduled": appointment.auto_scheduled,
        "ai_confidence_score": appointment.ai_confidence_score,
        "confirmed_at": appointment.confirmed_at.isoformat() if appointment.confirmed_at else None,
        "cancelled_at": appointment.cancelled_at.isoformat() if appointment.cancelled_at else None,
        "cancellation_reason": appointment.cancellation_reason,
        "reminder_sent": appointment.reminder_sent,
        "reminder_sent_at": appointment.reminder_sent_at.isoformat() if appointment.reminder_sent_at else None,
        "rescheduled_count": appointment.rescheduled_count,
        "created_at": appointment.created_at.isoformat(),
        "updated_at": appointment.updated_at.isoformat()
    }

@router.post("/appointments")
async def create_appointment(
    request: AppointmentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new appointment"""
    
    # Parse time strings
    start_time = datetime.strptime(request.start_time, "%H:%M").time()
    
    # Calculate end time based on appointment type or default duration
    if request.appointment_type_id:
        apt_type = db.query(AppointmentType).filter(
            AppointmentType.id == request.appointment_type_id,
            AppointmentType.user_id == current_user.id
        ).first()
        
        if not apt_type:
            raise HTTPException(status_code=404, detail="Appointment type not found")
        
        duration = apt_type.duration
    else:
        # Get default duration from template
        template = db.query(ScheduleTemplate).filter(
            ScheduleTemplate.user_id == current_user.id,
            ScheduleTemplate.day_of_week == request.appointment_date.weekday()
        ).first()
        
        duration = template.default_duration if template else 30
    
    # Calculate end time
    end_datetime = datetime.combine(date.today(), start_time) + timedelta(minutes=duration)
    end_time = end_datetime.time()
    
    # Check availability
    if not is_time_available(
        current_user.id,
        request.appointment_date,
        start_time,
        end_time,
        db
    ):
        raise HTTPException(
            status_code=400,
            detail="Time slot is not available"
        )
    
    # Check daily limit
    daily_count = db.query(func.count(Appointment.id)).filter(
        Appointment.user_id == current_user.id,
        Appointment.appointment_date == request.appointment_date,
        Appointment.status.in_(["scheduled", "confirmed"])
    ).scalar()
    
    settings = db.query(ScheduleSettings).filter(
        ScheduleSettings.user_id == current_user.id
    ).first()
    
    max_per_day = settings.max_patients_per_day if settings else 20
    
    if daily_count >= max_per_day:
        if not (settings and settings.allow_overbooking):
            raise HTTPException(
                status_code=400,
                detail=f"Daily limit of {max_per_day} appointments reached"
            )
    
    # Create appointment
    appointment = Appointment(
        user_id=current_user.id,
        patient_name=request.patient_name,
        patient_phone=request.patient_phone,
        patient_email=request.patient_email,
        appointment_date=request.appointment_date,
        start_time=start_time,
        end_time=end_time,
        appointment_type_id=request.appointment_type_id,
        reason=request.reason,
        notes=request.notes,
        source=request.source,
        status="scheduled"
    )
    
    # Auto-confirm if enabled
    if settings and settings.auto_confirm:
        appointment.status = "confirmed"
        appointment.confirmed_at = datetime.utcnow()
    
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    
    return {
        "message": "Appointment created successfully",
        "appointment_id": str(appointment.id),
        "status": appointment.status
    }

@router.put("/appointments/{appointment_id}/reschedule")
async def reschedule_appointment(
    appointment_id: str,
    request: RescheduleAppointmentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reschedule an existing appointment"""
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.user_id == current_user.id
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    if appointment.status == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot reschedule cancelled appointment")
    
    # Parse new time
    new_start_time = datetime.strptime(request.start_time, "%H:%M").time()
    
    # Calculate duration
    duration = (datetime.combine(date.today(), appointment.end_time) - 
                datetime.combine(date.today(), appointment.start_time)).seconds // 60
    
    new_end_datetime = datetime.combine(date.today(), new_start_time) + timedelta(minutes=duration)
    new_end_time = new_end_datetime.time()
    
    # Check availability for new time
    if not is_time_available(
        current_user.id,
        request.appointment_date,
        new_start_time,
        new_end_time,
        db,
        exclude_appointment_id=appointment_id
    ):
        raise HTTPException(
            status_code=400,
            detail="New time slot is not available"
        )
    
    # Create a record of the old appointment
    old_appointment_data = {
        "date": appointment.appointment_date.isoformat(),
        "start_time": appointment.start_time.strftime("%H:%M"),
        "end_time": appointment.end_time.strftime("%H:%M")
    }
    
    # Update appointment
    appointment.appointment_date = request.appointment_date
    appointment.start_time = new_start_time
    appointment.end_time = new_end_time
    appointment.status = "rescheduled" if appointment.status == "confirmed" else "scheduled"
    appointment.rescheduled_count += 1
    appointment.updated_at = datetime.utcnow()
    
    # Store reschedule info in notes
    reschedule_note = f"Rescheduled from {old_appointment_data['date']} {old_appointment_data['start_time']}"
    if request.reschedule_reason:
        reschedule_note += f" - Reason: {request.reschedule_reason}"
    
    if appointment.notes:
        appointment.notes = f"{appointment.notes}\n{reschedule_note}"
    else:
        appointment.notes = reschedule_note
    
    db.commit()
    
    # TODO: Send notification to patient if requested
    if request.notify_patient:
        # Implement notification logic here
        pass
    
    return {
        "message": "Appointment rescheduled successfully",
        "appointment_id": str(appointment.id),
        "new_date": request.appointment_date.isoformat(),
        "new_time": request.start_time
    }

@router.patch("/appointments/{appointment_id}/status")
async def update_appointment_status(
    appointment_id: str,
    request: AppointmentStatusRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update appointment status"""
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.user_id == current_user.id
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    valid_statuses = ["scheduled", "confirmed", "completed", "cancelled", "no_show", "rescheduled"]
    if request.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    appointment.status = request.status
    
    if request.status == "confirmed":
        appointment.confirmed_at = datetime.utcnow()
        appointment.confirmation_method = "manual"
    elif request.status == "cancelled":
        appointment.cancelled_at = datetime.utcnow()
        appointment.cancellation_reason = request.reason or "Cancelled by doctor"
    elif request.status == "completed":
        appointment.consultation_ended_at = datetime.utcnow()
    
    appointment.updated_at = datetime.utcnow()
    db.commit()
    
    # TODO: Send notification to patient about status change
    
    return {
        "message": f"Appointment status updated to {request.status}",
        "appointment_id": str(appointment.id),
        "status": appointment.status
    }

@router.delete("/appointments/{appointment_id}")
async def delete_appointment(
    appointment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an appointment"""
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.user_id == current_user.id
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    db.delete(appointment)
    db.commit()
    
    return {"message": "Appointment deleted"}

# Schedule Settings Endpoints
@router.get("/settings")
async def get_schedule_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get schedule settings for the current user"""
    settings = db.query(ScheduleSettings).filter(
        ScheduleSettings.user_id == current_user.id
    ).first()
    
    if not settings:
        # Return default settings
        return {
            "settings": {
                "timezone": "America/Mexico_City",
                "default_duration": 30,
                "buffer_time": 0,
                "min_advance_booking": 60,
                "max_advance_booking": 30,
                "auto_confirm": True,
                "confirmation_hours_before": 24,
                "allow_patient_cancellation": True,
                "cancellation_hours_limit": 24,
                "max_patients_per_day": 20,
                "waiting_list": False,
                "allow_overbooking": False,
                "max_overbooking_per_day": 0,
                "sync_google_calendar": False,
                "google_calendar_id": None,
                "confirmation_message": None,
                "reminder_message": None,
                "enable_ai_secretary": False,
                "ai_can_schedule": True,
                "ai_can_reschedule": True,
                "ai_can_cancel": False,
                "ai_requires_confirmation": True
            }
        }
    
    return {
        "settings": {
            "timezone": settings.timezone,
            "default_duration": settings.default_duration if settings.default_duration is not None else 30,
            "buffer_time": settings.buffer_time if settings.buffer_time is not None else 0,
            "min_advance_booking": settings.min_advance_booking,
            "max_advance_booking": settings.max_advance_booking,
            "auto_confirm": settings.auto_confirm,
            "confirmation_hours_before": settings.confirmation_hours_before,
            "allow_patient_cancellation": settings.allow_patient_cancellation,
            "cancellation_hours_limit": settings.cancellation_hours_limit,
            "max_patients_per_day": settings.max_patients_per_day if settings.max_patients_per_day is not None else 20,
            "waiting_list": settings.waiting_list if settings.waiting_list is not None else False,
            "allow_overbooking": settings.allow_overbooking,
            "max_overbooking_per_day": settings.max_overbooking_per_day,
            "sync_google_calendar": settings.sync_google_calendar,
            "google_calendar_id": settings.google_calendar_id,
            "confirmation_message": settings.confirmation_message,
            "reminder_message": settings.reminder_message,
            "enable_ai_secretary": settings.enable_ai_secretary if hasattr(settings, 'enable_ai_secretary') else False,
            "ai_can_schedule": settings.ai_can_schedule if hasattr(settings, 'ai_can_schedule') else True,
            "ai_can_reschedule": settings.ai_can_reschedule if hasattr(settings, 'ai_can_reschedule') else True,
            "ai_can_cancel": settings.ai_can_cancel if hasattr(settings, 'ai_can_cancel') else False,
            "ai_requires_confirmation": settings.ai_requires_confirmation if hasattr(settings, 'ai_requires_confirmation') else True
        }
    }

@router.post("/settings")
async def update_schedule_settings(
    request: ScheduleSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update schedule settings"""
    
    settings = db.query(ScheduleSettings).filter(
        ScheduleSettings.user_id == current_user.id
    ).first()
    
    if settings:
        # Update existing settings
        for key, value in request.dict().items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        settings.updated_at = datetime.utcnow()
    else:
        # Create new settings
        settings = ScheduleSettings(
            user_id=current_user.id,
            **request.dict()
        )
        db.add(settings)
    
    db.commit()
    
    return {"message": "Schedule settings updated"}

# Availability Endpoints
@router.get("/availability/{target_date}")
async def get_availability(
    target_date: date,
    appointment_type_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get available time slots for a specific date"""
    service = ScheduleService(db)
    available_slots = service.get_available_slots(
        user_id=current_user.id,
        target_date=target_date,
        appointment_type_id=appointment_type_id
    )
    
    return {
        "date": target_date.isoformat(),
        "available_slots": available_slots,
        "total_slots": len(available_slots)
    }

@router.get("/availability/range")
async def get_availability_range(
    start_date: date = Query(...),
    end_date: date = Query(...),
    appointment_type_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get available slots for a date range"""
    if (end_date - start_date).days > 31:
        raise HTTPException(
            status_code=400,
            detail="Date range cannot exceed 31 days"
        )
    
    service = ScheduleService(db)
    availability = {}
    
    current = start_date
    while current <= end_date:
        slots = service.get_available_slots(
            user_id=current_user.id,
            target_date=current,
            appointment_type_id=appointment_type_id
        )
        availability[current.isoformat()] = {
            "slots": slots,
            "count": len(slots)
        }
        current += timedelta(days=1)
    
    return {"availability": availability}

# Emergency Closure Endpoint
@router.post("/emergency-closure")
async def emergency_closure(
    request: EmergencyClosureRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Apply emergency closure for a specific date"""
    service = ScheduleService(db)
    
    try:
        result = service.emergency_closure(
            user_id=current_user.id,
            closure_date=request.date,
            reason=request.reason,
            message=request.message
        )
        
        # If requested, try to reschedule appointments
        if request.reschedule_appointments and result["cancelled_count"] > 0:
            # Find next available dates
            rescheduled_count = 0
            for patient_info in result["notified_patients"]:
                # This would be implemented to find next available slot
                # and notify patient with options
                pass
        
        return {
            "message": "Emergency closure applied successfully",
            "cancelled_count": result["cancelled_count"],
            "notified_patients": result["notified_patients"],
            "rescheduled_count": rescheduled_count if request.reschedule_appointments else 0
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Calendar View Endpoint
@router.get("/calendar-view")
async def get_calendar_view(
    view: str = Query("week", regex="^(day|week|month)$"),
    target_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get calendar view data for the agenda"""
    service = ScheduleService(db)
    calendar_date = target_date or datetime.now().date()
    
    calendar_data = service.get_calendar_view(
        user_id=current_user.id,
        view_type=view,
        target_date=calendar_date
    )
    
    return calendar_data

# AI Secretary Endpoints
@router.post("/ai/schedule")
async def ai_schedule_appointment(
    request: AIScheduleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Endpoint for AI Secretary to schedule appointments"""
    
    # Check if AI secretary is enabled
    settings = db.query(ScheduleSettings).filter(
        ScheduleSettings.user_id == current_user.id
    ).first()
    
    if not settings or not settings.enable_ai_secretary:
        raise HTTPException(
            status_code=403,
            detail="AI Secretary is not enabled for this account"
        )
    
    if not settings.ai_can_schedule:
        raise HTTPException(
            status_code=403,
            detail="AI Secretary does not have permission to schedule appointments"
        )
    
    service = ScheduleService(db)
    
    # Find best available slot based on preferences
    best_slot = None
    for preferred_date in request.preferred_dates:
        slots = service.get_available_slots(
            user_id=current_user.id,
            target_date=preferred_date
        )
        
        # Filter by preferred times
        for slot in slots:
            slot_hour = int(slot["start"].split(":")[0])
            
            for pref_time in request.preferred_times:
                if pref_time == "morning" and 6 <= slot_hour < 12:
                    best_slot = (preferred_date, slot)
                    break
                elif pref_time == "afternoon" and 12 <= slot_hour < 18:
                    best_slot = (preferred_date, slot)
                    break
                elif pref_time == "evening" and 18 <= slot_hour < 22:
                    best_slot = (preferred_date, slot)
                    break
                elif pref_time.startswith("specific:"):
                    specific_time = pref_time.split(":")[1] + ":" + pref_time.split(":")[2]
                    if slot["start"] == specific_time:
                        best_slot = (preferred_date, slot)
                        break
            
            if best_slot:
                break
        
        if best_slot:
            break
    
    if not best_slot:
        return {
            "success": False,
            "message": "No available slots found for the preferred dates and times",
            "alternative_slots": service.get_next_available_slots(
                user_id=current_user.id,
                count=3
            )
        }
    
    appointment_date, slot = best_slot
    
    # Create appointment
    appointment = Appointment(
        user_id=current_user.id,
        patient_name=request.patient_name,
        patient_phone=request.patient_phone,
        appointment_date=appointment_date,
        start_time=datetime.strptime(slot["start"], "%H:%M").time(),
        end_time=datetime.strptime(slot["end"], "%H:%M").time(),
        reason=request.reason,
        source="ai_secretary",
        auto_scheduled=True,
        ai_confidence_score=request.ai_confidence_score,
        whatsapp_session_id=request.whatsapp_session_id,
        status="scheduled" if settings.ai_requires_confirmation else "confirmed"
    )
    
    if not settings.ai_requires_confirmation:
        appointment.confirmed_at = datetime.utcnow()
        appointment.confirmation_method = "ai_auto"
    
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    
    return {
        "success": True,
        "appointment_id": str(appointment.id),
        "appointment_date": appointment_date.isoformat(),
        "appointment_time": slot["start"],
        "status": appointment.status,
        "requires_doctor_confirmation": settings.ai_requires_confirmation,
        "message": f"Appointment scheduled for {appointment_date.isoformat()} at {slot['start']}"
    }

@router.get("/ai/available-slots")
async def get_ai_formatted_slots(
    days_ahead: int = Query(7, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get available slots formatted for AI responses"""
    service = ScheduleService(db)
    
    slots_by_day = {}
    current = date.today()
    
    for i in range(days_ahead):
        check_date = current + timedelta(days=i)
        slots = service.get_available_slots(
            user_id=current_user.id,
            target_date=check_date
        )
        
        if slots:
            # Group by time period
            morning = [s for s in slots if int(s["start"].split(":")[0]) < 12]
            afternoon = [s for s in slots if 12 <= int(s["start"].split(":")[0]) < 18]
            evening = [s for s in slots if int(s["start"].split(":")[0]) >= 18]
            
            slots_by_day[check_date.isoformat()] = {
                "day_name": get_day_name(check_date.weekday()),
                "total_slots": len(slots),
                "morning": len(morning),
                "afternoon": len(afternoon),
                "evening": len(evening),
                "first_available": slots[0]["start"] if slots else None,
                "last_available": slots[-1]["start"] if slots else None
            }
    
    return {
        "summary": f"Availability for next {days_ahead} days",
        "slots_by_day": slots_by_day
    }

# Statistics Endpoints
@router.get("/stats")
async def get_schedule_stats(
    month: Optional[int] = Query(None),
    year: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get schedule statistics"""
    
    # Default to current month/year
    if not month or not year:
        now = datetime.now()
        month = month or now.month
        year = year or now.year
    
    # Calculate date range
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    # Get appointments for the month
    appointments = db.query(Appointment).filter(
        Appointment.user_id == current_user.id,
        Appointment.appointment_date >= start_date,
        Appointment.appointment_date <= end_date
    ).all()
    
    # Calculate statistics
    total_appointments = len(appointments)
    completed = len([a for a in appointments if a.status == "completed"])
    cancelled = len([a for a in appointments if a.status == "cancelled"])
    no_shows = len([a for a in appointments if a.status == "no_show"])
    
    # Calculate hours worked
    total_minutes = sum(
        (datetime.combine(date.today(), a.end_time) - 
         datetime.combine(date.today(), a.start_time)).seconds / 60
        for a in appointments if a.status == "completed"
    )
    hours_worked = total_minutes / 60
    
    # Calculate revenue (if prices are set)
    revenue = 0
    for apt in appointments:
        if apt.status == "completed" and apt.appointment_type and apt.appointment_type.suggested_price:
            revenue += apt.appointment_type.suggested_price
    
    # Most common appointment types
    type_counts = {}
    for apt in appointments:
        if apt.appointment_type:
            type_name = apt.appointment_type.name
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
    
    # Source distribution
    source_counts = {}
    for apt in appointments:
        source = apt.source
        source_counts[source] = source_counts.get(source, 0) + 1
    
    return {
        "month": month,
        "year": year,
        "total_appointments": total_appointments,
        "completed": completed,
        "cancelled": cancelled,
        "no_shows": no_shows,
        "completion_rate": round((completed / total_appointments * 100) if total_appointments > 0 else 0, 1),
        "hours_worked": round(hours_worked, 1),
        "revenue": revenue / 100,  # Convert from cents to currency
        "popular_appointment_types": sorted(
            [{"type": k, "count": v} for k, v in type_counts.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:5],
        "appointment_sources": source_counts,
        "ai_scheduled": len([a for a in appointments if a.auto_scheduled]),
        "average_reschedules": round(
            sum(a.rescheduled_count for a in appointments) / total_appointments 
            if total_appointments > 0 else 0, 2
        )
    }