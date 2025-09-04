from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import uuid
from database.connection import get_db
from models.user import User
from models.servicios import ServicioMedico, TipoPrecio, get_color_for_service, validate_service_duration
from models.consultorio import Consultorio
from api.auth import get_current_user
from services.servicios_service import ServiciosService
from services.capacidad_service import CapacidadService

router = APIRouter()

# Pydantic models for requests/responses
class ServicioMedicoRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: str = Field(..., min_length=10)  # Descripción obligatoria y precisa
    duracion_minutos: int = Field(..., ge=15, le=180)  # 15 min a 3 horas
    cantidad_consultas: int = Field(default=1, ge=1, le=10)
    tipo_precio: str = Field(default="precio_fijo")
    precio: Optional[int] = None  # En centavos
    precio_minimo: Optional[int] = None
    precio_maximo: Optional[int] = None
    instrucciones_ia: Optional[str] = None
    instrucciones_paciente: Optional[str] = None
    consultorio_id: Optional[str] = None  # ID del consultorio donde se ofrece
    doctores_atienden: Optional[List[str]] = None  # Lista de nombres de doctores
    
    @validator('tipo_precio')
    def validate_tipo_precio(cls, v):
        valid_types = ["precio_fijo", "precio_por_evaluar", "gratis", "precio_variable"]
        if v not in valid_types:
            raise ValueError(f'Tipo de precio debe ser uno de: {", ".join(valid_types)}')
        return v
    
    @validator('precio')
    def validate_precio(cls, v, values):
        if 'tipo_precio' in values:
            if values['tipo_precio'] == 'precio_fijo' and v is None:
                raise ValueError('Precio es requerido para tipo precio_fijo')
            if values['tipo_precio'] in ['gratis', 'precio_por_evaluar'] and v is not None:
                return None  # Ignorar precio para estos tipos
        return v
    
    @validator('doctores_atienden')
    def validate_doctores(cls, v):
        if v:
            # Filter out empty strings and strip whitespace
            return [doc.strip() for doc in v if doc.strip()]
        return []

class ServicioMedicoUpdateRequest(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    descripcion: Optional[str] = Field(None, min_length=10)
    duracion_minutos: Optional[int] = Field(None, ge=15, le=180)
    cantidad_consultas: Optional[int] = Field(None, ge=1, le=10)
    tipo_precio: Optional[str] = None
    precio: Optional[int] = None
    precio_minimo: Optional[int] = None
    precio_maximo: Optional[int] = None
    instrucciones_ia: Optional[str] = None
    instrucciones_paciente: Optional[str] = None
    consultorio_id: Optional[str] = None
    doctores_atienden: Optional[List[str]] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None
    
    @validator('doctores_atienden')
    def validate_doctores(cls, v):
        if v:
            # Filter out empty strings and strip whitespace
            return [doc.strip() for doc in v if doc.strip()]
        return v


# Servicios Endpoints
@router.get("/list")
async def get_servicios(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener todos los servicios médicos del usuario"""
    servicios = db.query(ServicioMedico).filter(
        ServicioMedico.user_id == current_user.id,
        ServicioMedico.is_active == True
    ).order_by(ServicioMedico.display_order, ServicioMedico.created_at).all()
    
    # Si no hay servicios, crear uno por defecto
    if not servicios:
        # Obtener consultorio principal
        consultorio_principal = db.query(Consultorio).filter(
            Consultorio.user_id == current_user.id,
            Consultorio.es_principal == True,
            Consultorio.activo == True
        ).first()
        
        servicio_default = ServicioMedico(
            user_id=current_user.id,
            nombre="Consulta inicial",
            descripcion="Evaluación completa del paciente, historia clínica y diagnóstico inicial",
            duracion_minutos=60,
            cantidad_consultas=1,
            tipo_precio=TipoPrecio.PRECIO_POR_EVALUAR,
            color="#9333ea",
            display_order=0,
            instrucciones_ia="Agendar para pacientes nuevos o que no han venido en más de 6 meses",
            consultorio_id=consultorio_principal.id if consultorio_principal else None,
            doctores_atienden=[]
        )
        db.add(servicio_default)
        servicios.append(servicio_default)
        db.commit()
    
    return {
        "servicios": [servicio.to_dict() for servicio in servicios]
    }


@router.post("/create")
async def create_servicio(
    request: ServicioMedicoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear un nuevo servicio médico"""
    
    # Validar duración
    if not validate_service_duration(request.duracion_minutos):
        raise HTTPException(
            status_code=400,
            detail="La duración debe estar entre 15 minutos y 3 horas"
        )
    
    # Si no se especifica consultorio, usar el principal
    consultorio_id = request.consultorio_id
    if not consultorio_id:
        consultorio_principal = db.query(Consultorio).filter(
            Consultorio.user_id == current_user.id,
            Consultorio.es_principal == True,
            Consultorio.activo == True
        ).first()
        
        if consultorio_principal:
            consultorio_id = str(consultorio_principal.id)
    else:
        # Validar que el consultorio pertenece al usuario
        consultorio = db.query(Consultorio).filter(
            Consultorio.id == consultorio_id,
            Consultorio.user_id == current_user.id,
            Consultorio.activo == True
        ).first()
        
        if not consultorio:
            raise HTTPException(
                status_code=404,
                detail="Consultorio no encontrado o no pertenece al usuario"
            )
    
    # Obtener el máximo display_order actual
    max_order = db.query(func.max(ServicioMedico.display_order)).filter(
        ServicioMedico.user_id == current_user.id
    ).scalar() or 0
    
    # Obtener color basado en el índice
    servicios_count = db.query(func.count(ServicioMedico.id)).filter(
        ServicioMedico.user_id == current_user.id
    ).scalar() or 0
    
    # Convertir tipo_precio string a enum
    tipo_precio_enum = TipoPrecio[request.tipo_precio.upper()]
    
    # Crear servicio
    servicio = ServicioMedico(
        user_id=current_user.id,
        nombre=request.nombre,
        descripcion=request.descripcion,
        duracion_minutos=request.duracion_minutos,
        cantidad_consultas=request.cantidad_consultas,
        tipo_precio=tipo_precio_enum,
        precio=request.precio if tipo_precio_enum == TipoPrecio.PRECIO_FIJO else None,
        precio_minimo=request.precio_minimo if tipo_precio_enum == TipoPrecio.PRECIO_VARIABLE else None,
        precio_maximo=request.precio_maximo if tipo_precio_enum == TipoPrecio.PRECIO_VARIABLE else None,
        instrucciones_ia=request.instrucciones_ia,
        instrucciones_paciente=request.instrucciones_paciente,
        consultorio_id=consultorio_id,
        doctores_atienden=request.doctores_atienden or [],
        color=get_color_for_service(servicios_count),
        display_order=max_order + 1
    )
    
    db.add(servicio)
    db.commit()
    db.refresh(servicio)
    
    return {
        "message": "Servicio creado exitosamente",
        "servicio": servicio.to_dict()
    }


@router.put("/{servicio_id}")
async def update_servicio(
    servicio_id: str,
    request: ServicioMedicoUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Actualizar un servicio médico existente"""
    servicio = db.query(ServicioMedico).filter(
        ServicioMedico.id == servicio_id,
        ServicioMedico.user_id == current_user.id
    ).first()
    
    if not servicio:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    
    # Actualizar solo campos proporcionados
    update_data = request.dict(exclude_unset=True)
    
    # Validar consultorio si se proporciona
    if 'consultorio_id' in update_data and update_data['consultorio_id']:
        consultorio = db.query(Consultorio).filter(
            Consultorio.id == update_data['consultorio_id'],
            Consultorio.user_id == current_user.id,
            Consultorio.activo == True
        ).first()
        
        if not consultorio:
            raise HTTPException(
                status_code=404,
                detail="Consultorio no encontrado o no pertenece al usuario"
            )
    
    # Manejar tipo_precio si se proporciona
    if 'tipo_precio' in update_data:
        update_data['tipo_precio'] = TipoPrecio[update_data['tipo_precio'].upper()]
        
        # Limpiar campos de precio según el tipo
        if update_data['tipo_precio'] in [TipoPrecio.GRATIS, TipoPrecio.PRECIO_POR_EVALUAR]:
            update_data['precio'] = None
            update_data['precio_minimo'] = None
            update_data['precio_maximo'] = None
    
    # Actualizar campos
    for key, value in update_data.items():
        setattr(servicio, key, value)
    
    servicio.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(servicio)
    
    return {
        "message": "Servicio actualizado",
        "servicio": servicio.to_dict()
    }


@router.delete("/{servicio_id}")
async def delete_servicio(
    servicio_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eliminar un servicio médico"""
    servicio = db.query(ServicioMedico).filter(
        ServicioMedico.id == servicio_id,
        ServicioMedico.user_id == current_user.id
    ).first()
    
    if not servicio:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    
    # Verificar si es el último servicio activo
    active_count = db.query(func.count(ServicioMedico.id)).filter(
        ServicioMedico.user_id == current_user.id,
        ServicioMedico.is_active == True
    ).scalar()
    
    if active_count <= 1:
        raise HTTPException(
            status_code=400,
            detail="No puedes eliminar el último servicio. Debe existir al menos uno."
        )
    
    # Soft delete - solo marcar como inactivo
    servicio.is_active = False
    servicio.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Servicio eliminado"}


@router.post("/reorder")
async def reorder_servicios(
    order: List[str],  # Lista de IDs en el nuevo orden
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reordenar servicios médicos"""
    for index, servicio_id in enumerate(order):
        servicio = db.query(ServicioMedico).filter(
            ServicioMedico.id == servicio_id,
            ServicioMedico.user_id == current_user.id
        ).first()
        
        if servicio:
            servicio.display_order = index
            servicio.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {"message": "Orden actualizado"}


# Estadísticas de servicios
@router.get("/stats")
async def get_servicios_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener estadísticas de servicios"""
    service = ServiciosService(db)
    stats = service.get_servicios_statistics(current_user.id)
    
    return stats


# Capacidad con servicios
@router.get("/capacidad")
async def get_capacidad_con_servicios(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener capacidad semanal considerando los servicios configurados"""
    service = CapacidadService(db)
    capacidad = service.calcular_capacidad_semanal(current_user.id)
    
    return capacidad


# Get consultorios for service configuration
@router.get("/consultorios")
async def get_consultorios_for_services(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener consultorios activos para configurar servicios"""
    consultorios = db.query(Consultorio).filter(
        Consultorio.user_id == current_user.id,
        Consultorio.activo == True
    ).order_by(
        Consultorio.es_principal.desc(),
        Consultorio.nombre
    ).all()
    
    return {
        "consultorios": [
            {
                "id": str(c.id),
                "nombre": c.nombre,
                "es_principal": c.es_principal,
                "direccion_corta": f"{c.calle} {c.numero}, {c.ciudad}",
                "foto": c.foto_principal
            } for c in consultorios
        ]
    }