from sqlalchemy import Column, String, DateTime, Boolean, JSON, ForeignKey, Integer, Time, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from database.connection import Base


class HorarioTemplate(Base):
    """Template de horario base por día de la semana"""
    __tablename__ = "horario_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Día de la semana (0=Lunes, 6=Domingo)
    day_of_week = Column(Integer, nullable=False)
    
    # Si este día está activo
    is_active = Column(Boolean, default=True)
    
    # Horario de apertura y cierre
    opens_at = Column(Time, nullable=True)
    closes_at = Column(Time, nullable=True)
    
    # Bloques de tiempo específicos (descansos, comidas, etc)
    # Formato: [{"start": "09:00", "end": "14:00", "type": "consultation"}, ...]
    time_blocks = Column(JSON, default=list)
    
    # NEW: Consultorio específico para este día
    consultorio_id = Column(UUID(as_uuid=True), ForeignKey("consultorios.id"), nullable=True)
    
    # NEW FIELDS FOR CALENDAR SYNC
    # Track if template has synced breaks
    has_synced_breaks = Column(Boolean, default=False)
    last_sync_update = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="horario_templates")
    consultorio = relationship("Consultorio", backref="horario_templates", foreign_keys=[consultorio_id])


class HorarioException(Base):
    """Excepciones/modificaciones a días específicos"""
    __tablename__ = "horario_exceptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Fecha específica de la excepción
    date = Column(Date, nullable=False)
    
    # Tipo de excepción
    is_working_day = Column(Boolean, default=True)  # False = día libre completo
    
    # Nueva columna para días especiales abiertos (normalmente cerrados)
    is_special_open = Column(Boolean, default=False)  # True = abrir en día normalmente cerrado
    
    # Nueva columna para vacaciones (rango de fechas)
    is_vacation = Column(Boolean, default=False)  # True = parte de un período de vacaciones
    vacation_group_id = Column(UUID(as_uuid=True), nullable=True)  # ID para agrupar días de vacaciones
    
    # Si es día laboral modificado
    opens_at = Column(Time, nullable=True)
    closes_at = Column(Time, nullable=True)
    
    # Bloques de tiempo para este día específico
    time_blocks = Column(JSON, default=list)
    
    # Razón/nota
    reason = Column(String(255), nullable=True)
    
    # NEW: Consultorio específico para este día especial
    consultorio_id = Column(UUID(as_uuid=True), ForeignKey("consultorios.id"), nullable=True)
    
    # NEW FIELDS FOR CALENDAR SYNC
    # Source of the exception
    sync_source = Column(String(50), nullable=True)  # 'google', 'apple', or 'manual'
    
    # External calendar event ID (for tracking synced events)
    external_calendar_id = Column(String(255), nullable=True)
    
    # Sync metadata
    sync_metadata = Column(JSON, nullable=True)  # Store additional sync info
    
    # Track if this exception was created from external calendar
    is_synced = Column(Boolean, default=False)
    
    # Connection ID that created this exception
    sync_connection_id = Column(UUID(as_uuid=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="horario_exceptions")
    consultorio = relationship("Consultorio", backref="horario_exceptions", foreign_keys=[consultorio_id])


# Helper functions
def get_day_name(day_number: int) -> str:
    """Convierte número de día a nombre en español"""
    days = {
        0: "Lunes",
        1: "Martes", 
        2: "Miércoles",
        3: "Jueves",
        4: "Viernes",
        5: "Sábado",
        6: "Domingo"
    }
    return days.get(day_number, "")


def get_day_abbreviation(day_number: int) -> str:
    """Convierte número de día a abreviación en español"""
    days = {
        0: "Lun",
        1: "Mar", 
        2: "Mié",
        3: "Jue",
        4: "Vie",
        5: "Sáb",
        6: "Dom"
    }
    return days.get(day_number, "")


def is_synced_event(exception: HorarioException) -> bool:
    """Check if an exception is from external calendar sync"""
    return exception.is_synced or exception.external_calendar_id is not None


def get_sync_source_display(source: str) -> str:
    """Get display name for sync source"""
    sources = {
        'google': 'Google Calendar',
        'apple': 'Apple Calendar',
        'manual': 'Manual',
        None: 'Manual'
    }
    return sources.get(source, 'Desconocido')