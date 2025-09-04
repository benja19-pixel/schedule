from datetime import datetime, date, time, timedelta
from typing import List, Dict, Optional, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from models.schedule import (
    ScheduleTemplate, ScheduleException, AppointmentType, 
    Appointment, ScheduleSettings, get_day_name
)
from models.user import User
import uuid
from collections import defaultdict
import json

class ScheduleService:
    """Service class for schedule management business logic"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_schedule_for_date(self, user_id: str, target_date: date) -> Dict:
        """
        Get the complete schedule for a specific date, considering templates and exceptions
        """
        # Check for exception first
        exception = self.db.query(ScheduleException).filter(
            ScheduleException.user_id == user_id,
            ScheduleException.date == target_date
        ).first()
        
        if exception:
            if not exception.is_working_day:
                return {
                    "date": target_date,
                    "is_working_day": False,
                    "reason": exception.reason
                }
            
            return {
                "date": target_date,
                "is_working_day": True,
                "opens_at": exception.opens_at,
                "closes_at": exception.closes_at,
                "time_blocks": exception.time_blocks or [],
                "source": "exception",
                "reason": exception.reason
            }
        
        # Get template for day of week
        day_of_week = target_date.weekday()
        template = self.db.query(ScheduleTemplate).filter(
            ScheduleTemplate.user_id == user_id,
            ScheduleTemplate.day_of_week == day_of_week
        ).first()
        
        if not template or not template.is_active:
            return {
                "date": target_date,
                "is_working_day": False,
                "day_name": get_day_name(day_of_week)
            }
        
        return {
            "date": target_date,
            "is_working_day": True,
            "opens_at": template.opens_at,
            "closes_at": template.closes_at,
            "time_blocks": template.time_blocks or [],
            "default_duration": template.default_duration,
            "buffer_time": template.buffer_time,
            "source": "template",
            "day_name": get_day_name(day_of_week)
        }
    
    def get_available_slots(
        self, 
        user_id: str, 
        target_date: date,
        appointment_type_id: Optional[str] = None,
        min_advance_booking: Optional[int] = None,
        max_advance_booking: Optional[int] = None
    ) -> List[Dict]:
        """
        Calculate available time slots for a specific date
        """
        # Get schedule for the date
        schedule = self.get_schedule_for_date(user_id, target_date)
        
        if not schedule["is_working_day"]:
            return []
        
        # Get user settings
        settings = self.db.query(ScheduleSettings).filter(
            ScheduleSettings.user_id == user_id
        ).first()
        
        # Apply booking restrictions
        now = datetime.now()
        min_booking_time = now + timedelta(minutes=min_advance_booking or (settings.min_advance_booking if settings else 60))
        max_booking_date = now.date() + timedelta(days=max_advance_booking or (settings.max_advance_booking if settings else 30))
        
        if target_date < now.date() or target_date > max_booking_date:
            return []
        
        # Get appointment type duration or use default
        duration = None
        if appointment_type_id:
            apt_type = self.db.query(AppointmentType).filter(
                AppointmentType.id == appointment_type_id,
                AppointmentType.user_id == user_id
            ).first()
            if apt_type:
                duration = apt_type.duration
        
        if not duration:
            duration = schedule.get("default_duration", 30)
        
        buffer_time = schedule.get("buffer_time", 0)
        
        # Get existing appointments
        appointments = self.db.query(Appointment).filter(
            Appointment.user_id == user_id,
            Appointment.appointment_date == target_date,
            Appointment.status.in_(["scheduled", "confirmed"])
        ).all()
        
        # Calculate slots
        available_slots = []
        time_blocks = schedule.get("time_blocks", [])
        
        if time_blocks:
            # Use defined consultation blocks
            for block in time_blocks:
                if block.get("type") == "consultation":
                    slots = self._calculate_slots_in_block(
                        block["start"],
                        block["end"],
                        duration,
                        buffer_time,
                        appointments,
                        target_date,
                        min_booking_time
                    )
                    available_slots.extend(slots)
        else:
            # Use general opening hours
            if schedule.get("opens_at") and schedule.get("closes_at"):
                slots = self._calculate_slots_in_block(
                    schedule["opens_at"].strftime("%H:%M") if hasattr(schedule["opens_at"], 'strftime') else schedule["opens_at"],
                    schedule["closes_at"].strftime("%H:%M") if hasattr(schedule["closes_at"], 'strftime') else schedule["closes_at"],
                    duration,
                    buffer_time,
                    appointments,
                    target_date,
                    min_booking_time
                )
                available_slots.extend(slots)
        
        # Check if we've reached daily limit
        if settings and settings.max_patients_per_day:
            current_count = len(appointments)
            if current_count >= settings.max_patients_per_day:
                if not settings.allow_overbooking:
                    return []
                elif current_count >= settings.max_patients_per_day + settings.max_overbooking_per_day:
                    return []
        
        return available_slots
    
    def _calculate_slots_in_block(
        self, 
        start_time: str, 
        end_time: str, 
        duration: int,
        buffer_time: int,
        appointments: List[Appointment],
        target_date: date,
        min_booking_time: datetime
    ) -> List[Dict]:
        """
        Calculate available slots within a time block
        """
        slots = []
        
        # Parse times
        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
        
        current = datetime.combine(target_date, start)
        end_datetime = datetime.combine(target_date, end)
        
        while current + timedelta(minutes=duration) <= end_datetime:
            slot_start = current.time()
            slot_end = (current + timedelta(minutes=duration)).time()
            
            # Check minimum advance booking
            slot_datetime = datetime.combine(target_date, slot_start)
            if slot_datetime < min_booking_time:
                current += timedelta(minutes=duration + buffer_time)
                continue
            
            # Check if slot is available
            is_available = True
            for apt in appointments:
                # Check for overlap
                if (apt.start_time < slot_end and apt.end_time > slot_start):
                    is_available = False
                    break
            
            if is_available:
                slots.append({
                    "start": slot_start.strftime("%H:%M"),
                    "end": slot_end.strftime("%H:%M"),
                    "datetime": slot_datetime.isoformat()
                })
            
            current += timedelta(minutes=duration + buffer_time)
        
        return slots
    
    def emergency_closure(
        self,
        user_id: str,
        closure_date: date,
        reason: str,
        message: Optional[str] = None
    ) -> Dict:
        """
        Apply emergency closure for a specific date
        """
        # Get all appointments for that date
        appointments = self.db.query(Appointment).filter(
            Appointment.user_id == user_id,
            Appointment.appointment_date == closure_date,
            Appointment.status.in_(["scheduled", "confirmed"])
        ).all()
        
        cancelled_count = 0
        notified_patients = []
        
        # Cancel all appointments
        for appointment in appointments:
            appointment.status = "cancelled"
            appointment.cancelled_at = datetime.utcnow()
            appointment.cancellation_reason = f"Cierre de emergencia: {reason}"
            appointment.updated_at = datetime.utcnow()
            
            cancelled_count += 1
            notified_patients.append({
                "name": appointment.patient_name,
                "phone": appointment.patient_phone,
                "email": appointment.patient_email,
                "original_time": appointment.start_time.strftime("%H:%M")
            })
            
            # TODO: Send notification via WhatsApp/SMS
            # This will be implemented when WhatsApp integration is ready
            # notification_service.send_cancellation(appointment, message)
        
        # Create exception for this date
        existing_exception = self.db.query(ScheduleException).filter(
            ScheduleException.user_id == user_id,
            ScheduleException.date == closure_date
        ).first()
        
        if existing_exception:
            existing_exception.is_working_day = False
            existing_exception.reason = f"Cierre de emergencia: {reason}"
            existing_exception.updated_at = datetime.utcnow()
        else:
            exception = ScheduleException(
                user_id=user_id,
                date=closure_date,
                is_working_day=False,
                reason=f"Cierre de emergencia: {reason}"
            )
            self.db.add(exception)
        
        # Commit all changes
        self.db.commit()
        
        return {
            "cancelled_count": cancelled_count,
            "notified_patients": notified_patients
        }
    
    def get_calendar_view(
        self,
        user_id: str,
        view_type: str,
        target_date: date
    ) -> Dict:
        """
        Get calendar view data for the agenda
        """
        if view_type == "day":
            start_date = target_date
            end_date = target_date
        elif view_type == "week":
            # Get Monday of the week
            days_since_monday = target_date.weekday()
            start_date = target_date - timedelta(days=days_since_monday)
            end_date = start_date + timedelta(days=6)
        elif view_type == "month":
            start_date = date(target_date.year, target_date.month, 1)
            # Get last day of month
            if target_date.month == 12:
                end_date = date(target_date.year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(target_date.year, target_date.month + 1, 1) - timedelta(days=1)
        else:
            raise ValueError(f"Invalid view type: {view_type}")
        
        # Get appointments in range
        appointments = self.db.query(Appointment).filter(
            Appointment.user_id == user_id,
            Appointment.appointment_date >= start_date,
            Appointment.appointment_date <= end_date
        ).order_by(
            Appointment.appointment_date,
            Appointment.start_time
        ).all()
        
        # Get exceptions in range
        exceptions = self.db.query(ScheduleException).filter(
            ScheduleException.user_id == user_id,
            ScheduleException.date >= start_date,
            ScheduleException.date <= end_date
        ).all()
        
        # Build calendar data
        calendar_data = {
            "view_type": view_type,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "appointments": [],
            "exceptions": [],
            "availability": {},
            "summary": {
                "total_appointments": len(appointments),
                "confirmed": 0,
                "pending": 0,
                "cancelled": 0
            }
        }
        
        # Process appointments
        for apt in appointments:
            apt_data = {
                "id": str(apt.id),
                "date": apt.appointment_date.isoformat(),
                "start_time": apt.start_time.strftime("%H:%M"),
                "end_time": apt.end_time.strftime("%H:%M"),
                "patient_name": apt.patient_name,
                "patient_phone": apt.patient_phone,
                "status": apt.status,
                "type": apt.appointment_type.name if apt.appointment_type else "Consulta",
                "color": apt.appointment_type.color if apt.appointment_type else "#3B82F6",
                "source": apt.source,
                "auto_scheduled": apt.auto_scheduled
            }
            calendar_data["appointments"].append(apt_data)
            
            # Update summary
            if apt.status == "confirmed":
                calendar_data["summary"]["confirmed"] += 1
            elif apt.status == "scheduled":
                calendar_data["summary"]["pending"] += 1
            elif apt.status == "cancelled":
                calendar_data["summary"]["cancelled"] += 1
        
        # Process exceptions
        for exc in exceptions:
            exc_data = {
                "date": exc.date.isoformat(),
                "is_working_day": exc.is_working_day,
                "reason": exc.reason
            }
            calendar_data["exceptions"].append(exc_data)
        
        # Calculate availability for each day (only for week view)
        if view_type == "week":
            current = start_date
            while current <= end_date:
                slots = self.get_available_slots(user_id, current)
                calendar_data["availability"][current.isoformat()] = {
                    "count": len(slots),
                    "slots": slots[:5]  # Only send first 5 for preview
                }
                current += timedelta(days=1)
        
        return calendar_data
    
    def create_appointment_from_whatsapp(
        self,
        user_id: str,
        patient_data: Dict,
        appointment_data: Dict
    ) -> Appointment:
        """
        Create an appointment from WhatsApp secretary data
        """
        # Validate availability
        slot_available = self.is_slot_available(
            user_id,
            appointment_data["date"],
            appointment_data["start_time"],
            appointment_data.get("duration", 30)
        )
        
        if not slot_available:
            raise ValueError("Time slot is not available")
        
        # Calculate end time
        start = datetime.strptime(appointment_data["start_time"], "%H:%M").time()
        duration = appointment_data.get("duration", 30)
        end = (datetime.combine(date.today(), start) + timedelta(minutes=duration)).time()
        
        # Create appointment
        appointment = Appointment(
            id=uuid.uuid4(),
            user_id=user_id,
            patient_name=patient_data["name"],
            patient_phone=patient_data["phone"],
            patient_email=patient_data.get("email"),
            appointment_date=appointment_data["date"],
            start_time=start,
            end_time=end,
            appointment_type_id=appointment_data.get("appointment_type_id"),
            reason=appointment_data.get("reason"),
            source="whatsapp",
            status="scheduled",
            auto_scheduled=True,
            whatsapp_session_id=appointment_data.get("session_id"),
            ai_confidence_score=appointment_data.get("confidence_score", 85)
        )
        
        self.db.add(appointment)
        self.db.commit()
        self.db.refresh(appointment)
        
        # Auto-confirm if enabled
        settings = self.db.query(ScheduleSettings).filter(
            ScheduleSettings.user_id == user_id
        ).first()
        
        if settings and settings.auto_confirm:
            appointment.status = "confirmed"
            appointment.confirmed_at = datetime.utcnow()
            appointment.confirmation_method = "ai_auto"
            self.db.commit()
        
        return appointment
    
    def is_slot_available(
        self,
        user_id: str,
        appointment_date: date,
        start_time: str,
        duration: int
    ) -> bool:
        """
        Check if a specific time slot is available
        """
        # Parse time
        start = datetime.strptime(start_time, "%H:%M").time()
        end = (datetime.combine(date.today(), start) + timedelta(minutes=duration)).time()
        
        # Check if it's within working hours
        schedule = self.get_schedule_for_date(user_id, appointment_date)
        if not schedule["is_working_day"]:
            return False
        
        # Check against existing appointments
        conflicting = self.db.query(Appointment).filter(
            Appointment.user_id == user_id,
            Appointment.appointment_date == appointment_date,
            Appointment.status.in_(["scheduled", "confirmed"]),
            # Check for time overlap
            Appointment.start_time < end,
            Appointment.end_time > start
        ).first()
        
        return conflicting is None
    
    def get_next_available_slots(
        self,
        user_id: str,
        count: int = 5,
        appointment_type_id: Optional[str] = None,
        start_date: Optional[date] = None
    ) -> List[Dict]:
        """
        Get the next N available slots across multiple days
        """
        available_slots = []
        current_date = start_date or date.today()
        max_days_ahead = 30
        days_checked = 0
        
        while len(available_slots) < count and days_checked < max_days_ahead:
            daily_slots = self.get_available_slots(
                user_id,
                current_date,
                appointment_type_id
            )
            
            for slot in daily_slots:
                if len(available_slots) < count:
                    slot["date"] = current_date.isoformat()
                    slot["day_name"] = self._get_day_name_spanish(current_date.weekday())
                    available_slots.append(slot)
            
            current_date += timedelta(days=1)
            days_checked += 1
        
        return available_slots
    
    def _get_day_name_spanish(self, weekday: int) -> str:
        """Get Spanish day name from weekday number"""
        days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        return days[weekday]
    
    def suggest_alternative_slots(
        self,
        user_id: str,
        preferred_date: date,
        preferred_time: str,
        appointment_type_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Suggest alternative slots when preferred time is not available
        """
        alternatives = []
        
        # Try same day, different times
        same_day_slots = self.get_available_slots(
            user_id,
            preferred_date,
            appointment_type_id
        )
        
        # Find closest times to preferred
        preferred_minutes = self._time_to_minutes(preferred_time)
        
        same_day_sorted = sorted(
            same_day_slots,
            key=lambda x: abs(self._time_to_minutes(x["start"]) - preferred_minutes)
        )[:3]
        
        for slot in same_day_sorted:
            slot["date"] = preferred_date.isoformat()
            slot["suggestion_type"] = "same_day"
            alternatives.append(slot)
        
        # Try nearby days at same time
        for days_offset in [1, -1, 2, -2]:
            alt_date = preferred_date + timedelta(days=days_offset)
            if alt_date >= date.today():
                day_slots = self.get_available_slots(
                    user_id,
                    alt_date,
                    appointment_type_id
                )
                
                # Find slots at similar time
                for slot in day_slots:
                    slot_minutes = self._time_to_minutes(slot["start"])
                    if abs(slot_minutes - preferred_minutes) <= 60:  # Within 1 hour
                        slot["date"] = alt_date.isoformat()
                        slot["suggestion_type"] = "nearby_day"
                        alternatives.append(slot)
                        break
        
        return alternatives[:5]  # Return top 5 suggestions
    
    def _time_to_minutes(self, time_str: str) -> int:
        """Convert time string to minutes since midnight"""
        h, m = map(int, time_str.split(':'))
        return h * 60 + m
    
    def get_doctor_availability_summary(
        self,
        user_id: str,
        start_date: date,
        end_date: date
    ) -> Dict:
        """
        Get a summary of doctor's availability for a date range
        """
        total_days = (end_date - start_date).days + 1
        working_days = 0
        total_hours = 0
        total_appointments = 0
        total_available_slots = 0
        
        current = start_date
        while current <= end_date:
            schedule = self.get_schedule_for_date(user_id, current)
            
            if schedule["is_working_day"]:
                working_days += 1
                
                # Calculate hours
                if schedule.get("opens_at") and schedule.get("closes_at"):
                    opens = schedule["opens_at"]
                    closes = schedule["closes_at"]
                    
                    if isinstance(opens, str):
                        opens = datetime.strptime(opens, "%H:%M").time()
                    if isinstance(closes, str):
                        closes = datetime.strptime(closes, "%H:%M").time()
                    
                    hours = (datetime.combine(date.today(), closes) - 
                            datetime.combine(date.today(), opens)).seconds / 3600
                    total_hours += hours
                
                # Count appointments
                appointments = self.db.query(Appointment).filter(
                    Appointment.user_id == user_id,
                    Appointment.appointment_date == current,
                    Appointment.status.in_(["scheduled", "confirmed", "completed"])
                ).count()
                total_appointments += appointments
                
                # Count available slots
                slots = self.get_available_slots(user_id, current)
                total_available_slots += len(slots)
            
            current += timedelta(days=1)
        
        return {
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "total_days": total_days
            },
            "working_days": working_days,
            "total_hours": round(total_hours, 1),
            "average_hours_per_day": round(total_hours / working_days, 1) if working_days > 0 else 0,
            "total_appointments": total_appointments,
            "total_available_slots": total_available_slots,
            "occupancy_rate": round((total_appointments / (total_appointments + total_available_slots) * 100), 1) 
                             if (total_appointments + total_available_slots) > 0 else 0
        }
    
    def optimize_schedule(self, user_id: str) -> List[Dict]:
        """
        Suggest schedule optimizations based on usage patterns
        """
        suggestions = []
        
        # Analyze last 30 days
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        # Get appointments by hour
        appointments = self.db.query(
            Appointment.start_time,
            Appointment.appointment_date
        ).filter(
            Appointment.user_id == user_id,
            Appointment.appointment_date >= start_date,
            Appointment.appointment_date <= end_date,
            Appointment.status.in_(["completed", "scheduled", "confirmed"])
        ).all()
        
        # Analyze patterns
        hour_counts = defaultdict(int)
        day_counts = defaultdict(int)
        
        for apt in appointments:
            hour_counts[apt.start_time.hour] += 1
            day_counts[apt.appointment_date.weekday()] += 1
        
        # Find peak hours
        if hour_counts:
            peak_hour = max(hour_counts, key=hour_counts.get)
            if hour_counts[peak_hour] > len(appointments) * 0.3:
                suggestions.append({
                    "type": "peak_hour",
                    "message": f"El horario de {peak_hour}:00 es muy solicitado. Considera ampliar disponibilidad en ese horario.",
                    "priority": "high"
                })
        
        # Find underutilized days
        for day in range(5):  # Monday to Friday
            template = self.db.query(ScheduleTemplate).filter(
                ScheduleTemplate.user_id == user_id,
                ScheduleTemplate.day_of_week == day
            ).first()
            
            if template and template.is_active and day_counts.get(day, 0) < 2:
                suggestions.append({
                    "type": "underutilized_day",
                    "message": f"Los {self._get_day_name_spanish(day)} tienen poca demanda. Podrías reducir horario o cerrar.",
                    "priority": "medium"
                })
        
        # Check for gaps in schedule
        templates = self.db.query(ScheduleTemplate).filter(
            ScheduleTemplate.user_id == user_id,
            ScheduleTemplate.is_active == True
        ).all()
        
        for template in templates:
            if template.time_blocks:
                # Check for long gaps between blocks
                blocks = sorted(template.time_blocks, key=lambda x: x["start"])
                for i in range(len(blocks) - 1):
                    end1 = datetime.strptime(blocks[i]["end"], "%H:%M")
                    start2 = datetime.strptime(blocks[i+1]["start"], "%H:%M")
                    gap_minutes = (start2 - end1).seconds / 60
                    
                    if gap_minutes > 90:  # More than 1.5 hours
                        suggestions.append({
                            "type": "schedule_gap",
                            "message": f"Tienes un espacio de {int(gap_minutes)} minutos los {self._get_day_name_spanish(template.day_of_week)}. Considera optimizar.",
                            "priority": "low"
                        })
        
        return suggestions
    
    def get_whatsapp_schedule_message(self, user_id: str, days_ahead: int = 7) -> str:
        """
        Generate a formatted schedule message for WhatsApp
        """
        message = "📅 *Horarios disponibles:*\n\n"
        
        current = date.today()
        for i in range(days_ahead):
            check_date = current + timedelta(days=i)
            schedule = self.get_schedule_for_date(user_id, check_date)
            
            if schedule["is_working_day"]:
                day_name = self._get_day_name_spanish(check_date.weekday())
                date_str = check_date.strftime("%d/%m")
                
                # Get available slots count
                slots = self.get_available_slots(user_id, check_date)
                
                if slots:
                    message += f"*{day_name} {date_str}*\n"
                    # Show first 3 slots
                    for slot in slots[:3]:
                        message += f"• {slot['start']}\n"
                    if len(slots) > 3:
                        message += f"• _y {len(slots) - 3} horarios más_\n"
                    message += "\n"
        
        if message == "📅 *Horarios disponibles:*\n\n":
            message = "Lo siento, no hay horarios disponibles en los próximos días. 😔"
        
        return message
    
    def format_slots_for_ai(
        self, 
        user_id: str, 
        days_ahead: int = 7,
        preferred_time: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Format available slots in a structure optimized for AI responses
        """
        slots_data = {
            "summary": {},
            "by_day": {},
            "by_time_period": {
                "morning": [],  # 6am-12pm
                "afternoon": [],  # 12pm-6pm
                "evening": []  # 6pm-10pm
            },
            "recommendations": []
        }
        
        total_slots = 0
        current = date.today()
        
        for i in range(days_ahead):
            check_date = current + timedelta(days=i)
            daily_slots = self.get_available_slots(user_id, check_date)
            
            if daily_slots:
                date_str = check_date.isoformat()
                day_name = self._get_day_name_spanish(check_date.weekday())
                
                slots_data["by_day"][date_str] = {
                    "day_name": day_name,
                    "date_formatted": check_date.strftime("%d de %B"),
                    "total_slots": len(daily_slots),
                    "first_available": daily_slots[0]["start"],
                    "last_available": daily_slots[-1]["start"],
                    "slots": daily_slots[:10]  # Limit to first 10 for AI
                }
                
                # Categorize by time period
                for slot in daily_slots:
                    hour = int(slot["start"].split(":")[0])
                    slot_with_date = {**slot, "date": date_str, "day_name": day_name}
                    
                    if 6 <= hour < 12:
                        slots_data["by_time_period"]["morning"].append(slot_with_date)
                    elif 12 <= hour < 18:
                        slots_data["by_time_period"]["afternoon"].append(slot_with_date)
                    elif 18 <= hour < 22:
                        slots_data["by_time_period"]["evening"].append(slot_with_date)
                
                total_slots += len(daily_slots)
        
        # Summary
        slots_data["summary"] = {
            "total_available_slots": total_slots,
            "days_with_availability": len(slots_data["by_day"]),
            "next_available": None,
            "busiest_day": None,
            "quietest_day": None
        }
        
        # Find next available slot
        if slots_data["by_day"]:
            first_day = list(slots_data["by_day"].keys())[0]
            slots_data["summary"]["next_available"] = {
                "date": first_day,
                "time": slots_data["by_day"][first_day]["first_available"],
                "day_name": slots_data["by_day"][first_day]["day_name"]
            }
        
        # Find busiest and quietest days
        if slots_data["by_day"]:
            sorted_days = sorted(
                slots_data["by_day"].items(),
                key=lambda x: x[1]["total_slots"]
            )
            
            slots_data["summary"]["quietest_day"] = sorted_days[0][0]
            slots_data["summary"]["busiest_day"] = sorted_days[-1][0]
        
        # Generate recommendations
        if preferred_time:
            if preferred_time == "morning" and slots_data["by_time_period"]["morning"]:
                slots_data["recommendations"].append(
                    "Tengo varios horarios disponibles en las mañanas que podrían convenirle."
                )
            elif preferred_time == "afternoon" and slots_data["by_time_period"]["afternoon"]:
                slots_data["recommendations"].append(
                    "Hay buena disponibilidad en las tardes."
                )
            elif preferred_time == "evening" and slots_data["by_time_period"]["evening"]:
                slots_data["recommendations"].append(
                    "Tengo algunos espacios en las noches disponibles."
                )
        
        if total_slots < 10:
            slots_data["recommendations"].append(
                "La agenda está bastante ocupada esta semana, le recomiendo agendar lo antes posible."
            )
        elif total_slots > 50:
            slots_data["recommendations"].append(
                "Hay muy buena disponibilidad, puede elegir el horario que más le convenga."
            )
        
        return slots_data
    
    def validate_ai_appointment(
        self,
        user_id: str,
        appointment_data: Dict
    ) -> Tuple[bool, str]:
        """
        Validate appointment data from AI with detailed error messages
        """
        # Check required fields
        required_fields = ["patient_name", "patient_phone", "date", "time"]
        for field in required_fields:
            if field not in appointment_data or not appointment_data[field]:
                return False, f"Falta información requerida: {field}"
        
        # Validate date
        try:
            apt_date = datetime.strptime(appointment_data["date"], "%Y-%m-%d").date()
        except ValueError:
            return False, "Formato de fecha inválido"
        
        if apt_date < date.today():
            return False, "No se pueden agendar citas en fechas pasadas"
        
        # Validate time
        try:
            apt_time = datetime.strptime(appointment_data["time"], "%H:%M").time()
        except ValueError:
            return False, "Formato de hora inválido"
        
        # Check if slot is available
        duration = appointment_data.get("duration", 30)
        if not self.is_slot_available(user_id, apt_date, appointment_data["time"], duration):
            return False, "El horario seleccionado no está disponible"
        
        # Check daily limit
        daily_appointments = self.db.query(func.count(Appointment.id)).filter(
            Appointment.user_id == user_id,
            Appointment.appointment_date == apt_date,
            Appointment.status.in_(["scheduled", "confirmed"])
        ).scalar()
        
        settings = self.db.query(ScheduleSettings).filter(
            ScheduleSettings.user_id == user_id
        ).first()
        
        max_daily = settings.max_patients_per_day if settings else 20
        
        if daily_appointments >= max_daily:
            if not settings or not settings.allow_overbooking:
                return False, f"Se ha alcanzado el límite diario de {max_daily} citas"
        
        # Validate phone number (basic check)
        phone = appointment_data["patient_phone"]
        if not phone or len(phone) < 10:
            return False, "Número de teléfono inválido"
        
        return True, "Validación exitosa"
    
    def get_patient_history(
        self,
        user_id: str,
        patient_phone: str
    ) -> List[Dict]:
        """
        Get appointment history for a patient by phone number
        """
        appointments = self.db.query(Appointment).filter(
            Appointment.user_id == user_id,
            Appointment.patient_phone == patient_phone
        ).order_by(
            Appointment.appointment_date.desc(),
            Appointment.start_time.desc()
        ).limit(10).all()
        
        history = []
        for apt in appointments:
            history.append({
                "date": apt.appointment_date.isoformat(),
                "time": apt.start_time.strftime("%H:%M"),
                "status": apt.status,
                "type": apt.appointment_type.name if apt.appointment_type else "Consulta",
                "reason": apt.reason,
                "no_show": apt.status == "no_show",
                "cancelled": apt.status == "cancelled"
            })
        
        return history