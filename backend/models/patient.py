from sqlalchemy import Column, String, DateTime, Float, Text, ForeignKey, Integer, Boolean, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, date
import uuid
from database.connection import Base

class Patient(Base):
    """
    Modelo simplificado de paciente - Solo campos esenciales
    """
    __tablename__ = "patients"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Foreign Key to User (Doctor)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # Información básica (lo que pide el modal HTML)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(200), nullable=False)
    age = Column(Integer, nullable=False)
    sex = Column(String(1), nullable=False)  # M, F, O
    
    # Contacto (todos opcionales como en el HTML)
    phone = Column(String(20))
    email = Column(String(255))
    whatsapp = Column(String(20))
    
    # Campos opcionales
    birth_date = Column(Date)
    notes = Column(Text)  # Notas iniciales/alergias/condiciones
    
    # Información financiera (para gestión de pagos)
    balance = Column(Float, default=0.0)  # Negativo = debe, Positivo = saldo a favor
    
    # Metadata
    last_visit = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relaciones simplificadas
    appointments = relationship("PatientAppointment", back_populates="patient", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="patient", cascade="all, delete-orphan")
    clinical_notes = relationship("ClinicalNote", back_populates="patient", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Patient {self.first_name} {self.last_name}>"
    
    def get_full_name(self):
        """Get patient's full name"""
        return f"{self.first_name} {self.last_name}"
    
    def calculate_age(self):
        """Calculate patient's age from birth_date or return stored age"""
        if self.birth_date:
            today = date.today()
            age = today.year - self.birth_date.year
            if today.month < self.birth_date.month or \
               (today.month == self.birth_date.month and today.day < self.birth_date.day):
                age -= 1
            return age
        return self.age
    
    def update_balance(self, amount: float, operation: str = "add"):
        """Update patient's financial balance"""
        if operation == "add_debt":
            self.balance -= amount  # Debt is negative
        elif operation == "add_payment":
            self.balance += amount  # Payment reduces debt
        elif operation == "add_credit":
            self.balance += amount  # Credit is positive
        elif operation == "set":
            self.balance = amount
        
        self.updated_at = datetime.utcnow()
    
    def to_dict(self):
        """Convert patient to dictionary for API responses"""
        return {
            "id": str(self.id),
            "doctor_id": str(self.doctor_id),
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.get_full_name(),
            "age": self.calculate_age(),
            "sex": self.sex,
            "phone": self.phone,
            "email": self.email,
            "whatsapp": self.whatsapp,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
            "notes": self.notes,
            "balance": self.balance,
            "last_visit": self.last_visit.isoformat() if self.last_visit else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class PatientAppointment(Base):
    """Modelo simplificado de citas"""
    __tablename__ = "patient_appointments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    appointment_date = Column(DateTime, nullable=False)
    appointment_type = Column(String(50), default="Consulta")  # Consulta, Seguimiento, etc.
    status = Column(String(20), default="scheduled")  # scheduled, completed, cancelled
    notes = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    patient = relationship("Patient", back_populates="appointments")


class Payment(Base):
    """Modelo simplificado de pagos - SIN ABONOS"""
    __tablename__ = "payments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    
    amount = Column(Float, nullable=False)
    payment_type = Column(String(20), nullable=False)  # debt, payment, credit (NO partial)
    concept = Column(String(200))  # Concepto del pago/deuda
    payment_method = Column(String(50))  # cash, card, transfer
    payment_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(Date)  # Fecha esperada de pago (para deudas)
    status = Column(String(20), default="pending")  # pending, paid
    reference = Column(String(100))  # Número de referencia o folio
    
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    # Relationships
    patient = relationship("Patient", back_populates="payments")
    
    def to_dict(self):
        """Convert payment to dictionary"""
        return {
            "id": str(self.id),
            "patient_id": str(self.patient_id),
            "amount": self.amount,
            "payment_type": self.payment_type,
            "concept": self.concept,
            "payment_method": self.payment_method,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "status": self.status,
            "reference": self.reference,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class ClinicalNote(Base):
    """Modelo simplificado de notas clínicas"""
    __tablename__ = "clinical_notes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    note_type = Column(String(50), default="general")  # general, reminder, important
    note_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    content = Column(Text, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    patient = relationship("Patient", back_populates="clinical_notes")
    
    def to_dict(self):
        """Convert note to dictionary"""
        return {
            "id": str(self.id),
            "patient_id": str(self.patient_id),
            "note_type": self.note_type,
            "note_date": self.note_date.isoformat() if self.note_date else None,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# Modelos legacy simplificados para compatibilidad
class MedicalRecord(Base):
    """Legacy medical records - simplificado"""
    __tablename__ = "medical_records"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    record_type = Column(String(20), nullable=False, default="note")
    record_date = Column(DateTime, default=datetime.utcnow)
    content = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Los siguientes modelos son placeholders para mantener compatibilidad
# pero no se usan en la versión simplificada

class ClinicalHistory(Base):
    """Placeholder para compatibilidad"""
    __tablename__ = "clinical_histories"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, unique=True)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class InformedConsent(Base):
    """Placeholder para compatibilidad"""
    __tablename__ = "informed_consents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ElectronicSignature(Base):
    """Placeholder para compatibilidad"""
    __tablename__ = "electronic_signatures"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    signed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PatientDocument(Base):
    """Placeholder para compatibilidad"""
    __tablename__ = "patient_documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)


class LabResult(Base):
    """Placeholder para compatibilidad"""
    __tablename__ = "lab_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Prescription(Base):
    """Placeholder para compatibilidad"""
    __tablename__ = "prescriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    prescription_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Enums simplificados para compatibilidad
class CaptureMode:
    BASIC = "basic"
    NOM004 = "nom004"

class ClinicalNoteType:
    EVOLUTION = "evolution"
    INTERCONSULTATION = "interconsultation"
    EMERGENCY = "emergency"

class ConsentType:
    GENERAL = "general"
    SURGERY = "surgery"

class DocumentType:
    ID = "identification"
    INSURANCE = "insurance"
    LAB_RESULT = "lab_result"
    OTHER = "other"