from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from models.servicios import ServicioMedico, TipoPrecio
from models.user import User

class ServiciosService:
    """Servicio para gestión de servicios médicos"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_all_servicios(self, user_id: str, include_inactive: bool = False) -> List[ServicioMedico]:
        """
        Obtener todos los servicios médicos de un usuario
        """
        query = self.db.query(ServicioMedico).filter(
            ServicioMedico.user_id == user_id
        )
        
        if not include_inactive:
            query = query.filter(ServicioMedico.is_active == True)
        
        return query.order_by(
            ServicioMedico.display_order,
            ServicioMedico.created_at
        ).all()
    
    def get_servicio_by_id(self, servicio_id: str, user_id: str) -> Optional[ServicioMedico]:
        """
        Obtener un servicio específico por ID
        """
        return self.db.query(ServicioMedico).filter(
            ServicioMedico.id == servicio_id,
            ServicioMedico.user_id == user_id
        ).first()
    
    def get_servicios_for_ai(self, user_id: str) -> List[Dict]:
        """
        Obtener servicios formateados para la IA Secretaria
        """
        servicios = self.get_all_servicios(user_id)
        
        ai_servicios = []
        for servicio in servicios:
            ai_data = {
                "id": str(servicio.id),
                "nombre": servicio.nombre,
                "descripcion": servicio.descripcion,
                "duracion_minutos": servicio.duracion_minutos,
                "precio": servicio.precio_display,
                "instrucciones_ia": servicio.instrucciones_ia or "Sin instrucciones específicas"
            }
            
            # Agregar contexto adicional para la IA
            if servicio.cantidad_consultas > 1:
                ai_data["nota_importante"] = f"Este servicio requiere {servicio.cantidad_consultas} consultas"
            
            if servicio.requiere_preparacion:
                ai_data["preparacion"] = f"Requiere {servicio.tiempo_preparacion} minutos de preparación"
            
            ai_servicios.append(ai_data)
        
        return ai_servicios
    
    def get_servicios_statistics(self, user_id: str) -> Dict:
        """
        Obtener estadísticas de los servicios
        """
        servicios = self.get_all_servicios(user_id)
        
        if not servicios:
            return {
                "total_servicios": 0,
                "duracion_promedio": 0,
                "servicio_mas_corto": None,
                "servicio_mas_largo": None,
                "tipos_precio": {},
                "requieren_preparacion": 0
            }
        
        duraciones = [s.duracion_minutos for s in servicios]
        tipos_precio = {}
        requieren_prep = 0
        
        for servicio in servicios:
            # Contar tipos de precio
            tipo = servicio.tipo_precio.value
            tipos_precio[tipo] = tipos_precio.get(tipo, 0) + 1
            
            # Contar los que requieren preparación
            if servicio.requiere_preparacion:
                requieren_prep += 1
        
        # Encontrar servicio más corto y más largo
        servicio_corto = min(servicios, key=lambda s: s.duracion_minutos)
        servicio_largo = max(servicios, key=lambda s: s.duracion_minutos)
        
        return {
            "total_servicios": len(servicios),
            "duracion_promedio": round(sum(duraciones) / len(duraciones), 0),
            "servicio_mas_corto": {
                "nombre": servicio_corto.nombre,
                "duracion": servicio_corto.duracion_display
            },
            "servicio_mas_largo": {
                "nombre": servicio_largo.nombre,
                "duracion": servicio_largo.duracion_display
            },
            "tipos_precio": tipos_precio,
            "requieren_preparacion": requieren_prep
        }
    
    def validate_servicio_name_unique(self, user_id: str, nombre: str, exclude_id: Optional[str] = None) -> bool:
        """
        Validar que el nombre del servicio sea único para el usuario
        """
        query = self.db.query(ServicioMedico).filter(
            ServicioMedico.user_id == user_id,
            ServicioMedico.nombre == nombre,
            ServicioMedico.is_active == True
        )
        
        if exclude_id:
            query = query.filter(ServicioMedico.id != exclude_id)
        
        return query.first() is None
    
    def calculate_service_capacity(self, servicio: ServicioMedico, available_minutes: int) -> int:
        """
        Calcular cuántas veces cabe un servicio en el tiempo disponible
        """
        if servicio.duracion_minutos == 0:
            return 0
        
        # Considerar el tiempo de preparación si es necesario
        tiempo_total = servicio.duracion_minutos
        if servicio.requiere_preparacion:
            tiempo_total += servicio.tiempo_preparacion
        
        # Considerar la cantidad de consultas
        tiempo_total *= servicio.cantidad_consultas
        
        return available_minutes // tiempo_total
    
    def get_price_range_for_user(self, user_id: str) -> Dict:
        """
        Obtener rango de precios de todos los servicios del usuario
        """
        servicios = self.get_all_servicios(user_id)
        
        precios_fijos = []
        precios_minimos = []
        precios_maximos = []
        
        for servicio in servicios:
            if servicio.tipo_precio == TipoPrecio.PRECIO_FIJO and servicio.precio:
                precios_fijos.append(servicio.precio)
            elif servicio.tipo_precio == TipoPrecio.PRECIO_VARIABLE:
                if servicio.precio_minimo:
                    precios_minimos.append(servicio.precio_minimo)
                if servicio.precio_maximo:
                    precios_maximos.append(servicio.precio_maximo)
        
        todos_precios = precios_fijos + precios_minimos + precios_maximos
        
        if not todos_precios:
            return {
                "min_precio": None,
                "max_precio": None,
                "precio_promedio": None,
                "tiene_gratis": any(s.tipo_precio == TipoPrecio.GRATIS for s in servicios),
                "tiene_por_evaluar": any(s.tipo_precio == TipoPrecio.PRECIO_POR_EVALUAR for s in servicios)
            }
        
        return {
            "min_precio": min(todos_precios),
            "max_precio": max(todos_precios),
            "precio_promedio": round(sum(todos_precios) / len(todos_precios), 0),
            "tiene_gratis": any(s.tipo_precio == TipoPrecio.GRATIS for s in servicios),
            "tiene_por_evaluar": any(s.tipo_precio == TipoPrecio.PRECIO_POR_EVALUAR for s in servicios)
        }
    
    def suggest_service_for_patient(self, user_id: str, patient_description: str) -> Optional[Dict]:
        """
        Sugerir un servicio basado en la descripción del paciente
        (Para futura integración con IA)
        """
        servicios = self.get_all_servicios(user_id)
        
        # Por ahora, buscar coincidencias simples en instrucciones_ia
        # En el futuro, esto usará IA para matching más inteligente
        
        patient_lower = patient_description.lower()
        
        for servicio in servicios:
            if servicio.instrucciones_ia:
                instrucciones_lower = servicio.instrucciones_ia.lower()
                
                # Buscar palabras clave comunes
                keywords = ["nuevo", "primera vez", "inicial", "evaluación", "urgente", "emergencia", 
                           "seguimiento", "control", "revisión"]
                
                for keyword in keywords:
                    if keyword in patient_lower and keyword in instrucciones_lower:
                        return {
                            "servicio_id": str(servicio.id),
                            "nombre": servicio.nombre,
                            "razon": f"Coincide con criterio: {keyword}",
                            "confianza": 70  # Porcentaje de confianza
                        }
        
        # Si no hay coincidencia, sugerir el servicio más común (primer servicio)
        if servicios:
            return {
                "servicio_id": str(servicios[0].id),
                "nombre": servicios[0].nombre,
                "razon": "Servicio por defecto",
                "confianza": 30
            }
        
        return None