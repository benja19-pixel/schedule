from datetime import datetime, date, timedelta
from typing import Dict, List
from sqlalchemy.orm import Session
from models.horarios import HorarioTemplate, HorarioException, get_day_name  # Added import here
from models.servicios import ServicioMedico
from services.horarios_service import HorariosService
from services.servicios_service import ServiciosService

class CapacidadService:
    """
    Servicio compartido para calcular capacidad de atención
    basándose en horarios configurados y servicios disponibles
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.horarios_service = HorariosService(db)
        self.servicios_service = ServiciosService(db)
    
    def calcular_capacidad_semanal(self, user_id: str) -> Dict:
        """
        Calcular la capacidad semanal completa considerando
        horarios y tipos de servicios
        """
        # Obtener horarios semanales
        weekly_schedule = self.horarios_service.get_weekly_schedule(user_id)
        
        # Obtener servicios activos
        servicios = self.servicios_service.get_all_servicios(user_id)
        
        if not servicios:
            # Si no hay servicios, no se puede calcular capacidad
            return {
                "total_horas_semana": weekly_schedule["total_hours"],
                "dias_laborables": weekly_schedule["working_days"],
                "capacidad_min_citas": 0,
                "capacidad_max_citas": 0,
                "capacidad_display": "0 citas/sem",
                "mensaje": "Configura al menos un servicio para calcular capacidad",
                "detalles": {
                    "servicio_mas_corto": None,
                    "servicio_mas_largo": None,
                    "promedio_duracion": 0
                }
            }
        
        # Encontrar servicio más corto y más largo
        servicio_mas_corto = min(servicios, key=lambda s: s.duracion_minutos * s.cantidad_consultas)
        servicio_mas_largo = max(servicios, key=lambda s: s.duracion_minutos * s.cantidad_consultas)
        
        duracion_mas_corta = servicio_mas_corto.duracion_minutos * servicio_mas_corto.cantidad_consultas
        duracion_mas_larga = servicio_mas_largo.duracion_minutos * servicio_mas_largo.cantidad_consultas
        
        # Calcular minutos disponibles por semana
        total_minutos_semana = 0
        capacidad_por_dia = {}
        
        # Obtener templates de horario
        templates = self.db.query(HorarioTemplate).filter(
            HorarioTemplate.user_id == user_id,
            HorarioTemplate.is_active == True
        ).all()
        
        for template in templates:
            if template.opens_at and template.closes_at:
                # Obtener bloques de consulta para este día
                horario_dia = {
                    "is_working_day": True,
                    "opens_at": template.opens_at,
                    "closes_at": template.closes_at,
                    "time_blocks": template.time_blocks or []
                }
                
                consultation_blocks = self.horarios_service.get_consultation_blocks(horario_dia)
                
                # Sumar minutos de consulta disponibles
                minutos_dia = sum(block["duration_minutes"] for block in consultation_blocks)
                total_minutos_semana += minutos_dia
                
                # Calcular capacidad para este día
                if minutos_dia > 0:
                    min_citas_dia = minutos_dia // duracion_mas_larga
                    max_citas_dia = minutos_dia // duracion_mas_corta
                    
                    capacidad_por_dia[template.day_of_week] = {
                        "dia": get_day_name(template.day_of_week),  # Changed: now calling directly
                        "minutos_disponibles": minutos_dia,
                        "horas_disponibles": round(minutos_dia / 60, 1),
                        "capacidad_min": min_citas_dia,
                        "capacidad_max": max_citas_dia
                    }
        
        # Calcular capacidad total semanal
        capacidad_min_total = total_minutos_semana // duracion_mas_larga if duracion_mas_larga > 0 else 0
        capacidad_max_total = total_minutos_semana // duracion_mas_corta if duracion_mas_corta > 0 else 0
        
        # Formatear display de capacidad
        if capacidad_min_total == capacidad_max_total:
            capacidad_display = f"{capacidad_min_total} citas/sem"
        else:
            capacidad_display = f"{capacidad_min_total}-{capacidad_max_total} citas/sem"
        
        # Calcular promedio de duración
        promedio_duracion = sum(s.duracion_minutos for s in servicios) / len(servicios)
        
        return {
            "total_horas_semana": round(total_minutos_semana / 60, 1),
            "total_minutos_semana": total_minutos_semana,
            "dias_laborables": weekly_schedule["working_days"],
            "capacidad_min_citas": capacidad_min_total,
            "capacidad_max_citas": capacidad_max_total,
            "capacidad_display": capacidad_display,
            "capacidad_por_dia": capacidad_por_dia,
            "detalles": {
                "total_servicios": len(servicios),
                "servicio_mas_corto": {
                    "nombre": servicio_mas_corto.nombre,
                    "duracion": servicio_mas_corto.duracion_display,
                    "minutos_totales": duracion_mas_corta
                },
                "servicio_mas_largo": {
                    "nombre": servicio_mas_largo.nombre,
                    "duracion": servicio_mas_largo.duracion_display,
                    "minutos_totales": duracion_mas_larga
                },
                "promedio_duracion": round(promedio_duracion, 0)
            }
        }
    
    def calcular_capacidad_fecha(self, user_id: str, fecha: date) -> Dict:
        """
        Calcular capacidad para una fecha específica
        """
        # Obtener horario para la fecha
        horario = self.horarios_service.get_horario_for_date(user_id, fecha)
        
        if not horario.get("is_working_day"):
            return {
                "fecha": fecha.isoformat(),
                "es_dia_laboral": False,
                "capacidad_min": 0,
                "capacidad_max": 0,
                "razon": horario.get("reason", "Día no laboral")
            }
        
        # Obtener bloques de consulta
        consultation_blocks = self.horarios_service.get_consultation_blocks(horario)
        minutos_disponibles = sum(block["duration_minutes"] for block in consultation_blocks)
        
        # Obtener servicios
        servicios = self.servicios_service.get_all_servicios(user_id)
        
        if not servicios or minutos_disponibles == 0:
            return {
                "fecha": fecha.isoformat(),
                "es_dia_laboral": True,
                "minutos_disponibles": minutos_disponibles,
                "capacidad_min": 0,
                "capacidad_max": 0
            }
        
        # Calcular capacidad con servicios más corto y más largo
        servicio_mas_corto = min(servicios, key=lambda s: s.duracion_minutos * s.cantidad_consultas)
        servicio_mas_largo = max(servicios, key=lambda s: s.duracion_minutos * s.cantidad_consultas)
        
        duracion_mas_corta = servicio_mas_corto.duracion_minutos * servicio_mas_corto.cantidad_consultas
        duracion_mas_larga = servicio_mas_largo.duracion_minutos * servicio_mas_largo.cantidad_consultas
        
        capacidad_min = minutos_disponibles // duracion_mas_larga
        capacidad_max = minutos_disponibles // duracion_mas_corta
        
        return {
            "fecha": fecha.isoformat(),
            "es_dia_laboral": True,
            "minutos_disponibles": minutos_disponibles,
            "horas_disponibles": round(minutos_disponibles / 60, 1),
            "capacidad_min": capacidad_min,
            "capacidad_max": capacidad_max,
            "bloques_consulta": len(consultation_blocks)
        }
    
    def calcular_capacidad_mensual(self, user_id: str, year: int, month: int) -> Dict:
        """
        Calcular capacidad para un mes completo
        """
        # Obtener primer y último día del mes
        primer_dia = date(year, month, 1)
        if month == 12:
            ultimo_dia = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            ultimo_dia = date(year, month + 1, 1) - timedelta(days=1)
        
        # Obtener excepciones del mes
        excepciones = self.horarios_service.get_exceptions_for_range(
            user_id, primer_dia, ultimo_dia
        )
        excepciones_dict = {exc["date"]: exc for exc in excepciones}
        
        # Calcular capacidad día por día
        total_minutos_mes = 0
        dias_laborables = 0
        capacidad_min_mes = 0
        capacidad_max_mes = 0
        
        current_date = primer_dia
        while current_date <= ultimo_dia:
            # Verificar si hay excepción para este día
            if current_date in excepciones_dict:
                if excepciones_dict[current_date]["is_working_day"]:
                    dias_laborables += 1
                    # Calcular capacidad con horario de excepción
                    capacidad_dia = self.calcular_capacidad_fecha(user_id, current_date)
                    total_minutos_mes += capacidad_dia.get("minutos_disponibles", 0)
                    capacidad_min_mes += capacidad_dia.get("capacidad_min", 0)
                    capacidad_max_mes += capacidad_dia.get("capacidad_max", 0)
            else:
                # Usar template normal
                capacidad_dia = self.calcular_capacidad_fecha(user_id, current_date)
                if capacidad_dia.get("es_dia_laboral"):
                    dias_laborables += 1
                    total_minutos_mes += capacidad_dia.get("minutos_disponibles", 0)
                    capacidad_min_mes += capacidad_dia.get("capacidad_min", 0)
                    capacidad_max_mes += capacidad_dia.get("capacidad_max", 0)
            
            current_date += timedelta(days=1)
        
        return {
            "año": year,
            "mes": month,
            "dias_totales": (ultimo_dia - primer_dia).days + 1,
            "dias_laborables": dias_laborables,
            "total_horas_mes": round(total_minutos_mes / 60, 1),
            "capacidad_min_mes": capacidad_min_mes,
            "capacidad_max_mes": capacidad_max_mes,
            "promedio_citas_por_dia": round(capacidad_max_mes / dias_laborables, 1) if dias_laborables > 0 else 0
        }
    
    def sugerir_optimizaciones(self, user_id: str) -> List[Dict]:
        """
        Sugerir optimizaciones basadas en la capacidad actual
        """
        sugerencias = []
        
        # Obtener capacidad actual
        capacidad = self.calcular_capacidad_semanal(user_id)
        
        # Obtener servicios
        servicios = self.servicios_service.get_all_servicios(user_id)
        
        # Sugerencia 1: Si hay mucha diferencia entre min y max
        if capacidad["capacidad_max_citas"] > 0:
            diferencia_porcentual = ((capacidad["capacidad_max_citas"] - capacidad["capacidad_min_citas"]) 
                                    / capacidad["capacidad_max_citas"]) * 100
            
            if diferencia_porcentual > 50:
                sugerencias.append({
                    "tipo": "variabilidad_alta",
                    "titulo": "Alta variabilidad en capacidad",
                    "descripcion": f"Tienes una diferencia del {diferencia_porcentual:.0f}% entre tu capacidad mínima y máxima",
                    "recomendacion": "Considera estandarizar la duración de tus servicios para predecir mejor tu agenda",
                    "prioridad": "media"
                })
        
        # Sugerencia 2: Si trabaja menos de 30 horas semanales
        if capacidad["total_horas_semana"] < 30 and capacidad["dias_laborables"] >= 5:
            sugerencias.append({
                "tipo": "pocas_horas",
                "titulo": "Horario reducido detectado",
                "descripcion": f"Trabajas solo {capacidad['total_horas_semana']} horas por semana",
                "recomendacion": "Podrías ampliar tu horario para atender más pacientes si lo deseas",
                "prioridad": "baja"
            })
        
        # Sugerencia 3: Si trabaja más de 50 horas semanales
        if capacidad["total_horas_semana"] > 50:
            sugerencias.append({
                "tipo": "muchas_horas",
                "titulo": "Carga horaria alta",
                "descripcion": f"Trabajas {capacidad['total_horas_semana']} horas por semana",
                "recomendacion": "Considera reducir horario o agregar más descansos para evitar agotamiento",
                "prioridad": "alta"
            })
        
        # Sugerencia 4: Si no tiene servicios cortos
        if servicios:
            duracion_minima = min(s.duracion_minutos for s in servicios)
            if duracion_minima >= 60:
                sugerencias.append({
                    "tipo": "sin_consultas_cortas",
                    "titulo": "Sin opciones de consulta rápida",
                    "descripcion": "Todos tus servicios duran 1 hora o más",
                    "recomendacion": "Considera agregar consultas de seguimiento de 30 minutos para optimizar tu agenda",
                    "prioridad": "media"
                })
        
        # Sugerencia 5: Distribución desigual por día
        if capacidad.get("capacidad_por_dia"):
            capacidades_dia = [dia["capacidad_max"] for dia in capacidad["capacidad_por_dia"].values()]
            if capacidades_dia:
                promedio = sum(capacidades_dia) / len(capacidades_dia)
                desviacion = sum(abs(c - promedio) for c in capacidades_dia) / len(capacidades_dia)
                
                if desviacion > promedio * 0.3:  # Más del 30% de desviación
                    sugerencias.append({
                        "tipo": "distribucion_desigual",
                        "titulo": "Distribución desigual de capacidad",
                        "descripcion": "Algunos días tienen mucha más capacidad que otros",
                        "recomendacion": "Considera equilibrar tus horarios para una carga más uniforme",
                        "prioridad": "baja"
                    })
        
        return sugerencias