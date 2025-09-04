from sqlalchemy import Column, String, DateTime, Boolean, JSON, ForeignKey, Integer, Time, Date, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, time, date
import uuid
import enum
from database.connection import Base

class DayOfWeek(enum.Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

class BlockType(enum.Enum):
    CONSULTATION = "consultation"
    LUNCH = "lunch"
    ADMINISTRATIVE = "administrative"
    BREAK = "break"
    UNAVAILABLE = "unavailable"

class AppointmentDuration(enum.Enum):
    MIN_15 = 15
    MIN_30 = 30
    MIN_45 = 45
    MIN_60 = 60
    MIN_90 = 90

class ScheduleTemplate(Base):
    """Horario base/típico del doctor por día de la semana"""
    __tablename__ = "schedule_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Día de la semana (0=Lunes, 6=Domingo)
    day_of_week = Column(Integer, nullable=False)
    
    # Si este día está activo
    is_active = Column(Boolean, default=True)
    
    # Horario de apertura y cierre general
    opens_at = Column(Time, nullable=True)
    closes_at = Column(Time, nullable=True)
    
    # Configuración de citas
    default_duration = Column(Integer, default=30)  # minutos
    buffer_time = Column(Integer, default=0)  # minutos entre citas
    
    # Bloques de tiempo específicos (JSON)
    # Formato: [{"start": "09:00", "end": "14:00", "type": "consultation"}, ...]
    time_blocks = Column(JSON, default=list)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="schedule_templates")

class ScheduleException(Base):
    """Excepciones/modificaciones a días específicos"""
    __tablename__ = "schedule_exceptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Fecha específica de la excepción
    date = Column(Date, nullable=False)
    
    # Tipo de excepción
    is_working_day = Column(Boolean, default=True)  # False = día libre completo
    
    # Si es día laboral modificado, estos campos aplican
    opens_at = Column(Time, nullable=True)
    closes_at = Column(Time, nullable=True)
    
    # Bloques de tiempo para este día específico
    time_blocks = Column(JSON, default=list)
    
    # Razón/nota (opcional)
    reason = Column(String(255), nullable=True)  # "Congreso", "Vacaciones", etc.
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="schedule_exceptions")

class AppointmentType(Base):
    """Tipos de consulta con duraciones diferentes"""
    __tablename__ = "appointment_types"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    name = Column(String(100), nullable=False)  # "Primera consulta", "Seguimiento"
    duration = Column(Integer, nullable=False)  # minutos
    color = Column(String(7), default="#3B82F6")  # Hex color for UI
    
    # Precio sugerido (opcional)
    suggested_price = Column(Integer, nullable=True)  # en centavos
    
    # Si requiere preparación especial
    requires_preparation = Column(Boolean, default=False)
    preparation_time = Column(Integer, default=0)  # minutos antes
    
    is_active = Column(Boolean, default=True)
    
    # Order for display
    display_order = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="appointment_types")

class Appointment(Base):
    """Citas agendadas"""
    __tablename__ = "appointments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Información del paciente
    patient_name = Column(String(255), nullable=False)
    patient_phone = Column(String(20), nullable=False)
    patient_email = Column(String(255), nullable=True)
    
    # Detalles de la cita
    appointment_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    
    appointment_type_id = Column(UUID(as_uuid=True), ForeignKey("appointment_types.id"), nullable=True)
    
    # Estado
    status = Column(String(50), default="scheduled")  # scheduled, confirmed, completed, cancelled, no_show, rescheduled
    
    # Notas
    reason = Column(String(500), nullable=True)  # Motivo de consulta
    notes = Column(String(1000), nullable=True)  # Notas adicionales
    
    # Confirmación
    confirmed_at = Column(DateTime, nullable=True)
    confirmation_sent_at = Column(DateTime, nullable=True)
    confirmation_method = Column(String(50), nullable=True)  # whatsapp, sms, email, manual
    
    # Cancelación
    cancelled_at = Column(DateTime, nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    
    # Origen
    source = Column(String(50), default="manual")  # manual, whatsapp, web, instagram, ai_secretary
    
    # ===== NUEVOS CAMPOS PARA IA Y WHATSAPP =====
    
    # Tracking de WhatsApp/Twilio
    whatsapp_session_id = Column(String(255), nullable=True)  # ID de la conversación en Twilio
    whatsapp_conversation_sid = Column(String(255), nullable=True)  # SID de Twilio Conversations
    
    # Control de IA
    auto_scheduled = Column(Boolean, default=False)  # True si fue agendada por IA
    ai_confidence_score = Column(Integer, nullable=True)  # 0-100, confianza de la IA en la cita
    ai_interaction_log = Column(JSON, nullable=True)  # Log de la conversación con IA
    ai_extracted_data = Column(JSON, nullable=True)  # Datos extraídos por IA de la conversación
    
    # Control de recordatorios
    reminder_sent = Column(Boolean, default=False)
    reminder_sent_at = Column(DateTime, nullable=True)
    reminder_response = Column(String(50), nullable=True)  # confirmed, cancelled, no_response
    
    # Reprogramación
    rescheduled_from = Column(UUID(as_uuid=True), nullable=True)  # ID de la cita original si fue reprogramada
    rescheduled_count = Column(Integer, default=0)  # Número de veces que se ha reprogramado
    
    # Métricas
    patient_arrived_at = Column(DateTime, nullable=True)  # Hora real de llegada
    consultation_started_at = Column(DateTime, nullable=True)  # Hora real de inicio
    consultation_ended_at = Column(DateTime, nullable=True)  # Hora real de fin
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="appointments")
    appointment_type = relationship("AppointmentType", backref="appointments")

class ScheduleSettings(Base):
    """Configuraciones generales del horario del doctor"""
    __tablename__ = "schedule_settings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    
    # Configuración general
    timezone = Column(String(50), default="America/Mexico_City")
    
    # Configuración de duración y espaciado
    default_duration = Column(Integer, default=30)  # minutos por defecto para citas
    buffer_time = Column(Integer, default=0)  # minutos entre citas
    
    # Anticipación para citas
    min_advance_booking = Column(Integer, default=60)  # minutos mínimos de anticipación
    max_advance_booking = Column(Integer, default=30)  # días máximos de anticipación
    
    # Confirmaciones automáticas
    auto_confirm = Column(Boolean, default=True)
    confirmation_hours_before = Column(Integer, default=24)  # horas antes para enviar recordatorio
    
    # Política de cancelación
    allow_patient_cancellation = Column(Boolean, default=True)
    cancellation_hours_limit = Column(Integer, default=24)  # horas mínimas antes para cancelar
    
    # Límites diarios
    max_patients_per_day = Column(Integer, default=20)  # máximo de pacientes por día
    
    # Lista de espera
    waiting_list = Column(Boolean, default=False)  # habilitar lista de espera automática
    
    # Sobrecupo
    allow_overbooking = Column(Boolean, default=False)
    max_overbooking_per_day = Column(Integer, default=0)
    
    # Sincronización externa
    sync_google_calendar = Column(Boolean, default=False)
    google_calendar_id = Column(String(255), nullable=True)
    
    # ===== NUEVOS CAMPOS PARA IA Y WHATSAPP =====
    
    # Configuración de WhatsApp/IA
    enable_ai_secretary = Column(Boolean, default=False)  # Habilitar secretaria IA
    ai_secretary_phone = Column(String(20), nullable=True)  # Número de WhatsApp Business
    ai_secretary_active_hours = Column(JSON, nullable=True)  # Horarios activos de IA {"start": "08:00", "end": "20:00"}
    ai_secretary_personality = Column(String(50), default="professional")  # professional, friendly, formal
    ai_secretary_language = Column(String(10), default="es")  # Idioma principal
    
    # Respuestas automáticas personalizadas
    ai_greeting_message = Column(String(500), nullable=True)
    ai_busy_message = Column(String(500), nullable=True)
    ai_after_hours_message = Column(String(500), nullable=True)
    
    # Control de IA
    ai_can_schedule = Column(Boolean, default=True)  # IA puede agendar citas
    ai_can_reschedule = Column(Boolean, default=True)  # IA puede reprogramar
    ai_can_cancel = Column(Boolean, default=False)  # IA puede cancelar (más riesgoso)
    ai_requires_confirmation = Column(Boolean, default=True)  # Requiere confirmación del doctor para citas de IA
    
    # Mensajes personalizados
    confirmation_message = Column(String(500), nullable=True)
    reminder_message = Column(String(500), nullable=True)
    cancellation_message = Column(String(500), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="schedule_settings", uselist=False)

# Helper functions for the models
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

def is_time_available(user_id: str, date: date, start_time: time, end_time: time, db_session, exclude_appointment_id: str = None) -> bool:
    """Verifica si un horario está disponible"""
    # Build base query
    query = db_session.query(Appointment).filter(
        Appointment.user_id == user_id,
        Appointment.appointment_date == date,
        Appointment.status.in_(["scheduled", "confirmed"]),
        # Check for time overlap
        Appointment.start_time < end_time,
        Appointment.end_time > start_time
    )
    
    # Exclude specific appointment if editing
    if exclude_appointment_id:
        query = query.filter(Appointment.id != exclude_appointment_id)
    
    existing = query.first()
    return existing is None

def get_appointment_color(appointment_type: str) -> str:
    """Retorna el color según el tipo de cita"""
    colors = {
        "Primera consulta": "#9333ea",  # Purple
        "Control": "#0284c7",  # Blue
        "Seguimiento": "#16a34a",  # Green
        "Urgente": "#dc2626",  # Red
        "Consulta general": "#f59e0b",  # Amber
    }
    return colors.get(appointment_type, "#6b7280")  # Default gray