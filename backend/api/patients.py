from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from database.connection import get_db
from models.patient import Patient, PatientAppointment, Payment, ClinicalNote
from models.user import User
from api.auth import get_current_user
import uuid
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter()

# ============= PYDANTIC MODELS SIMPLIFICADOS =============

class PatientCreate(BaseModel):
    """Modelo simple para crear paciente - coincide con el modal HTML"""
    first_name: str
    last_name: str
    age: int = Field(ge=0, le=120)
    sex: str = Field(pattern="^[MFO]$")  # M, F, O
    phone: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[str] = None
    birth_date: Optional[date] = None
    notes: Optional[str] = None  # Para alergias, condiciones, etc.

class PatientUpdate(BaseModel):
    """Modelo para actualizar paciente"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    whatsapp: Optional[str] = None
    birth_date: Optional[date] = None
    notes: Optional[str] = None

class PatientResponse(BaseModel):
    """Respuesta simplificada del paciente"""
    id: str
    first_name: str
    last_name: str
    full_name: str
    age: int
    sex: str
    phone: Optional[str]
    email: Optional[str]
    whatsapp: Optional[str]
    balance: float
    last_visit: Optional[datetime]
    notes: Optional[str]
    created_at: datetime

class PaymentCreate(BaseModel):
    """Modelo para registrar pagos/deudas"""
    amount: float
    payment_type: str  # debt, payment, credit (NO partial)
    concept: Optional[str] = None
    payment_method: Optional[str] = "cash"  # cash, card, transfer
    payment_date: Optional[datetime] = None  # Fecha cuando se hizo el pago/deuda
    due_date: Optional[date] = None  # Fecha esperada de pago (para deudas)
    reference: Optional[str] = None  # Para vincular pagos con deudas específicas

class PaymentResponse(BaseModel):
    """Respuesta de pago"""
    id: str
    patient_id: str
    amount: float
    payment_type: str
    concept: Optional[str]
    payment_method: Optional[str]
    payment_date: datetime
    due_date: Optional[date]
    status: str
    reference: Optional[str]

class NoteCreate(BaseModel):
    """Modelo para crear notas"""
    note_type: str = "general"  # general, reminder, important
    content: str

class NoteResponse(BaseModel):
    """Respuesta de nota"""
    id: str
    patient_id: str
    note_type: str
    note_date: datetime
    content: str

class AppointmentCreate(BaseModel):
    """Modelo para crear citas"""
    appointment_date: datetime
    appointment_type: str = "Consulta"
    notes: Optional[str] = None

class AppointmentResponse(BaseModel):
    """Respuesta de cita"""
    id: str
    patient_id: str
    appointment_date: datetime
    appointment_type: str
    status: str
    notes: Optional[str]

# ============= ENDPOINTS - ORDEN CRÍTICO =============

# 1. POST / - Crear paciente
@router.post("/", response_model=PatientResponse)
async def create_patient(
    patient: PatientCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear un nuevo paciente - Simple"""
    logger.info(f"Creating patient: {patient.first_name} {patient.last_name}")
    
    db_patient = Patient(
        doctor_id=current_user.id,
        first_name=patient.first_name,
        last_name=patient.last_name,
        age=patient.age,
        sex=patient.sex,
        phone=patient.phone,
        email=patient.email,
        whatsapp=patient.whatsapp,
        birth_date=patient.birth_date,
        notes=patient.notes,
        balance=0.0
    )
    
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    
    return PatientResponse(
        id=str(db_patient.id),
        first_name=db_patient.first_name,
        last_name=db_patient.last_name,
        full_name=db_patient.get_full_name(),
        age=db_patient.age,
        sex=db_patient.sex,
        phone=db_patient.phone,
        email=db_patient.email,
        whatsapp=db_patient.whatsapp,
        balance=db_patient.balance,
        last_visit=db_patient.last_visit,
        notes=db_patient.notes,
        created_at=db_patient.created_at
    )

# 2. GET /stats/summary - Estadísticas ANTES de rutas dinámicas
@router.get("/stats/summary")
async def get_patients_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener estadísticas de pacientes"""
    total_patients = db.query(func.count(Patient.id)).filter(
        Patient.doctor_id == current_user.id,
        Patient.is_active == True
    ).scalar() or 0
    
    patients_with_debt = db.query(func.count(Patient.id)).filter(
        Patient.doctor_id == current_user.id,
        Patient.balance < 0,
        Patient.is_active == True
    ).scalar() or 0
    
    patients_with_credit = db.query(func.count(Patient.id)).filter(
        Patient.doctor_id == current_user.id,
        Patient.balance > 0,
        Patient.is_active == True
    ).scalar() or 0
    
    total_debt = db.query(func.sum(Patient.balance)).filter(
        Patient.doctor_id == current_user.id,
        Patient.balance < 0,
        Patient.is_active == True
    ).scalar() or 0
    
    total_credit = db.query(func.sum(Patient.balance)).filter(
        Patient.doctor_id == current_user.id,
        Patient.balance > 0,
        Patient.is_active == True
    ).scalar() or 0
    
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)
    
    appointments_today = db.query(func.count(PatientAppointment.id)).filter(
        PatientAppointment.doctor_id == current_user.id,
        PatientAppointment.appointment_date >= today_start,
        PatientAppointment.appointment_date <= today_end,
        PatientAppointment.status != "cancelled"
    ).scalar() or 0
    
    current_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_this_month = db.query(func.count(Patient.id)).filter(
        Patient.doctor_id == current_user.id,
        Patient.created_at >= current_month,
        Patient.is_active == True
    ).scalar() or 0
    
    return {
        "total_patients": total_patients,
        "patients_with_debt": patients_with_debt,
        "patients_with_credit": patients_with_credit,
        "appointments_today": appointments_today,
        "new_this_month": new_this_month,
        "total_debt": abs(total_debt) if total_debt else 0,
        "total_credit": total_credit if total_credit else 0,
        "net_balance": (total_credit if total_credit else 0) - abs(total_debt if total_debt else 0)
    }

# 3. GET /payment-calendar - ACTUALIZADO PARA CONSIDERAR SALDO A FAVOR
@router.get("/payment-calendar")
async def get_payment_calendar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener calendario de pagos pendientes agrupados por paciente con montos restantes reales"""
    try:
        logger.info("Getting payment calendar for user: %s", current_user.id)
        
        # Obtener pacientes con deuda neta (balance < 0 después de aplicar saldo a favor)
        patients_with_debt = db.query(Patient).filter(
            Patient.doctor_id == current_user.id,
            Patient.balance < 0,
            Patient.is_active == True
        ).all()
        
        patients_data = []
        
        for patient in patients_with_debt:
            # El balance del paciente ya considera deudas y créditos
            # Obtener TODAS las deudas pendientes del paciente
            pending_debts = db.query(Payment).filter(
                Payment.patient_id == patient.id,
                Payment.payment_type == "debt",
                Payment.status == "pending"
            ).order_by(Payment.due_date.asc()).all()
            
            # Calcular el total de créditos del paciente
            total_credits = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
                Payment.patient_id == patient.id,
                Payment.payment_type == "credit"
            ).scalar() or 0
            
            # Crear lista de deudas del paciente con montos restantes
            patient_debts = []
            earliest_due_date = None
            days_until_earliest = 999999
            virtual_credit_remaining = float(total_credits)  # Crédito disponible para aplicar
            
            if pending_debts:
                for debt in pending_debts:
                    # Calcular cuánto se ha pagado de esta deuda específica
                    total_paid = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
                        Payment.patient_id == patient.id,
                        Payment.payment_type == "payment",
                        Payment.reference == str(debt.id)
                    ).scalar() or 0
                    
                    original_amount = debt.amount
                    remaining = debt.amount - float(total_paid)
                    credit_applied_to_this_debt = 0
                    
                    # Aplicar crédito virtual si existe
                    if virtual_credit_remaining > 0 and remaining > 0:
                        if virtual_credit_remaining >= remaining:
                            credit_applied_to_this_debt = remaining
                            virtual_credit_remaining -= remaining
                            remaining = 0
                        else:
                            credit_applied_to_this_debt = virtual_credit_remaining
                            remaining -= virtual_credit_remaining
                            virtual_credit_remaining = 0
                    
                    # Solo incluir deudas con saldo pendiente
                    if remaining > 0:
                        if debt.due_date:
                            today = date.today()
                            days_until_due = (debt.due_date - today).days
                            is_overdue = debt.due_date < today  # Solo es vencido si la fecha es anterior a hoy
                            
                            if earliest_due_date is None or debt.due_date < earliest_due_date:
                                earliest_due_date = debt.due_date
                                days_until_earliest = days_until_due
                        else:
                            days_until_due = None
                            is_overdue = False
                        
                        # Si se aplicó crédito, mostrar el monto original
                        if credit_applied_to_this_debt > 0:
                            display_original = original_amount
                            display_remaining = remaining
                        else:
                            display_original = original_amount
                            display_remaining = remaining
                        
                        patient_debts.append({
                            "original_amount": display_original,  # Monto original de la deuda
                            "amount": display_remaining,  # Monto restante por pagar
                            "total_paid": float(total_paid),  # Cuánto se ha pagado
                            "credit_applied": credit_applied_to_this_debt,  # Crédito aplicado
                            "concept": debt.concept or "Servicio médico",
                            "due_date": debt.due_date.isoformat() if debt.due_date else None,
                            "days_until_due": days_until_due,
                            "is_overdue": is_overdue,
                            "has_partial_payment": float(total_paid) > 0 or credit_applied_to_this_debt > 0
                        })
            
            # Si no hay deudas con detalle, usar el balance total
            if not patient_debts and patient.balance < 0:
                patient_debts.append({
                    "original_amount": abs(patient.balance),
                    "amount": abs(patient.balance),
                    "total_paid": 0,
                    "concept": "Adeudo total",
                    "due_date": None,
                    "days_until_due": None,
                    "is_overdue": True,
                    "has_partial_payment": False
                })
                days_until_earliest = 999998
            
            # Solo agregar paciente si tiene deudas pendientes reales
            if patient_debts:
                patients_data.append({
                    "patient_id": str(patient.id),
                    "patient_name": patient.get_full_name(),
                    "total_debt": abs(patient.balance),  # Balance real del paciente
                    "phone": patient.phone,
                    "whatsapp": patient.whatsapp,
                    "debts": patient_debts,
                    "earliest_due_date": earliest_due_date.isoformat() if earliest_due_date else None,
                    "days_until_earliest": days_until_earliest,
                    "has_overdue": any(d.get("is_overdue", False) for d in patient_debts)
                })
        
        # Ordenar pacientes por urgencia
        patients_data.sort(key=lambda x: (
            not x["has_overdue"],
            x["days_until_earliest"] if x["days_until_earliest"] is not None else 999999
        ))
        
        # Limitar a 10 pacientes para el carousel
        patients_data = patients_data[:10]
        
        # Calcular el total general (suma de balances negativos reales)
        total_amount = sum(p["total_debt"] for p in patients_data)
        
        return {
            "total_pending": len(patients_data),
            "total_amount": total_amount,
            "patients": patients_data
        }
        
    except Exception as e:
        logger.error(f"Error in payment calendar: {str(e)}")
        return {
            "total_pending": 0,
            "total_amount": 0,
            "patients": []
        }

# 4. GET / - Listar pacientes (también debe ir antes de /{patient_id})
@router.get("/", response_model=List[PatientResponse])
async def get_patients(
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener todos los pacientes con búsqueda opcional"""
    query = db.query(Patient).filter(
        Patient.doctor_id == current_user.id,
        Patient.is_active == True
    )
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Patient.first_name.ilike(search_term),
                Patient.last_name.ilike(search_term),
                Patient.phone.like(search_term),
                Patient.email.ilike(search_term),
                Patient.whatsapp.like(search_term)
            )
        )
    
    patients = query.offset(skip).limit(limit).all()
    
    return [
        PatientResponse(
            id=str(p.id),
            first_name=p.first_name,
            last_name=p.last_name,
            full_name=p.get_full_name(),
            age=p.calculate_age(),
            sex=p.sex,
            phone=p.phone,
            email=p.email,
            whatsapp=p.whatsapp,
            balance=p.balance,
            last_visit=p.last_visit,
            notes=p.notes,
            created_at=p.created_at
        ) for p in patients
    ]

# ============= AHORA SÍ LAS RUTAS DINÁMICAS =============

# 5. GET /{patient_id}/pending-debts - ACTUALIZADO PARA CONSIDERAR SALDO A FAVOR
@router.get("/{patient_id}/pending-debts")
async def get_pending_debts(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener deudas pendientes de un paciente considerando saldo a favor"""
    try:
        patient = db.query(Patient).filter(
            Patient.id == patient_id,
            Patient.doctor_id == current_user.id
        ).first()
        
        if not patient:
            raise HTTPException(status_code=404, detail="Paciente no encontrado")
        
        # Obtener el total de créditos del paciente
        total_credits = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.patient_id == patient_id,
            Payment.payment_type == "credit"
        ).scalar() or 0
        
        available_credit = float(total_credits)
        logger.info(f"Patient {patient_id} has total credits: {available_credit}")
        
        # Obtener todas las deudas pendientes
        pending_debts = db.query(Payment).filter(
            Payment.patient_id == patient_id,
            Payment.payment_type == "debt",
            Payment.status == "pending"
        ).order_by(Payment.due_date.asc(), Payment.payment_date.desc()).all()
        
        debts_list = []
        virtual_credit_used = 0  # Para tracking del crédito usado
        
        for debt in pending_debts:
            # Para cada deuda, calcular cuánto se ha pagado
            total_paid = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
                Payment.patient_id == patient_id,
                Payment.payment_type == "payment",
                Payment.reference == str(debt.id)
            ).scalar() or 0
            
            original_amount = debt.amount
            remaining = debt.amount - float(total_paid)
            credit_applied_to_this_debt = 0
            
            # Aplicar saldo a favor disponible a esta deuda
            if available_credit > 0 and remaining > 0:
                if available_credit >= remaining:
                    # El crédito cubre toda la deuda restante
                    credit_applied_to_this_debt = remaining
                    available_credit -= remaining
                    virtual_credit_used += remaining
                    logger.info(f"Credit covers full debt {debt.id}: {remaining}")
                    remaining = 0
                else:
                    # El crédito cubre parte de la deuda
                    credit_applied_to_this_debt = available_credit
                    remaining -= available_credit
                    virtual_credit_used += available_credit
                    logger.info(f"Credit partially covers debt {debt.id}: {available_credit}")
                    available_credit = 0
            
            # Solo incluir si aún debe algo después de aplicar créditos
            if remaining > 0:
                # Determinar si está vencida
                is_overdue = False
                if debt.due_date:
                    today = date.today()
                    is_overdue = debt.due_date < today
                
                debts_list.append({
                    "id": str(debt.id),
                    "amount": original_amount,  # Monto original de la deuda
                    "concept": debt.concept or "Servicio médico",
                    "due_date": debt.due_date.isoformat() if debt.due_date else None,
                    "payment_date": debt.payment_date.isoformat() if debt.payment_date else None,
                    "total_paid": float(total_paid),
                    "credit_applied": credit_applied_to_this_debt,  # Crédito aplicado a esta deuda
                    "remaining": remaining,  # Lo que realmente debe después de pagos y créditos
                    "is_overdue": is_overdue
                })
        
        # Calcular el total real considerando el balance del paciente
        # Si balance < 0: el paciente debe
        # Si balance > 0: el paciente tiene saldo a favor
        # Si balance = 0: está al corriente
        total_debt = abs(patient.balance) if patient.balance < 0 else 0
        
        return {
            "pending_debts": debts_list,
            "total_debt": total_debt,
            "credit_available": float(total_credits),
            "credit_used": virtual_credit_used,
            "net_balance": patient.balance  # Negativo = debe, Positivo = a favor
        }
        
    except Exception as e:
        logger.error(f"Error getting pending debts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 6. GET /{patient_id} - Esta DEBE ir DESPUÉS de todas las rutas estáticas
@router.get("/{patient_id}")
async def get_patient(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener un paciente por ID"""
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == current_user.id
    ).first()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    
    return patient.to_dict()

@router.put("/{patient_id}")
async def update_patient(
    patient_id: str,
    patient_update: PatientUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Actualizar información del paciente"""
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == current_user.id
    ).first()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    
    update_data = patient_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        if value is not None:
            setattr(patient, field, value)
    
    patient.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(patient)
    
    return patient.to_dict()

@router.delete("/{patient_id}")
async def delete_patient(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eliminar paciente (soft delete)"""
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == current_user.id
    ).first()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    
    patient.is_active = False
    patient.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {"message": "Paciente eliminado exitosamente"}

# ============= GESTIÓN DE PAGOS =============

@router.post("/{patient_id}/payments", response_model=PaymentResponse)
async def create_payment(
    patient_id: str,
    payment: PaymentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Registrar pago, deuda o saldo a favor"""
    try:
        patient = db.query(Patient).filter(
            Patient.id == patient_id,
            Patient.doctor_id == current_user.id
        ).first()
        
        if not patient:
            raise HTTPException(status_code=404, detail="Paciente no encontrado")
        
        # Si no se proporciona fecha, usar la fecha/hora actual
        if payment.payment_date:
            payment_date = payment.payment_date
        else:
            # Usar datetime.utcnow() para mantener consistencia con UTC
            payment_date = datetime.utcnow()
        
        # Si es un pago y tiene referencia (debt_id), verificar si liquida la deuda
        if payment.payment_type == "payment" and payment.reference:
            # Buscar la deuda original
            original_debt = db.query(Payment).filter(
                Payment.id == payment.reference,
                Payment.payment_type == "debt",
                Payment.status == "pending"
            ).first()
            
            if original_debt:
                # Calcular total pagado para esta deuda
                already_paid = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
                    Payment.patient_id == patient_id,
                    Payment.payment_type == "payment",
                    Payment.reference == payment.reference
                ).scalar() or 0
                
                total_paid_after = float(already_paid) + payment.amount
                
                # Si el total pagado >= deuda, marcarla como pagada
                if total_paid_after >= original_debt.amount:
                    original_debt.status = "paid"
                    payment.concept = f"Liquidación - {original_debt.concept or 'Servicio médico'}"
                else:
                    payment.concept = f"Abono - {original_debt.concept or 'Servicio médico'} (${payment.amount:.2f})"
        
        # Crear el registro de pago
        db_payment = Payment(
            patient_id=patient_id,
            amount=payment.amount,
            payment_type=payment.payment_type,
            concept=payment.concept,
            payment_method=payment.payment_method,
            payment_date=payment_date,
            due_date=payment.due_date,
            reference=payment.reference,
            status="paid" if payment.payment_type in ["payment", "credit"] else "pending",
            created_by=current_user.id
        )
        
        # Actualizar balance del paciente
        if payment.payment_type == "debt":
            patient.balance -= payment.amount  # Las deudas son negativas
        elif payment.payment_type == "payment":
            patient.balance += payment.amount  # Los pagos reducen la deuda (hacen el balance menos negativo)
        elif payment.payment_type == "credit":
            patient.balance += payment.amount  # Los créditos son positivos
        
        patient.updated_at = datetime.utcnow()
        
        db.add(db_payment)
        db.commit()
        db.refresh(db_payment)
        
        return PaymentResponse(
            id=str(db_payment.id),
            patient_id=str(db_payment.patient_id),
            amount=db_payment.amount,
            payment_type=db_payment.payment_type,
            concept=db_payment.concept,
            payment_method=db_payment.payment_method,
            payment_date=db_payment.payment_date,
            due_date=db_payment.due_date,
            status=db_payment.status,
            reference=db_payment.reference
        )
        
    except Exception as e:
        logger.error(f"Error creating payment: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{patient_id}/payments", response_model=List[PaymentResponse])
async def get_payments(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener historial de pagos de un paciente ordenado por fecha reciente"""
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == current_user.id
    ).first()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    
    # Obtener TODOS los movimientos ordenados por fecha más reciente
    payments = db.query(Payment).filter(
        Payment.patient_id == patient_id
    ).order_by(Payment.payment_date.desc()).all()
    
    return [
        PaymentResponse(
            id=str(p.id),
            patient_id=str(p.patient_id),
            amount=p.amount,
            payment_type=p.payment_type,
            concept=p.concept,
            payment_method=p.payment_method,
            payment_date=p.payment_date,
            due_date=p.due_date,
            status=p.status,
            reference=p.reference
        ) for p in payments
    ]

# ============= NOTAS =============

@router.post("/{patient_id}/notes", response_model=NoteResponse)
async def create_note(
    patient_id: str,
    note: NoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear una nota para el paciente"""
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == current_user.id
    ).first()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    
    db_note = ClinicalNote(
        patient_id=patient_id,
        doctor_id=current_user.id,
        note_type=note.note_type,
        content=note.content
    )
    
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    
    return NoteResponse(
        id=str(db_note.id),
        patient_id=str(db_note.patient_id),
        note_type=db_note.note_type,
        note_date=db_note.note_date,
        content=db_note.content
    )

@router.get("/{patient_id}/notes", response_model=List[NoteResponse])
async def get_notes(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener notas del paciente"""
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == current_user.id
    ).first()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    
    notes = db.query(ClinicalNote).filter(
        ClinicalNote.patient_id == patient_id
    ).order_by(ClinicalNote.note_date.desc()).all()
    
    return [
        NoteResponse(
            id=str(n.id),
            patient_id=str(n.patient_id),
            note_type=n.note_type,
            note_date=n.note_date,
            content=n.content
        ) for n in notes
    ]

# ============= CITAS =============

@router.post("/{patient_id}/appointments", response_model=AppointmentResponse)
async def create_appointment(
    patient_id: str,
    appointment: AppointmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear una cita para el paciente"""
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == current_user.id
    ).first()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    
    db_appointment = PatientAppointment(
        patient_id=patient_id,
        doctor_id=current_user.id,
        appointment_date=appointment.appointment_date,
        appointment_type=appointment.appointment_type,
        notes=appointment.notes,
        status="scheduled"
    )
    
    db.add(db_appointment)
    db.commit()
    db.refresh(db_appointment)
    
    return AppointmentResponse(
        id=str(db_appointment.id),
        patient_id=str(db_appointment.patient_id),
        appointment_date=db_appointment.appointment_date,
        appointment_type=db_appointment.appointment_type,
        status=db_appointment.status,
        notes=db_appointment.notes
    )

@router.get("/{patient_id}/appointments", response_model=List[AppointmentResponse])
async def get_appointments(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener citas del paciente"""
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.doctor_id == current_user.id
    ).first()
    
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    
    appointments = db.query(PatientAppointment).filter(
        PatientAppointment.patient_id == patient_id
    ).order_by(PatientAppointment.appointment_date.desc()).all()
    
    return [
        AppointmentResponse(
            id=str(a.id),
            patient_id=str(a.patient_id),
            appointment_date=a.appointment_date,
            appointment_type=a.appointment_type,
            status=a.status,
            notes=a.notes
        ) for a in appointments
    ]

@router.put("/{patient_id}/appointments/{appointment_id}/status")
async def update_appointment_status(
    patient_id: str,
    appointment_id: str,
    status: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Actualizar estado de cita (completed, cancelled, etc.)"""
    appointment = db.query(PatientAppointment).filter(
        PatientAppointment.id == appointment_id,
        PatientAppointment.patient_id == patient_id,
        PatientAppointment.doctor_id == current_user.id
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    appointment.status = status
    appointment.updated_at = datetime.utcnow()
    
    if status == "completed":
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if patient:
            patient.last_visit = appointment.appointment_date
    
    db.commit()
    
    return {"message": f"Estado de cita actualizado a {status}"}