from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import logging
from dateutil import parser
from dateutil.rrule import rrulestr
import re

logger = logging.getLogger(__name__)

class GoogleCalendarService:
    """Service for interacting with Google Calendar API with improved recurrence handling"""
    
    def __init__(self, credentials: Credentials):
        """Initialize the Google Calendar service"""
        self.credentials = credentials
        self.service = build('calendar', 'v3', credentials=credentials)
        
    def get_user_info(self) -> Dict:
        """Get user's Google account information"""
        try:
            # Use the OAuth2 service to get user info
            oauth2_service = build('oauth2', 'v2', credentials=self.credentials)
            user_info = oauth2_service.userinfo().get().execute()
            
            return {
                'email': user_info.get('email'),
                'name': user_info.get('name'),
                'picture': user_info.get('picture')
            }
        except Exception as e:
            logger.error(f"Error getting user info: {str(e)}")
            return {'email': 'unknown@gmail.com'}
    
    def get_all_events(self, time_min: Optional[datetime] = None, time_max: Optional[datetime] = None) -> Dict:
        """
        Get all events from Google Calendar, organized by type
        Now only fetches FUTURE events and groups recurring events
        """
        try:
            # IMPORTANT: Only get future events from TODAY onwards
            if not time_min:
                time_min = datetime.now(timezone.utc)  # Start from NOW, not past
            
            if not time_max:
                time_max = time_min + timedelta(days=730)  # 2 years in future
            
            logger.info(f"Fetching events from {time_min.isoformat()} to {time_max.isoformat()}")
            
            # FIXED: Get recurring events WITHOUT orderBy (incompatible with singleEvents=False)
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=False,  # Get recurring events as series
                # orderBy='startTime',  # REMOVED - incompatible with singleEvents=False
                maxResults=2500  # Increase limit
            ).execute()
            
            raw_events = events_result.get('items', [])
            
            # Get expanded single events (WITH orderBy since singleEvents=True)
            single_events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,  # Expand recurring events
                orderBy='startTime',  # This works with singleEvents=True
                maxResults=2500
            ).execute()
            
            expanded_events = single_events_result.get('items', [])
            
            logger.info(f"Retrieved {len(raw_events)} raw events and {len(expanded_events)} expanded events")
            
            # Process and categorize events
            result = self._categorize_and_group_events(raw_events, expanded_events, time_min)
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching events: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'recurrent': [],
                'special': [],
                'all_day': [],
                'grouped_recurring': {}
            }
    
    def _categorize_and_group_events(self, raw_events: List, expanded_events: List, time_min: datetime) -> Dict:
        """
        Categorize events and group recurring ones
        """
        recurrent_events = []
        special_events = []
        all_day_events = []
        grouped_recurring = {}
        
        # Track recurring event IDs
        recurring_event_ids = set()
        
        # First pass: identify recurring events from raw events
        for event in raw_events:
            if event.get('status') == 'cancelled':
                continue
                
            # Check if it's a recurring event (has recurrence rule)
            if 'recurrence' in event:
                recurring_event_ids.add(event['id'])
                
                # Analyze the recurrence pattern
                pattern = self.analyze_recurrence_pattern(event.get('recurrence', []))
                
                # Parse the master event
                master_event = self._parse_event(event)
                if master_event:
                    master_event['recurring_group_id'] = event['id']
                    master_event['pattern'] = pattern
                    
                    # Create a group for this recurring event
                    grouped_recurring[event['id']] = {
                        'master_event': master_event,
                        'pattern': pattern,
                        'instances': [],
                        'recurring_group_id': event['id']
                    }
        
        # Second pass: process expanded events
        for event in expanded_events:
            if event.get('status') == 'cancelled':
                continue
            
            # Skip past events
            event_start = self._parse_datetime(event.get('start'))
            if event_start and event_start < time_min:
                continue
            
            parsed_event = self._parse_event(event)
            if not parsed_event:
                continue
            
            # Check if this is an instance of a recurring event
            recurring_event_id = event.get('recurringEventId')
            if recurring_event_id:
                # Add the recurring group ID to the event
                parsed_event['recurring_group_id'] = recurring_event_id
                parsed_event['is_recurring'] = True
                
                # Add to the appropriate group
                if recurring_event_id in grouped_recurring:
                    grouped_recurring[recurring_event_id]['instances'].append(parsed_event)
                    
                    # Add pattern info to the instance
                    if grouped_recurring[recurring_event_id]['pattern']:
                        parsed_event['pattern'] = grouped_recurring[recurring_event_id]['pattern']
                
                recurrent_events.append(parsed_event)
            else:
                # Check if it's all-day
                if self._is_all_day_event(event):
                    all_day_events.append(parsed_event)
                else:
                    # It's a special one-time event
                    special_events.append(parsed_event)
        
        # Log the categorization
        logger.info(f"Categorized events - Recurrent: {len(recurrent_events)}, "
                   f"Special: {len(special_events)}, All-day: {len(all_day_events)}, "
                   f"Grouped recurring: {len(grouped_recurring)} groups")
        
        return {
            'recurrent': recurrent_events,
            'special': special_events,
            'all_day': all_day_events,
            'grouped_recurring': grouped_recurring
        }
    
    def analyze_recurrence_pattern(self, recurrence_rules: List[str]) -> Dict:
        """
        Analyze RRULE to determine the recurrence pattern
        Returns pattern info including frequency in days
        """
        if not recurrence_rules:
            return {}
        
        pattern = {
            'frequency_days': None,
            'day_of_week': None,
            'pattern_type': 'custom',
            'rule': None
        }
        
        for rule in recurrence_rules:
            if rule.startswith('RRULE:'):
                try:
                    # Parse the RRULE
                    rrule_str = rule.replace('RRULE:', '')
                    pattern['rule'] = rrule_str
                    
                    # Extract components
                    components = {}
                    for part in rrule_str.split(';'):
                        if '=' in part:
                            key, value = part.split('=', 1)
                            components[key] = value
                    
                    freq = components.get('FREQ', '')
                    interval = int(components.get('INTERVAL', '1'))
                    
                    # Determine frequency in days
                    if freq == 'DAILY':
                        pattern['frequency_days'] = interval
                        pattern['pattern_type'] = 'daily'
                    elif freq == 'WEEKLY':
                        pattern['frequency_days'] = 7 * interval
                        pattern['pattern_type'] = 'weekly' if interval == 1 else 'custom'
                        
                        # Extract day of week from BYDAY or from the event's start date
                        if 'BYDAY' in components:
                            day_map = {'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5, 'SU': 6}
                            byday = components['BYDAY']
                            for day_code, day_num in day_map.items():
                                if day_code in byday:
                                    pattern['day_of_week'] = day_num
                                    break
                    elif freq == 'MONTHLY':
                        # Approximate monthly as 30 days
                        pattern['frequency_days'] = 30 * interval
                        pattern['pattern_type'] = 'monthly'
                    elif freq == 'YEARLY':
                        # Approximate yearly as 365 days
                        pattern['frequency_days'] = 365 * interval
                        pattern['pattern_type'] = 'yearly'
                    
                    logger.info(f"Analyzed pattern: {pattern}")
                    
                except Exception as e:
                    logger.error(f"Error parsing RRULE '{rule}': {str(e)}")
        
        return pattern
    
    def group_recurring_events(self, events_list: List[Dict]) -> Dict[str, Dict]:
        """
        Group recurring events by their recurringEventId
        Returns a dictionary with grouped events
        """
        groups = {}
        
        for event in events_list:
            recurring_id = event.get('recurring_group_id') or event.get('recurringEventId')
            if recurring_id:
                if recurring_id not in groups:
                    groups[recurring_id] = {
                        'group_id': recurring_id,
                        'master_event': event,
                        'instances': [],
                        'pattern': event.get('pattern', {}),
                        'count': 0
                    }
                
                groups[recurring_id]['instances'].append(event)
                groups[recurring_id]['count'] += 1
                
                # Update master event with the first instance's details if needed
                if groups[recurring_id]['count'] == 1:
                    groups[recurring_id]['master_event'] = event
        
        logger.info(f"Grouped {len(events_list)} events into {len(groups)} recurring groups")
        
        return groups
    
    def _parse_event(self, event: Dict) -> Optional[Dict]:
        """Parse a Google Calendar event into our format"""
        try:
            # Skip cancelled events
            if event.get('status') == 'cancelled':
                return None
            
            # Get start and end times
            start = event.get('start', {})
            end = event.get('end', {})
            
            # Parse datetime or date
            start_datetime = self._parse_datetime(start)
            end_datetime = self._parse_datetime(end)
            
            if not start_datetime:
                return None
            
            # Determine if it's all-day
            is_all_day = 'date' in start and 'dateTime' not in start
            
            # Get recurrence info
            recurring_event_id = event.get('recurringEventId')
            is_recurring = bool(recurring_event_id or event.get('recurrence'))
            
            parsed = {
                'id': event.get('id'),
                'summary': event.get('summary', 'Sin título'),
                'description': event.get('description', ''),
                'location': event.get('location', ''),
                'start_date': start_datetime.date().isoformat(),
                'end_date': end_datetime.date().isoformat() if end_datetime else start_datetime.date().isoformat(),
                'is_all_day': is_all_day,
                'is_recurring': is_recurring,
                'recurring_event_id': recurring_event_id,
                'status': event.get('status', 'confirmed'),
                'created': event.get('created'),
                'updated': event.get('updated')
            }
            
            # Add time info if not all-day
            if not is_all_day:
                parsed['start_time'] = start_datetime.time().isoformat()
                parsed['end_time'] = end_datetime.time().isoformat() if end_datetime else start_datetime.time().isoformat()
                parsed['start_datetime'] = start_datetime.isoformat()
                parsed['end_datetime'] = end_datetime.isoformat() if end_datetime else start_datetime.isoformat()
            
            # Add organizer info
            if 'organizer' in event:
                parsed['organizer'] = event['organizer'].get('email', '')
            
            # Add attendees count
            if 'attendees' in event:
                parsed['attendees_count'] = len(event['attendees'])
            
            return parsed
            
        except Exception as e:
            logger.error(f"Error parsing event: {str(e)}")
            logger.error(f"Event data: {event}")
            return None
    
    def _parse_datetime(self, dt_info: Dict) -> Optional[datetime]:
        """Parse datetime from Google Calendar format"""
        try:
            if 'dateTime' in dt_info:
                # Has specific time
                return parser.parse(dt_info['dateTime'])
            elif 'date' in dt_info:
                # All-day event (date only)
                return parser.parse(dt_info['date'])
            return None
        except Exception as e:
            logger.error(f"Error parsing datetime: {str(e)}")
            return None
    
    def _is_all_day_event(self, event: Dict) -> bool:
        """Check if an event is all-day"""
        start = event.get('start', {})
        return 'date' in start and 'dateTime' not in start
    
    def calculate_future_occurrences(self, pattern: Dict, start_date: str, limit_years: int = 2) -> List[str]:
        """
        Calculate future occurrence dates based on pattern
        Used for non-weekly recurring events
        """
        occurrences = []
        
        if not pattern.get('frequency_days'):
            return occurrences
        
        try:
            start = datetime.fromisoformat(start_date)
            end = start + timedelta(days=365 * limit_years)
            current = start
            
            while current <= end:
                occurrences.append(current.date().isoformat())
                current += timedelta(days=pattern['frequency_days'])
            
            logger.info(f"Calculated {len(occurrences)} future occurrences")
            
        except Exception as e:
            logger.error(f"Error calculating occurrences: {str(e)}")
        
        return occurrences
    
    def get_calendars_list(self) -> List[Dict]:
        """Get list of available calendars"""
        try:
            calendar_list = self.service.calendarList().list().execute()
            calendars = []
            
            for calendar in calendar_list.get('items', []):
                calendars.append({
                    'id': calendar['id'],
                    'summary': calendar.get('summary', 'Unnamed'),
                    'primary': calendar.get('primary', False),
                    'accessRole': calendar.get('accessRole'),
                    'backgroundColor': calendar.get('backgroundColor'),
                    'foregroundColor': calendar.get('foregroundColor')
                })
            
            return calendars
            
        except Exception as e:
            logger.error(f"Error getting calendars list: {str(e)}")
            return []