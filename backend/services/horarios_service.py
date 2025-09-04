from datetime import datetime, date, time, timedelta
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from models.horarios import HorarioTemplate, HorarioException, get_day_name
from models.user import User
from models.consultorio import Consultorio
import uuid

class HorariosService:
    """Servicio para gestión de horarios y disponibilidad"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_horario_for_date(self, user_id: str, target_date: date) -> Dict:
        """
        Obtener el horario completo para una fecha específica,
        considerando templates y excepciones
        IMPROVED: Better handling of consultorio assignment
        """
        # Primero verificar si hay excepción para esta fecha
        exception = self.db.query(HorarioException).filter(
            HorarioException.user_id == user_id,
            HorarioException.date == target_date
        ).first()
        
        if exception:
            # Check if it's a vacation day
            is_vacation = getattr(exception, 'is_vacation', False)
            
            if is_vacation:
                return {
                    "date": target_date,
                    "is_working_day": False,
                    "is_vacation": True,
                    "reason": exception.reason or "Vacaciones",
                    "source": "exception",
                    "consultorio_id": None
                }
            
            # Check if it's a special open day
            is_special_open = getattr(exception, 'is_special_open', False)
            
            if not exception.is_working_day and not is_special_open:
                return {
                    "date": target_date,
                    "is_working_day": False,
                    "reason": exception.reason,
                    "source": "exception",
                    "consultorio_id": None
                }
            
            # Get consultorio info if exists
            consultorio_info = None
            if exception.consultorio_id:
                consultorio = self.db.query(Consultorio).filter(
                    Consultorio.id == exception.consultorio_id
                ).first()
                if consultorio:
                    consultorio_info = {
                        "id": str(consultorio.id),
                        "nombre": consultorio.nombre,
                        "direccion": consultorio.get_short_address(),
                        "es_principal": consultorio.es_principal
                    }
            else:
                # IMPROVED: If no specific consultorio for exception, use principal
                consultorio_info = self._get_principal_consultorio_info(user_id)
            
            return {
                "date": target_date,
                "is_working_day": True,
                "is_special_open": is_special_open,
                "opens_at": exception.opens_at,
                "closes_at": exception.closes_at,
                "time_blocks": exception.time_blocks or [],
                "source": "exception",
                "reason": exception.reason,
                "consultorio_id": str(exception.consultorio_id) if exception.consultorio_id else None,
                "consultorio": consultorio_info
            }
        
        # Si no hay excepción, usar template del día de la semana
        day_of_week = target_date.weekday()
        template = self.db.query(HorarioTemplate).filter(
            HorarioTemplate.user_id == user_id,
            HorarioTemplate.day_of_week == day_of_week
        ).first()
        
        if not template or not template.is_active:
            return {
                "date": target_date,
                "is_working_day": False,
                "day_name": get_day_name(day_of_week),
                "source": "template",
                "consultorio_id": None
            }
        
        # IMPROVED: Get consultorio info with better logic
        consultorio_info = None
        if template.consultorio_id:
            # Template has specific consultorio
            consultorio = self.db.query(Consultorio).filter(
                Consultorio.id == template.consultorio_id
            ).first()
            if consultorio:
                consultorio_info = {
                    "id": str(consultorio.id),
                    "nombre": consultorio.nombre,
                    "direccion": consultorio.get_short_address(),
                    "es_principal": consultorio.es_principal
                }
        else:
            # IMPROVED: Template doesn't have specific consultorio, use principal
            consultorio_info = self._get_principal_consultorio_info(user_id)
        
        return {
            "date": target_date,
            "is_working_day": True,
            "opens_at": template.opens_at,
            "closes_at": template.closes_at,
            "time_blocks": template.time_blocks or [],
            "day_name": get_day_name(day_of_week),
            "source": "template",
            "consultorio_id": str(template.consultorio_id) if template.consultorio_id else None,
            "consultorio": consultorio_info,
            "uses_default_consultorio": not bool(template.consultorio_id)
        }
    
    def _get_principal_consultorio_info(self, user_id: str) -> Optional[Dict]:
        """
        IMPROVED: Helper to get principal consultorio info
        Returns None if no principal exists
        """
        principal = Consultorio.get_principal_for_user(self.db, user_id)
        if principal:
            return {
                "id": str(principal.id),
                "nombre": principal.nombre,
                "direccion": principal.get_short_address(),
                "es_principal": True,
                "is_default": True  # Flag to indicate this is the default
            }
        return None
    
    def get_consultation_blocks(self, horario: Dict) -> List[Dict]:
        """
        Obtener bloques de consulta de un horario
        (excluyendo descansos, comidas, etc.)
        """
        blocks = []
        
        if not horario.get("is_working_day"):
            return blocks
        
        time_blocks = horario.get("time_blocks", [])
        
        if not time_blocks:
            # Si no hay bloques definidos, todo el horario es consulta
            if horario.get("opens_at") and horario.get("closes_at"):
                blocks.append({
                    "start": self._time_to_str(horario["opens_at"]),
                    "end": self._time_to_str(horario["closes_at"]),
                    "type": "consultation",
                    "duration_minutes": self._calculate_duration(
                        horario["opens_at"], 
                        horario["closes_at"]
                    )
                })
        else:
            # Filtrar solo bloques de consulta
            consultation_blocks = [b for b in time_blocks if b.get("type") == "consultation"]
            
            if consultation_blocks:
                # Usar bloques de consulta explícitos
                for block in consultation_blocks:
                    start_time = self._str_to_time(block["start"])
                    end_time = self._str_to_time(block["end"])
                    blocks.append({
                        "start": block["start"],
                        "end": block["end"],
                        "type": "consultation",
                        "duration_minutes": self._calculate_duration(start_time, end_time)
                    })
            else:
                # Calcular bloques de consulta desde los gaps entre descansos
                breaks = [b for b in time_blocks if b.get("type") != "consultation"]
                breaks.sort(key=lambda x: x["start"])
                
                last_end = self._time_to_str(horario["opens_at"])
                
                for break_block in breaks:
                    # Agregar bloque de consulta antes del descanso
                    if last_end < break_block["start"]:
                        blocks.append({
                            "start": last_end,
                            "end": break_block["start"],
                            "type": "consultation",
                            "duration_minutes": self._calculate_duration(
                                self._str_to_time(last_end),
                                self._str_to_time(break_block["start"])
                            )
                        })
                    last_end = break_block["end"]
                
                # Agregar bloque final después del último descanso
                closes_str = self._time_to_str(horario["closes_at"])
                if last_end < closes_str:
                    blocks.append({
                        "start": last_end,
                        "end": closes_str,
                        "type": "consultation",
                        "duration_minutes": self._calculate_duration(
                            self._str_to_time(last_end),
                            self._str_to_time(closes_str)
                        )
                    })
        
        return blocks
    
    def get_weekly_schedule(self, user_id: str) -> Dict:
        """
        Obtener resumen del horario semanal con cálculo correcto de horas
        IMPROVED: Better handling of consultorios used
        """
        templates = self.db.query(HorarioTemplate).filter(
            HorarioTemplate.user_id == user_id
        ).order_by(HorarioTemplate.day_of_week).all()
        
        # Get principal consultorio for default display
        principal = Consultorio.get_principal_for_user(self.db, user_id)
        principal_id = str(principal.id) if principal else None
        principal_name = principal.nombre if principal else None
        
        weekly_schedule = {
            "working_days": 0,
            "total_hours": 0,
            "days": {},
            "consultorios_used": set(),  # Track consultorios used in week
            "principal_consultorio_id": principal_id,
            "principal_consultorio_name": principal_name
        }
        
        for template in templates:
            if template.is_active and template.opens_at and template.closes_at:
                weekly_schedule["working_days"] += 1
                
                # IMPROVED: Track consultorio, don't duplicate principal
                if template.consultorio_id:
                    weekly_schedule["consultorios_used"].add(str(template.consultorio_id))
                elif principal_id:
                    # If no specific consultorio, count principal as used
                    weekly_schedule["consultorios_used"].add(principal_id)
                
                # Calcular horas base del día
                total_minutes = self._calculate_duration(template.opens_at, template.closes_at)
                
                # Restar tiempo de descansos
                if template.time_blocks:
                    for block in template.time_blocks:
                        # Solo restar bloques que NO son de consulta
                        if block.get("type") != "consultation":
                            break_duration = self._calculate_duration(
                                self._str_to_time(block["start"]),
                                self._str_to_time(block["end"])
                            )
                            total_minutes -= break_duration
                
                # Convertir minutos a horas
                hours = total_minutes / 60
                
                weekly_schedule["total_hours"] += hours
                
                # IMPROVED: Get consultorio info
                consultorio_name = None
                consultorio_id = None
                uses_default = False
                
                if template.consultorio_id:
                    consultorio = self.db.query(Consultorio).filter(
                        Consultorio.id == template.consultorio_id
                    ).first()
                    if consultorio:
                        consultorio_name = consultorio.nombre
                        consultorio_id = str(consultorio.id)
                else:
                    # No specific consultorio, use principal
                    if principal:
                        consultorio_name = f"{principal.nombre} (por defecto)"
                        consultorio_id = principal_id
                        uses_default = True
                
                weekly_schedule["days"][template.day_of_week] = {
                    "name": get_day_name(template.day_of_week),
                    "is_active": True,
                    "hours": round(hours, 1),
                    "opens_at": template.opens_at.strftime("%H:%M"),
                    "closes_at": template.closes_at.strftime("%H:%M"),
                    "breaks": len([b for b in template.time_blocks if b.get("type") != "consultation"]) if template.time_blocks else 0,
                    "consultorio_id": consultorio_id,
                    "consultorio_name": consultorio_name,
                    "uses_default_consultorio": uses_default
                }
            else:
                weekly_schedule["days"][template.day_of_week] = {
                    "name": get_day_name(template.day_of_week),
                    "is_active": False,
                    "hours": 0,
                    "consultorio_id": None,
                    "consultorio_name": None,
                    "uses_default_consultorio": False
                }
        
        weekly_schedule["total_hours"] = round(weekly_schedule["total_hours"], 1)
        weekly_schedule["consultorios_used"] = list(weekly_schedule["consultorios_used"])
        
        return weekly_schedule
    
    def validate_horario_times(self, opens_at: str, closes_at: str, time_blocks: List[Dict]) -> Tuple[bool, str]:
        """
        Validar que los horarios sean coherentes
        """
        # Validar que apertura sea antes que cierre
        if opens_at >= closes_at:
            return False, "El horario de apertura debe ser anterior al de cierre"
        
        # Separate breaks from consultation blocks
        breaks = [block for block in time_blocks if block.get('type') != 'consultation']
        
        # Validar bloques de tiempo (solo descansos)
        for block in breaks:
            # Validar que el bloque esté dentro del horario
            if block["start"] < opens_at or block["end"] > closes_at:
                return False, f"El descanso {block['start']}-{block['end']} está fuera del horario de trabajo ({opens_at}-{closes_at})"
            
            # Validar que inicio sea antes que fin
            if block["start"] >= block["end"]:
                return False, f"El descanso {block['start']}-{block['end']} tiene horarios inválidos"
        
        # Validar que los descansos no se superpongan
        sorted_breaks = sorted(breaks, key=lambda x: x["start"])
        for i in range(len(sorted_breaks) - 1):
            if sorted_breaks[i]["end"] > sorted_breaks[i + 1]["start"]:
                return False, f"Los descansos {sorted_breaks[i]['start']}-{sorted_breaks[i]['end']} y {sorted_breaks[i+1]['start']}-{sorted_breaks[i+1]['end']} se superponen"
        
        return True, "Horario válido"
    
    def validate_time_blocks_overlap(self, time_blocks: List[Dict]) -> Tuple[bool, str]:
        """
        Validar que los bloques de tiempo no se superpongan
        """
        if not time_blocks or len(time_blocks) < 2:
            return True, "No hay solapamiento"
        
        # Ordenar bloques por hora de inicio
        sorted_blocks = sorted(time_blocks, key=lambda x: x["start"])
        
        # Verificar solapamientos
        for i in range(len(sorted_blocks) - 1):
            current_block = sorted_blocks[i]
            next_block = sorted_blocks[i + 1]
            
            # Si el fin del bloque actual es posterior al inicio del siguiente, hay solapamiento
            if current_block["end"] > next_block["start"]:
                return False, f"Los bloques {current_block['start']}-{current_block['end']} y {next_block['start']}-{next_block['end']} se superponen"
        
        return True, "No hay solapamiento"
    
    def copy_template_to_days(self, user_id: str, source_day: int, target_days: List[int]) -> int:
        """
        Copiar configuración de un día a otros días
        IMPROVED: Don't copy consultorio assignments
        """
        source_template = self.db.query(HorarioTemplate).filter(
            HorarioTemplate.user_id == user_id,
            HorarioTemplate.day_of_week == source_day
        ).first()
        
        if not source_template:
            return 0
        
        updated_count = 0
        
        for target_day in target_days:
            if target_day == source_day:
                continue
            
            target_template = self.db.query(HorarioTemplate).filter(
                HorarioTemplate.user_id == user_id,
                HorarioTemplate.day_of_week == target_day
            ).first()
            
            if target_template:
                # Actualizar existente (pero mantener el consultorio específico del día)
                target_template.is_active = source_template.is_active
                target_template.opens_at = source_template.opens_at
                target_template.closes_at = source_template.closes_at
                target_template.time_blocks = source_template.time_blocks
                # IMPROVED: NO copiar consultorio_id - cada día mantiene su propio consultorio
                target_template.updated_at = datetime.utcnow()
            else:
                # Crear nuevo
                target_template = HorarioTemplate(
                    user_id=user_id,
                    day_of_week=target_day,
                    is_active=source_template.is_active,
                    opens_at=source_template.opens_at,
                    closes_at=source_template.closes_at,
                    time_blocks=source_template.time_blocks,
                    consultorio_id=None  # No copiar consultorio
                )
                self.db.add(target_template)
            
            updated_count += 1
        
        self.db.commit()
        return updated_count
    
    def get_exceptions_for_range(self, user_id: str, start_date: date, end_date: date) -> List[Dict]:
        """
        Obtener todas las excepciones en un rango de fechas
        IMPROVED: Better consultorio info handling
        """
        exceptions = self.db.query(HorarioException).filter(
            HorarioException.user_id == user_id,
            HorarioException.date >= start_date,
            HorarioException.date <= end_date
        ).order_by(HorarioException.date).all()
        
        # Get principal consultorio for defaults
        principal = Consultorio.get_principal_for_user(self.db, user_id)
        
        result = []
        for exc in exceptions:
            # Get consultorio info if exists
            consultorio_info = None
            if exc.consultorio_id:
                consultorio = self.db.query(Consultorio).filter(
                    Consultorio.id == exc.consultorio_id
                ).first()
                if consultorio:
                    consultorio_info = {
                        "id": str(consultorio.id),
                        "nombre": consultorio.nombre,
                        "direccion": consultorio.get_short_address(),
                        "es_principal": consultorio.es_principal
                    }
            elif principal and exc.is_working_day:
                # If working day but no specific consultorio, show principal as default
                consultorio_info = {
                    "id": str(principal.id),
                    "nombre": f"{principal.nombre} (por defecto)",
                    "direccion": principal.get_short_address(),
                    "es_principal": True,
                    "is_default": True
                }
            
            result.append({
                "date": exc.date,
                "is_working_day": exc.is_working_day,
                "is_special_open": getattr(exc, 'is_special_open', False),
                "is_vacation": getattr(exc, 'is_vacation', False),
                "vacation_group_id": getattr(exc, 'vacation_group_id', None),
                "reason": exc.reason,
                "opens_at": exc.opens_at.strftime("%H:%M") if exc.opens_at else None,
                "closes_at": exc.closes_at.strftime("%H:%M") if exc.closes_at else None,
                "time_blocks": exc.time_blocks or [],
                "consultorio_id": str(exc.consultorio_id) if exc.consultorio_id else None,
                "consultorio": consultorio_info
            })
        
        return result
    
    def check_exception_exists(self, user_id: str, check_date: date) -> bool:
        """
        Verificar si ya existe una excepción para una fecha
        """
        exception = self.db.query(HorarioException).filter(
            HorarioException.user_id == user_id,
            HorarioException.date == check_date
        ).first()
        
        return exception is not None
    
    def create_vacation_period(self, user_id: str, start_date: date, end_date: date, reason: str = "Vacaciones") -> int:
        """
        Crear un período de vacaciones
        """
        vacation_group_id = str(uuid.uuid4())
        created_count = 0
        
        current_date = start_date
        while current_date <= end_date:
            # Check if exception already exists
            if not self.check_exception_exists(user_id, current_date):
                exception = HorarioException(
                    user_id=user_id,
                    date=current_date,
                    is_working_day=False,
                    is_vacation=True,
                    vacation_group_id=vacation_group_id,
                    reason=reason,
                    consultorio_id=None  # Vacations don't have consultorio
                )
                self.db.add(exception)
                created_count += 1
            
            current_date += timedelta(days=1)
        
        self.db.commit()
        return created_count
    
    def delete_vacation_group(self, user_id: str, vacation_group_id: str) -> int:
        """
        Eliminar un grupo completo de vacaciones
        """
        exceptions = self.db.query(HorarioException).filter(
            HorarioException.user_id == user_id,
            HorarioException.vacation_group_id == vacation_group_id
        ).all()
        
        deleted_count = len(exceptions)
        
        for exception in exceptions:
            self.db.delete(exception)
        
        self.db.commit()
        return deleted_count
    
    def get_consultorio_for_date(self, user_id: str, target_date: date) -> Optional[Dict]:
        """
        Get the consultorio for a specific date
        IMPROVED: Better handling of default consultorio
        """
        horario = self.get_horario_for_date(user_id, target_date)
        
        if not horario.get("is_working_day"):
            return None
        
        return horario.get("consultorio")
    
    # Métodos auxiliares privados
    def _time_to_str(self, time_obj) -> str:
        """Convertir objeto time a string HH:MM"""
        if isinstance(time_obj, str):
            return time_obj
        return time_obj.strftime("%H:%M") if time_obj else ""
    
    def _str_to_time(self, time_str: str) -> time:
        """Convertir string HH:MM a objeto time"""
        if isinstance(time_str, time):
            return time_str
        return datetime.strptime(time_str, "%H:%M").time()
    
    def _calculate_duration(self, start_time, end_time) -> int:
        """Calcular duración en minutos entre dos tiempos"""
        if isinstance(start_time, str):
            start_time = self._str_to_time(start_time)
        if isinstance(end_time, str):
            end_time = self._str_to_time(end_time)
        
        start_dt = datetime.combine(date.today(), start_time)
        end_dt = datetime.combine(date.today(), end_time)
        
        return int((end_dt - start_dt).total_seconds() / 60)