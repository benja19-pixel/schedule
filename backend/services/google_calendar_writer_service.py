from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Set
import logging
import uuid

logger = logging.getLogger(__name__)

class GoogleCalendarWriterService:
    """Service for writing events to Google Calendar with bidirectional sync support"""
    
    def __init__(self, credentials: Credentials):
        """Initialize the Google Calendar writer service"""
        self.credentials = credentials
        self.service = build('calendar', 'v3', credentials=credentials)
        self.calendar_id = 'primary'
        self.tracked_event_ids: Set[str] = set()  # Track events we've created
    
    def sync_break_to_calendar(self, break_info: Dict, date_info: Dict) -> Optional[str]:
        """
        Sync a break/rest period to Google Calendar
        date_info contains either is_recurring=True with day_of_week, or is_recurring=False with date
        """
        try:
            # Prepare event data
            event = {
                'summary': self._get_break_title(break_info.get('type', 'break')),
                'description': 'Sincronizado desde MediConnect - Descanso programado',
                'colorId': self._get_color_for_break_type(break_info.get('type', 'break')),
                'reminders': {
                    'useDefault': False,
                    'overrides': []
                }
            }
            
            # Set time
            if date_info.get('is_recurring'):
                # For recurring events, use next occurrence
                next_date = self._get_next_weekday(date_info['day_of_week'])
                start_datetime = datetime.combine(next_date, self._parse_time(break_info['start']))
                end_datetime = datetime.combine(next_date, self._parse_time(break_info['end']))
                
                event['start'] = {
                    'dateTime': start_datetime.isoformat(),
                    'timeZone': 'America/Mexico_City'
                }
                event['end'] = {
                    'dateTime': end_datetime.isoformat(),
                    'timeZone': 'America/Mexico_City'
                }
                
                # Add recurrence rule for weekly events
                event['recurrence'] = [
                    f"RRULE:FREQ=WEEKLY;BYDAY={self._day_to_rrule(date_info['day_of_week'])}"
                ]
                
            else:
                # One-time event
                event_date = datetime.fromisoformat(date_info['date']).date()
                start_datetime = datetime.combine(event_date, self._parse_time(break_info['start']))
                end_datetime = datetime.combine(event_date, self._parse_time(break_info['end']))
                
                event['start'] = {
                    'dateTime': start_datetime.isoformat(),
                    'timeZone': 'America/Mexico_City'
                }
                event['end'] = {
                    'dateTime': end_datetime.isoformat(),
                    'timeZone': 'America/Mexico_City'
                }
            
            # Create the event
            created_event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event
            ).execute()
            
            event_id = created_event.get('id')
            self.tracked_event_ids.add(event_id)
            
            logger.info(f"Created break event in Google Calendar: {event_id}")
            return event_id
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error syncing break to calendar: {str(e)}")
            return None
    
    def sync_recurring_break_to_calendar(self, break_info: Dict, recurrence_pattern: Dict) -> Optional[str]:
        """
        Sync a recurring break with custom recurrence pattern
        Supports non-weekly patterns (e.g., every 8 days)
        """
        try:
            event = {
                'summary': self._get_break_title(break_info.get('type', 'break')),
                'description': f'Sincronizado desde MediConnect - Evento recurrente cada {recurrence_pattern.get("frequency_days", "?")} días',
                'colorId': self._get_color_for_break_type(break_info.get('type', 'break')),
                'reminders': {
                    'useDefault': False,
                    'overrides': []
                }
            }
            
            # Calculate first occurrence
            if recurrence_pattern.get('day_of_week') is not None:
                next_date = self._get_next_weekday(recurrence_pattern['day_of_week'])
            else:
                next_date = date.today()
            
            start_datetime = datetime.combine(next_date, self._parse_time(break_info['start']))
            end_datetime = datetime.combine(next_date, self._parse_time(break_info['end']))
            
            event['start'] = {
                'dateTime': start_datetime.isoformat(),
                'timeZone': 'America/Mexico_City'
            }
            event['end'] = {
                'dateTime': end_datetime.isoformat(),
                'timeZone': 'America/Mexico_City'
            }
            
            # Create recurrence rule based on pattern
            frequency_days = recurrence_pattern.get('frequency_days', 7)
            
            if frequency_days == 7:
                # Weekly
                day_code = self._day_to_rrule(recurrence_pattern.get('day_of_week', 0))
                event['recurrence'] = [f"RRULE:FREQ=WEEKLY;BYDAY={day_code}"]
            elif frequency_days % 7 == 0:
                # Multi-week
                weeks = frequency_days // 7
                day_code = self._day_to_rrule(recurrence_pattern.get('day_of_week', 0))
                event['recurrence'] = [f"RRULE:FREQ=WEEKLY;INTERVAL={weeks};BYDAY={day_code}"]
            else:
                # Daily interval (for patterns like every 8 days)
                event['recurrence'] = [f"RRULE:FREQ=DAILY;INTERVAL={frequency_days}"]
            
            # Create the event
            created_event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event
            ).execute()
            
            event_id = created_event.get('id')
            self.tracked_event_ids.add(event_id)
            
            logger.info(f"Created recurring break event with pattern: {recurrence_pattern}")
            return event_id
            
        except Exception as e:
            logger.error(f"Error creating recurring break: {str(e)}")
            return None
    
    def sync_closed_day_to_calendar(self, date_str: str, reason: Optional[str] = None) -> Optional[str]:
        """Sync a closed day to Google Calendar as an all-day event"""
        try:
            event = {
                'summary': '🚫 Consultorio Cerrado',
                'description': f'MediConnect - {reason or "Día no laborable"}',
                'start': {
                    'date': date_str
                },
                'end': {
                    'date': date_str
                },
                'colorId': '11',  # Red color for closed days
                'transparency': 'transparent',  # Show as free in calendar
                'reminders': {
                    'useDefault': False
                }
            }
            
            created_event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event
            ).execute()
            
            event_id = created_event.get('id')
            self.tracked_event_ids.add(event_id)
            
            logger.info(f"Created closed day event: {event_id}")
            return event_id
            
        except Exception as e:
            logger.error(f"Error creating closed day event: {str(e)}")
            return None
    
    def sync_special_hours_to_calendar(self, date_str: str, opens_at: str, closes_at: str) -> Optional[str]:
        """Sync special hours to Google Calendar"""
        try:
            event = {
                'summary': f'⏰ Horario Especial: {opens_at} - {closes_at}',
                'description': 'MediConnect - Horario especial de atención',
                'start': {
                    'date': date_str
                },
                'end': {
                    'date': date_str
                },
                'colorId': '5',  # Yellow for special hours
                'transparency': 'transparent',
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 60}  # Reminder 1 hour before
                    ]
                }
            }
            
            created_event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event
            ).execute()
            
            event_id = created_event.get('id')
            self.tracked_event_ids.add(event_id)
            
            logger.info(f"Created special hours event: {event_id}")
            return event_id
            
        except Exception as e:
            logger.error(f"Error creating special hours event: {str(e)}")
            return None
    
    def sync_vacation_period_to_calendar(self, start_date: str, end_date: str) -> Optional[str]:
        """Sync vacation period as a multi-day event"""
        try:
            # Add 1 day to end_date for all-day events
            end_dt = datetime.fromisoformat(end_date).date() + timedelta(days=1)
            
            event = {
                'summary': '🏖️ Vacaciones - Consultorio Cerrado',
                'description': 'MediConnect - Período de vacaciones',
                'start': {
                    'date': start_date
                },
                'end': {
                    'date': end_dt.isoformat()
                },
                'colorId': '7',  # Turquoise for vacation
                'transparency': 'transparent',
                'reminders': {
                    'useDefault': False
                }
            }
            
            created_event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event
            ).execute()
            
            event_id = created_event.get('id')
            self.tracked_event_ids.add(event_id)
            
            logger.info(f"Created vacation period event: {event_id}")
            return event_id
            
        except Exception as e:
            logger.error(f"Error creating vacation event: {str(e)}")
            return None
    
    def delete_event(self, event_id: str) -> bool:
        """Delete an event from Google Calendar"""
        try:
            # First check if event exists
            try:
                self.service.events().get(
                    calendarId=self.calendar_id,
                    eventId=event_id
                ).execute()
            except HttpError as e:
                if e.resp.status == 404:
                    logger.warning(f"Event {event_id} not found, may have been already deleted")
                    return True
                raise
            
            # Delete the event
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            
            if event_id in self.tracked_event_ids:
                self.tracked_event_ids.remove(event_id)
            
            logger.info(f"Deleted event from Google Calendar: {event_id}")
            return True
            
        except HttpError as e:
            if e.resp.status == 410:  # Gone - event was already deleted
                logger.warning(f"Event {event_id} was already deleted")
                return True
            logger.error(f"Google Calendar API error deleting event: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error deleting event: {str(e)}")
            return False
    
    def bulk_delete_events(self, event_ids: List[str]) -> Dict[str, bool]:
        """Delete multiple events from Google Calendar"""
        results = {}
        
        for event_id in event_ids:
            try:
                success = self.delete_event(event_id)
                results[event_id] = success
            except Exception as e:
                logger.error(f"Error deleting event {event_id}: {str(e)}")
                results[event_id] = False
        
        logger.info(f"Bulk delete complete: {sum(results.values())}/{len(event_ids)} successful")
        return results
    
    def update_event(self, event_id: str, updates: Dict) -> bool:
        """Update an existing event in Google Calendar"""
        try:
            # Get current event
            event = self.service.events().get(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
            
            # Apply updates
            if 'summary' in updates:
                event['summary'] = updates['summary']
            
            if 'start_time' in updates and 'end_time' in updates:
                if 'start' in event and 'dateTime' in event['start']:
                    # Update time keeping the date
                    current_date = datetime.fromisoformat(event['start']['dateTime'].split('T')[0])
                    start_datetime = datetime.combine(current_date.date(), self._parse_time(updates['start_time']))
                    end_datetime = datetime.combine(current_date.date(), self._parse_time(updates['end_time']))
                    
                    event['start']['dateTime'] = start_datetime.isoformat()
                    event['end']['dateTime'] = end_datetime.isoformat()
            
            if 'description' in updates:
                event['description'] = updates['description']
            
            # Update the event
            updated_event = self.service.events().update(
                calendarId=self.calendar_id,
                eventId=event_id,
                body=event
            ).execute()
            
            logger.info(f"Updated event {event_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating event: {str(e)}")
            return False
    
    def get_mediconnect_events(self) -> List[str]:
        """Get all events created by MediConnect (for cleanup)"""
        try:
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                q='MediConnect',  # Search for our marker in description
                maxResults=2500,
                singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            event_ids = []
            
            for event in events:
                description = event.get('description', '')
                if 'MediConnect' in description or 'Sincronizado desde MediConnect' in description:
                    event_ids.append(event['id'])
            
            logger.info(f"Found {len(event_ids)} MediConnect events in Google Calendar")
            return event_ids
            
        except Exception as e:
            logger.error(f"Error getting MediConnect events: {str(e)}")
            return []
    
    def cleanup_all_mediconnect_events(self) -> int:
        """Remove all events created by MediConnect from Google Calendar"""
        event_ids = self.get_mediconnect_events()
        
        if not event_ids:
            logger.info("No MediConnect events to clean up")
            return 0
        
        results = self.bulk_delete_events(event_ids)
        successful = sum(results.values())
        
        logger.info(f"Cleaned up {successful}/{len(event_ids)} MediConnect events")
        return successful
    
    # Helper methods
    def _get_break_title(self, break_type: str) -> str:
        """Get appropriate title for break type"""
        titles = {
            'lunch': '🍽️ Hora de Comida',
            'break': '☕ Descanso',
            'administrative': '📋 Tiempo Administrativo',
            'personal': '👤 Asunto Personal'
        }
        return titles.get(break_type, '⏸️ Descanso')
    
    def _get_color_for_break_type(self, break_type: str) -> str:
        """Get Google Calendar color ID for break type"""
        colors = {
            'lunch': '10',  # Green
            'break': '9',   # Blue
            'administrative': '6',  # Orange
            'personal': '8'  # Gray
        }
        return colors.get(break_type, '9')
    
    def _parse_time(self, time_str: str) -> time:
        """Parse time string to time object"""
        if isinstance(time_str, time):
            return time_str
        
        # Remove microseconds if present
        time_str = time_str.split('.')[0] if '.' in time_str else time_str
        
        # Handle different formats
        if len(time_str) > 8:  # Has date component
            return datetime.fromisoformat(time_str).time()
        elif ':' in time_str:
            parts = time_str.split(':')
            if len(parts) == 3:
                return datetime.strptime(time_str, "%H:%M:%S").time()
            else:
                return datetime.strptime(time_str, "%H:%M").time()
        else:
            # Assume HH:MM format
            return datetime.strptime(f"{time_str}:00", "%H:%M").time()
    
    def _get_next_weekday(self, weekday: int) -> date:
        """Get the next occurrence of a weekday (0=Monday, 6=Sunday)"""
        today = date.today()
        days_ahead = weekday - today.weekday()
        
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        
        return today + timedelta(days=days_ahead)
    
    def _day_to_rrule(self, day_of_week: int) -> str:
        """Convert day of week number to RRULE format (0=Monday)"""
        days = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
        return days[day_of_week] if 0 <= day_of_week <= 6 else 'MO'