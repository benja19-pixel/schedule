from sqlalchemy import Column, String, DateTime, Boolean, Integer, ForeignKey, Text, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from database.connection import Base


class TipoPrecio(enum.Enum):
    """Tipos de precio para servicios"""
    PRECIO_FIJO = "precio_fijo"
    PRECIO_POR_EVALUAR = "precio_por_evaluar"  # El doctor evalúa en consulta
    GRATIS = "gratis"
    PRECIO_VARIABLE = "precio_variable"  # Rango de precios


class ServicioMedico(Base):
    """Servicios médicos que ofrece el doctor"""
    __tablename__ = "servicios_medicos"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Consultorio donde se ofrece el servicio
    consultorio_id = Column(UUID(as_uuid=True), ForeignKey("consultorios.id"), nullable=True)
    
    # Información básica del servicio
    nombre = Column(String(100), nullable=False)
    descripcion = Column(Text, nullable=False)  # Obligatoria y precisa
    
    # Duración y consultas
    duracion_minutos = Column(Integer, nullable=False)  # 15 a 180 minutos (3 horas)
    cantidad_consultas = Column(Integer, default=1, nullable=False)  # 1, 2, 3, etc.
    
    # Configuración de precio
    tipo_precio = Column(Enum(TipoPrecio), default=TipoPrecio.PRECIO_FIJO, nullable=False)
    precio = Column(Integer, nullable=True)  # En centavos (null si es por_evaluar o gratis)
    precio_minimo = Column(Integer, nullable=True)  # Para precio variable
    precio_maximo = Column(Integer, nullable=True)  # Para precio variable
    
    # Instrucciones para IA Secretaria
    instrucciones_ia = Column(Text, nullable=True)
    # Ej: "Agendar cuando el paciente mencione dolor crónico o necesite evaluación inicial"
    
    # Visual y orden
    color = Column(String(7), default="#3B82F6")  # Hex color para UI
    display_order = Column(Integer, default=0)
    
    # Estado
    is_active = Column(Boolean, default=True)
    
    # Doctores que atienden este servicio (lista de nombres)
    doctores_atienden = Column(JSON, nullable=True, default=list)
    # Format: ["Dr. Juan Pérez", "Dra. María García"]
    
    # Instrucciones para el paciente (se envían al confirmar cita)
    instrucciones_paciente = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="servicios_medicos")
    consultorio = relationship("Consultorio", backref="servicios_ofrecidos")
    
    @property
    def precio_display(self):
        """Retorna el precio formateado para mostrar"""
        if self.tipo_precio == TipoPrecio.GRATIS:
            return "Gratis"
        elif self.tipo_precio == TipoPrecio.PRECIO_POR_EVALUAR:
            return "A evaluar en consulta"
        elif self.tipo_precio == TipoPrecio.PRECIO_VARIABLE:
            min_precio = f"${self.precio_minimo/100:.2f}" if self.precio_minimo else "?"
            max_precio = f"${self.precio_maximo/100:.2f}" if self.precio_maximo else "?"
            return f"{min_precio} - {max_precio}"
        elif self.precio:
            return f"${self.precio/100:.2f}"
        return "Sin definir"
    
    @property
    def duracion_display(self):
        """Retorna la duración formateada"""
        horas = self.duracion_minutos // 60
        minutos = self.duracion_minutos % 60
        
        if horas > 0 and minutos > 0:
            return f"{horas}h {minutos}min"
        elif horas > 0:
            return f"{horas} hora{'s' if horas > 1 else ''}"
        else:
            return f"{minutos} minutos"
    
    @property
    def consultas_display(self):
        """Retorna el número de consultas formateado"""
        if self.cantidad_consultas == 1:
            return "1 consulta"
        else:
            return f"{self.cantidad_consultas} consultas"
    
    @property
    def doctores_display(self):
        """Retorna los doctores formateados"""
        if not self.doctores_atienden or len(self.doctores_atienden) == 0:
            return "No especificado"
        elif len(self.doctores_atienden) == 1:
            return self.doctores_atienden[0]
        elif len(self.doctores_atienden) == 2:
            return f"{self.doctores_atienden[0]} y {self.doctores_atienden[1]}"
        else:
            return f"{', '.join(self.doctores_atienden[:-1])} y {self.doctores_atienden[-1]}"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": str(self.id),
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "duracion_minutos": self.duracion_minutos,
            "duracion_display": self.duracion_display,
            "cantidad_consultas": self.cantidad_consultas,
            "consultas_display": self.consultas_display,
            "tipo_precio": self.tipo_precio.value,
            "precio": self.precio,
            "precio_minimo": self.precio_minimo,
            "precio_maximo": self.precio_maximo,
            "precio_display": self.precio_display,
            "instrucciones_ia": self.instrucciones_ia,
            "instrucciones_paciente": self.instrucciones_paciente,
            "color": self.color,
            "display_order": self.display_order,
            "consultorio_id": str(self.consultorio_id) if self.consultorio_id else None,
            "consultorio": self.consultorio.to_dict() if self.consultorio else None,
            "doctores_atienden": self.doctores_atienden or [],
            "doctores_display": self.doctores_display,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


# Helper functions
def get_color_for_service(index: int) -> str:
    """Retorna un color predefinido para nuevos servicios"""
    colors = [
        '#9333ea',  # Purple
        '#0284c7',  # Blue
        '#16a34a',  # Green
        '#dc2626',  # Red
        '#f59e0b',  # Amber
        '#ec4899',  # Pink
        '#6366f1',  # Indigo
        '#14b8a6',  # Teal
        '#f97316',  # Orange
        '#8b5cf6'   # Violet
    ]
    return colors[index % len(colors)]


def validate_service_duration(duration: int) -> bool:
    """Valida que la duración esté en el rango permitido"""
    return 15 <= duration <= 180  # 15 minutos a 3 horas


def calculate_slots_per_service(duration_minutes: int, cantidad_consultas: int) -> float:
    """Calcula cuántos slots de tiempo consume un servicio"""
    # Cada consulta ocupa el tiempo especificado
    return (duration_minutes * cantidad_consultas) / 30  # Basado en slots de 30 min