from sqlalchemy import Column, String, DateTime, Boolean, JSON, ForeignKey, Float, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from database.connection import Base


class Consultorio(Base):
    """Modelo para gestionar consultorios/sedes médicas"""
    __tablename__ = "consultorios"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Basic information
    nombre = Column(String(255), nullable=False)
    es_principal = Column(Boolean, default=False)
    
    # Address fields
    pais = Column(String(100), nullable=False)
    estado = Column(String(100), nullable=False)
    ciudad = Column(String(100), nullable=False)
    calle = Column(String(255), nullable=False)
    numero = Column(String(50), nullable=False)
    colonia = Column(String(100), nullable=True)
    codigo_postal = Column(String(20), nullable=False)
    
    # Geolocation
    latitud = Column(Float, nullable=True)
    longitud = Column(Float, nullable=True)
    google_maps_url = Column(Text, nullable=True)
    direccion_completa = Column(Text, nullable=True)  # Formatted full address
    
    # Marker adjustment flag
    marcador_ajustado = Column(Boolean, default=False)  # True if user manually adjusted marker
    
    # Photos
    foto_principal = Column(JSON, nullable=True)
    # Format: {"url": "...", "thumbnail": "...", "color": "#hexcolor"}
    fotos_secundarias = Column(JSON, nullable=True, default=list)
    # Format: [{"url": "...", "thumbnail": "...", "caption": "..."}]
    
    # Extra optional fields
    notas = Column(Text, nullable=True)
    tiene_estacionamiento = Column(Boolean, default=False)
    accesibilidad = Column(String(50), default='todos')
    # Options: 'todos', 'con_discapacidad', 'sin_discapacidad', 'limitada'
    
    # Facilities (for future expansion)
    servicios_adicionales = Column(JSON, nullable=True, default=dict)
    # Format: {"wifi": true, "sala_espera": true, "aire_acondicionado": true, etc}
    
    # Contact info specific to this location
    telefono_consultorio = Column(String(20), nullable=True)
    email_consultorio = Column(String(255), nullable=True)
    usa_telefono_virtual = Column(Boolean, default=False)  # Use virtual secretary phone
    
    # Working hours specific to this location (optional override)
    horario_especifico = Column(JSON, nullable=True)
    
    # Status
    activo = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="consultorios")
    
    def to_dict(self):
        """Convert consultorio to dictionary for API responses"""
        return {
            "id": str(self.id),
            "nombre": self.nombre,
            "es_principal": self.es_principal,
            "pais": self.pais,
            "estado": self.estado,
            "ciudad": self.ciudad,
            "calle": self.calle,
            "numero": self.numero,
            "colonia": self.colonia,
            "codigo_postal": self.codigo_postal,
            "latitud": self.latitud,
            "longitud": self.longitud,
            "google_maps_url": self.google_maps_url,
            "direccion_completa": self.direccion_completa,
            "marcador_ajustado": self.marcador_ajustado,
            "foto_principal": self.foto_principal,
            "fotos_secundarias": self.fotos_secundarias or [],
            "notas": self.notas,
            "tiene_estacionamiento": self.tiene_estacionamiento,
            "accesibilidad": self.accesibilidad,
            "servicios_adicionales": self.servicios_adicionales or {},
            "telefono_consultorio": self.telefono_consultorio,
            "email_consultorio": self.email_consultorio,
            "usa_telefono_virtual": self.usa_telefono_virtual,
            "horario_especifico": self.horario_especifico,
            "activo": self.activo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_display_address(self):
        """Get formatted address for display"""
        parts = [
            f"{self.calle} {self.numero}",
            self.colonia,
            f"{self.ciudad}, {self.estado}",
            f"C.P. {self.codigo_postal}",
            self.pais
        ]
        return ", ".join(filter(None, parts))
    
    def get_short_address(self):
        """Get short version of address"""
        return f"{self.calle} {self.numero}, {self.ciudad}"
    
    @classmethod
    def get_principal_for_user(cls, db, user_id):
        """Get the principal consultorio for a user"""
        return db.query(cls).filter(
            cls.user_id == user_id,
            cls.es_principal == True,
            cls.activo == True
        ).first()
    
    @classmethod
    def get_active_for_user(cls, db, user_id):
        """Get all active consultorios for a user"""
        return db.query(cls).filter(
            cls.user_id == user_id,
            cls.activo == True
        ).order_by(cls.es_principal.desc(), cls.nombre).all()


# Helper functions
def ensure_single_principal(db, user_id, consultorio_id=None):
    """
    FIXED: Ensure only one consultorio is marked as principal for a user
    Always maintains exactly one principal consultorio
    """
    if consultorio_id:
        # First, unset all other consultorios as principal
        db.query(Consultorio).filter(
            Consultorio.user_id == user_id,
            Consultorio.id != consultorio_id,
            Consultorio.activo == True
        ).update({"es_principal": False})
        
        # Ensure the specified consultorio is set as principal
        db.query(Consultorio).filter(
            Consultorio.id == consultorio_id,
            Consultorio.user_id == user_id
        ).update({"es_principal": True})
        
    else:
        # Check if there's any principal consultorio
        principal_exists = db.query(Consultorio).filter(
            Consultorio.user_id == user_id,
            Consultorio.es_principal == True,
            Consultorio.activo == True
        ).first()
        
        if not principal_exists:
            # No principal exists, set the first active consultorio as principal
            first_active = db.query(Consultorio).filter(
                Consultorio.user_id == user_id,
                Consultorio.activo == True
            ).order_by(Consultorio.created_at).first()
            
            if first_active:
                first_active.es_principal = True
                db.add(first_active)
    
    # Final validation: ensure there's exactly one principal
    principals = db.query(Consultorio).filter(
        Consultorio.user_id == user_id,
        Consultorio.es_principal == True,
        Consultorio.activo == True
    ).all()
    
    if len(principals) > 1:
        # Multiple principals found, keep only the first one
        for i, principal in enumerate(principals):
            if i > 0:
                principal.es_principal = False
                db.add(principal)
    
    db.commit()


def count_active_for_user(db, user_id):
    """
    Count active consultorios for a user
    Helper function to check consultorio count
    """
    return db.query(Consultorio).filter(
        Consultorio.user_id == user_id,
        Consultorio.activo == True
    ).count()


def validate_principal_status(db, user_id, consultorio_id, new_principal_status):
    """
    Validate if principal status can be changed
    Returns (is_valid, error_message)
    """
    if not new_principal_status:
        # Trying to unset principal
        current_consultorio = db.query(Consultorio).filter(
            Consultorio.id == consultorio_id,
            Consultorio.user_id == user_id
        ).first()
        
        if current_consultorio and current_consultorio.es_principal:
            # Check if it's the only active consultorio
            active_count = count_active_for_user(db, user_id)
            
            if active_count == 1:
                return False, "No puedes quitar el estado principal del único consultorio activo"
            
            # Check if there's another consultorio that can be principal
            other_active = db.query(Consultorio).filter(
                Consultorio.user_id == user_id,
                Consultorio.id != consultorio_id,
                Consultorio.activo == True
            ).first()
            
            if not other_active:
                return False, "Debe existir al menos un consultorio principal activo"
    
    return True, None


def generate_default_color():
    """Generate a random default color for consultorio without photo"""
    import random
    colors = [
        "#6366f1",  # Indigo
        "#8b5cf6",  # Purple
        "#ec4899",  # Pink
        "#f43f5e",  # Rose
        "#f97316",  # Orange
        "#10b981",  # Emerald
        "#3b82f6",  # Blue
        "#06b6d4",  # Cyan
    ]
    return random.choice(colors)


def validate_accesibilidad(value):
    """Validate accessibility value"""
    valid_values = ['todos', 'con_discapacidad', 'sin_discapacidad', 'limitada']
    return value if value in valid_values else 'todos'