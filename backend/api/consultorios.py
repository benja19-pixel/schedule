from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict
from datetime import datetime
import uuid
import json
import base64
from database.connection import get_db
from models.user import User
from models.consultorio import Consultorio, ensure_single_principal, generate_default_color, validate_accesibilidad, count_active_for_user, validate_principal_status
from api.auth import get_current_user
from services.geocoding_service import GeocodingService
import os

router = APIRouter()

# Pydantic models for requests/responses
class ConsultorioCreateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=255)
    es_principal: bool = False
    pais: str = Field(..., min_length=1, max_length=100)
    estado: str = Field(..., min_length=1, max_length=100)
    ciudad: str = Field(..., min_length=1, max_length=100)
    calle: str = Field(..., min_length=1, max_length=255)
    numero: str = Field(..., min_length=1, max_length=50)
    colonia: Optional[str] = Field(None, max_length=100)
    codigo_postal: str = Field(..., min_length=1, max_length=20)
    notas: Optional[str] = None
    tiene_estacionamiento: bool = False
    accesibilidad: str = 'todos'
    telefono_consultorio: Optional[str] = None
    email_consultorio: Optional[str] = None
    usa_telefono_virtual: bool = False
    # Manual marker coordinates (if user adjusted)
    marcador_latitud: Optional[float] = None
    marcador_longitud: Optional[float] = None
    
    @validator('accesibilidad')
    def validate_accesibilidad_field(cls, v):
        return validate_accesibilidad(v)

class ConsultorioUpdateRequest(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=255)
    es_principal: Optional[bool] = None
    pais: Optional[str] = Field(None, min_length=1, max_length=100)
    estado: Optional[str] = Field(None, min_length=1, max_length=100)
    ciudad: Optional[str] = Field(None, min_length=1, max_length=100)
    calle: Optional[str] = Field(None, min_length=1, max_length=255)
    numero: Optional[str] = Field(None, min_length=1, max_length=50)
    colonia: Optional[str] = None
    codigo_postal: Optional[str] = Field(None, min_length=1, max_length=20)
    notas: Optional[str] = None
    tiene_estacionamiento: Optional[bool] = None
    accesibilidad: Optional[str] = None
    telefono_consultorio: Optional[str] = None
    email_consultorio: Optional[str] = None
    usa_telefono_virtual: Optional[bool] = None
    # Manual marker coordinates (if user adjusted)
    marcador_latitud: Optional[float] = None
    marcador_longitud: Optional[float] = None
    
    @validator('accesibilidad')
    def validate_accesibilidad_field(cls, v):
        if v is not None:
            return validate_accesibilidad(v)
        return v

class PhotoUploadResponse(BaseModel):
    url: str
    thumbnail: str
    color: Optional[str] = None

# Helper function to generate Google Maps URL from coordinates
def generate_maps_url_from_coords(lat: float, lng: float) -> str:
    """Generate Google Maps URL from coordinates"""
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"

# Endpoints
@router.get("/")
async def get_consultorios(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    include_inactive: bool = Query(False)
):
    """Obtener todos los consultorios del usuario"""
    query = db.query(Consultorio).filter(Consultorio.user_id == current_user.id)
    
    if not include_inactive:
        query = query.filter(Consultorio.activo == True)
    
    consultorios = query.order_by(
        Consultorio.es_principal.desc(),
        Consultorio.nombre
    ).all()
    
    return {
        "consultorios": [c.to_dict() for c in consultorios],
        "total": len(consultorios)
    }

@router.get("/{consultorio_id}")
async def get_consultorio(
    consultorio_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener un consultorio específico"""
    consultorio = db.query(Consultorio).filter(
        Consultorio.id == consultorio_id,
        Consultorio.user_id == current_user.id
    ).first()
    
    if not consultorio:
        raise HTTPException(status_code=404, detail="Consultorio no encontrado")
    
    return consultorio.to_dict()

@router.post("/")
async def create_consultorio(
    request: ConsultorioCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear un nuevo consultorio"""
    
    # Check if this is the first consultorio
    existing_count = count_active_for_user(db, current_user.id)
    is_first_consultorio = existing_count == 0
    
    # Initialize geocoding service
    geocoding_service = GeocodingService()
    
    # Check if user provided manual marker coordinates
    if request.marcador_latitud is not None and request.marcador_longitud is not None:
        # User adjusted the marker - use those coordinates
        lat = request.marcador_latitud
        lng = request.marcador_longitud
        maps_url = generate_maps_url_from_coords(lat, lng)
        marcador_ajustado = True
        
        # Still build the formatted address from form fields
        full_address = f"{request.calle} {request.numero}, "
        if request.colonia:
            full_address += f"{request.colonia}, "
        full_address += f"{request.ciudad}, {request.estado}, {request.codigo_postal}, {request.pais}"
        formatted_address = full_address
    else:
        # No manual adjustment - geocode the address
        full_address = f"{request.calle} {request.numero}, "
        if request.colonia:
            full_address += f"{request.colonia}, "
        full_address += f"{request.ciudad}, {request.estado}, {request.codigo_postal}, {request.pais}"
        
        # Get coordinates and Google Maps URL
        location_data = await geocoding_service.geocode_address(full_address)
        
        if location_data:
            lat = location_data.get('lat')
            lng = location_data.get('lng')
            maps_url = location_data.get('maps_url')
            formatted_address = location_data.get('formatted_address', full_address)
        else:
            lat = None
            lng = None
            maps_url = None
            formatted_address = full_address
        
        marcador_ajustado = False
    
    # FIXED: Handle principal status correctly
    if is_first_consultorio:
        # First consultorio MUST be principal
        es_principal = True
        message_suffix = " (establecido como principal automáticamente)"
    else:
        # Not first consultorio
        es_principal = request.es_principal
        message_suffix = ""
        
        # If setting as principal, ensure no other is principal
        if es_principal:
            ensure_single_principal(db, current_user.id, None)
    
    # Create consultorio
    consultorio = Consultorio(
        user_id=current_user.id,
        nombre=request.nombre,
        es_principal=es_principal,
        pais=request.pais,
        estado=request.estado,
        ciudad=request.ciudad,
        calle=request.calle,
        numero=request.numero,
        colonia=request.colonia,
        codigo_postal=request.codigo_postal,
        latitud=lat,
        longitud=lng,
        google_maps_url=maps_url,
        direccion_completa=formatted_address,
        marcador_ajustado=marcador_ajustado,
        notas=request.notas,
        tiene_estacionamiento=request.tiene_estacionamiento,
        accesibilidad=request.accesibilidad,
        telefono_consultorio=request.telefono_consultorio if not request.usa_telefono_virtual else None,
        usa_telefono_virtual=request.usa_telefono_virtual,
        email_consultorio=request.email_consultorio,
        foto_principal={"color": generate_default_color()}  # Start with default color
    )
    
    db.add(consultorio)
    db.commit()
    db.refresh(consultorio)
    
    # FIXED: Ensure single principal after creation
    if es_principal:
        ensure_single_principal(db, current_user.id, consultorio.id)
    
    return {
        "message": f"Consultorio creado exitosamente{message_suffix}",
        "consultorio": consultorio.to_dict(),
        "is_first": is_first_consultorio
    }

@router.put("/{consultorio_id}")
async def update_consultorio(
    consultorio_id: str,
    request: ConsultorioUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Actualizar un consultorio existente"""
    consultorio = db.query(Consultorio).filter(
        Consultorio.id == consultorio_id,
        Consultorio.user_id == current_user.id
    ).first()
    
    if not consultorio:
        raise HTTPException(status_code=404, detail="Consultorio no encontrado")
    
    # FIXED: Better validation for principal status changes
    if request.es_principal is not None:
        # Validate the change
        is_valid, error_msg = validate_principal_status(
            db, current_user.id, consultorio_id, request.es_principal
        )
        
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
    
    # Check if user provided manual marker coordinates
    if request.marcador_latitud is not None and request.marcador_longitud is not None:
        # User adjusted the marker - use those coordinates
        consultorio.latitud = request.marcador_latitud
        consultorio.longitud = request.marcador_longitud
        consultorio.google_maps_url = generate_maps_url_from_coords(
            request.marcador_latitud, 
            request.marcador_longitud
        )
        consultorio.marcador_ajustado = True
        
        # Update address fields if provided
        address_fields = ['pais', 'estado', 'ciudad', 'calle', 'numero', 'colonia', 'codigo_postal']
        for field in address_fields:
            new_value = getattr(request, field, None)
            if new_value is not None:
                setattr(consultorio, field, new_value)
        
        # Build formatted address from fields
        full_address = f"{consultorio.calle} {consultorio.numero}, "
        if consultorio.colonia:
            full_address += f"{consultorio.colonia}, "
        full_address += f"{consultorio.ciudad}, {consultorio.estado}, {consultorio.codigo_postal}, {consultorio.pais}"
        consultorio.direccion_completa = full_address
        
    else:
        # Check if address fields are being updated
        address_updated = False
        address_fields = ['pais', 'estado', 'ciudad', 'calle', 'numero', 'colonia', 'codigo_postal']
        
        for field in address_fields:
            new_value = getattr(request, field, None)
            if new_value is not None and new_value != getattr(consultorio, field):
                address_updated = True
                setattr(consultorio, field, new_value)
        
        # If address was updated, re-geocode
        if address_updated:
            geocoding_service = GeocodingService()
            
            # Build new full address
            full_address = f"{consultorio.calle} {consultorio.numero}, "
            if consultorio.colonia:
                full_address += f"{consultorio.colonia}, "
            full_address += f"{consultorio.ciudad}, {consultorio.estado}, {consultorio.codigo_postal}, {consultorio.pais}"
            
            location_data = await geocoding_service.geocode_address(full_address)
            
            if location_data:
                consultorio.latitud = location_data.get('lat')
                consultorio.longitud = location_data.get('lng')
                consultorio.google_maps_url = location_data.get('maps_url')
                consultorio.direccion_completa = location_data.get('formatted_address')
                consultorio.marcador_ajustado = False
    
    # Update other fields
    update_fields = ['nombre', 'notas', 'tiene_estacionamiento', 'accesibilidad', 'email_consultorio']
    
    for field in update_fields:
        value = getattr(request, field, None)
        if value is not None:
            setattr(consultorio, field, value)
    
    # Handle phone fields
    if request.usa_telefono_virtual is not None:
        consultorio.usa_telefono_virtual = request.usa_telefono_virtual
        if request.usa_telefono_virtual:
            consultorio.telefono_consultorio = None
        elif request.telefono_consultorio is not None:
            consultorio.telefono_consultorio = request.telefono_consultorio
    elif request.telefono_consultorio is not None:
        consultorio.telefono_consultorio = request.telefono_consultorio
        consultorio.usa_telefono_virtual = False
    
    # FIXED: Handle es_principal with proper single principal enforcement
    if request.es_principal is not None:
        old_principal_status = consultorio.es_principal
        consultorio.es_principal = request.es_principal
        
        if request.es_principal and not old_principal_status:
            # Setting this as principal, unset all others
            ensure_single_principal(db, current_user.id, consultorio_id)
        elif not request.es_principal and old_principal_status:
            # Unsetting principal, assign to another
            db.commit()  # Save current changes first
            ensure_single_principal(db, current_user.id, None)
    
    consultorio.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(consultorio)
    
    return {
        "message": "Consultorio actualizado exitosamente",
        "consultorio": consultorio.to_dict()
    }

@router.delete("/{consultorio_id}")
async def delete_consultorio(
    consultorio_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eliminar un consultorio (soft delete)"""
    consultorio = db.query(Consultorio).filter(
        Consultorio.id == consultorio_id,
        Consultorio.user_id == current_user.id
    ).first()
    
    if not consultorio:
        raise HTTPException(status_code=404, detail="Consultorio no encontrado")
    
    # Don't allow deleting the only consultorio
    active_count = count_active_for_user(db, current_user.id)
    
    if active_count <= 1:
        raise HTTPException(
            status_code=400, 
            detail="No puedes eliminar tu único consultorio activo. Debes tener al menos un consultorio."
        )
    
    # FIXED: If deleting principal, properly assign to another
    if consultorio.es_principal:
        # First mark this one as not principal
        consultorio.es_principal = False
        # Then soft delete
        consultorio.activo = False
        consultorio.updated_at = datetime.utcnow()
        db.commit()
        
        # Now ensure another one becomes principal
        ensure_single_principal(db, current_user.id, None)
    else:
        # Just soft delete
        consultorio.activo = False
        consultorio.updated_at = datetime.utcnow()
        db.commit()
    
    return {"message": "Consultorio eliminado exitosamente"}

@router.post("/{consultorio_id}/foto-principal")
async def upload_foto_principal(
    consultorio_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Subir foto principal del consultorio"""
    consultorio = db.query(Consultorio).filter(
        Consultorio.id == consultorio_id,
        Consultorio.user_id == current_user.id
    ).first()
    
    if not consultorio:
        raise HTTPException(status_code=404, detail="Consultorio no encontrado")
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Tipo de archivo no permitido")
    
    # Read file content
    content = await file.read()
    
    # Convert to base64 for storage (in production, use cloud storage)
    base64_image = base64.b64encode(content).decode('utf-8')
    data_url = f"data:{file.content_type};base64,{base64_image}"
    
    # Update consultorio
    consultorio.foto_principal = {
        "url": data_url,
        "thumbnail": data_url,  # In production, generate actual thumbnail
        "color": generate_default_color(),
        "filename": file.filename,
        "uploaded_at": datetime.utcnow().isoformat()
    }
    
    db.commit()
    db.refresh(consultorio)
    
    return {
        "message": "Foto principal actualizada",
        "foto": consultorio.foto_principal
    }

@router.delete("/{consultorio_id}/foto-principal")
async def delete_foto_principal(
    consultorio_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eliminar foto principal del consultorio"""
    consultorio = db.query(Consultorio).filter(
        Consultorio.id == consultorio_id,
        Consultorio.user_id == current_user.id
    ).first()
    
    if not consultorio:
        raise HTTPException(status_code=404, detail="Consultorio no encontrado")
    
    # Reset to default color
    consultorio.foto_principal = {"color": generate_default_color()}
    
    db.commit()
    
    return {"message": "Foto principal eliminada"}

@router.post("/{consultorio_id}/fotos-secundarias")
async def upload_foto_secundaria(
    consultorio_id: str,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Agregar foto secundaria al consultorio"""
    consultorio = db.query(Consultorio).filter(
        Consultorio.id == consultorio_id,
        Consultorio.user_id == current_user.id
    ).first()
    
    if not consultorio:
        raise HTTPException(status_code=404, detail="Consultorio no encontrado")
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Tipo de archivo no permitido")
    
    # Limit number of secondary photos
    current_photos = consultorio.fotos_secundarias or []
    if len(current_photos) >= 10:
        raise HTTPException(status_code=400, detail="Máximo 10 fotos secundarias permitidas")
    
    # Read file content
    content = await file.read()
    
    # Convert to base64
    base64_image = base64.b64encode(content).decode('utf-8')
    data_url = f"data:{file.content_type};base64,{base64_image}"
    
    # Add to secondary photos
    new_photo = {
        "id": str(uuid.uuid4()),
        "url": data_url,
        "thumbnail": data_url,
        "caption": caption,
        "filename": file.filename,
        "uploaded_at": datetime.utcnow().isoformat()
    }
    
    current_photos.append(new_photo)
    consultorio.fotos_secundarias = current_photos
    
    db.commit()
    
    return {
        "message": "Foto secundaria agregada",
        "foto": new_photo
    }

@router.delete("/{consultorio_id}/fotos-secundarias/{foto_id}")
async def delete_foto_secundaria(
    consultorio_id: str,
    foto_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eliminar una foto secundaria específica"""
    consultorio = db.query(Consultorio).filter(
        Consultorio.id == consultorio_id,
        Consultorio.user_id == current_user.id
    ).first()
    
    if not consultorio:
        raise HTTPException(status_code=404, detail="Consultorio no encontrado")
    
    current_photos = consultorio.fotos_secundarias or []
    updated_photos = [p for p in current_photos if p.get('id') != foto_id]
    
    if len(current_photos) == len(updated_photos):
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    
    consultorio.fotos_secundarias = updated_photos
    db.commit()
    
    return {"message": "Foto secundaria eliminada"}

@router.get("/principal/info")
async def get_consultorio_principal(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener información del consultorio principal"""
    consultorio = Consultorio.get_principal_for_user(db, current_user.id)
    
    if not consultorio:
        # Return more informative response
        return {
            "consultorio_principal": None,
            "message": "No hay consultorio principal configurado"
        }
    
    return {"consultorio_principal": consultorio.to_dict()}

@router.put("/{consultorio_id}/set-principal")
async def set_consultorio_principal(
    consultorio_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Establecer un consultorio como principal"""
    consultorio = db.query(Consultorio).filter(
        Consultorio.id == consultorio_id,
        Consultorio.user_id == current_user.id,
        Consultorio.activo == True
    ).first()
    
    if not consultorio:
        raise HTTPException(status_code=404, detail="Consultorio no encontrado o inactivo")
    
    # FIXED: Properly set as principal ensuring only one
    ensure_single_principal(db, current_user.id, consultorio_id)
    
    # Refresh to get updated status
    db.refresh(consultorio)
    
    return {
        "message": "Consultorio establecido como principal",
        "consultorio": consultorio.to_dict()
    }