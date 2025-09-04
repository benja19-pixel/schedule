import requests
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional, Any
import pytz
from dateutil import parser
import json

class AppleCalendarService:
    """Service for interacting with Apple Calendar via Nylas API"""
    
    def __init__(self, access_token: str, nylas_client_id: Optional[str] = None, nylas_client_secret: Optional[str] = None):
        self.access_token = access_token
        self.nylas_client_id = nylas_client_id
        self.nylas_client_secret = nylas_client_secret
        self.base_url = "https://api.nylas.com"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    def get_user_info(self) -> Dict:
        """Get user's email and account info from Nylas"""
        try:
            response = requests.get(
                f"{self.base_url}/account",
                headers=self.headers
            )
            response.raise_for_status()
            
            account_data = response.json()
            return {
                'email': account_data.get('email_address', ''),
                'name': account_data.get('name', ''),
                'provider': account_data.get('provider', 'apple'),
                'account_id': account_data.get('account_id', '')
            }
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get user info from Nylas: {str(e)}")
    
    def get_calendars(self) -> List[Dict]:
        """Get list of user's calendars from Apple via Nylas"""
        try:
            response = requests.get(
                f"{self.base_url}/calendars",
                headers=self.headers
            )
            response.raise_for_status()
            
            calendars = []
            for calendar in response.json():
                calendars.append({
                    'id': calendar['id'],
                    'name': calendar.get('name', ''),
                    'description': calendar.get('description', ''),
                    'is_primary': calendar.get('is_primary', False),
                    'read_only': calendar.get('read_only', False)
                })
            
            return calendars
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get calendars: {str(e)}")
    
    def get_all_events(self, days_ahead: int = 365) -> Dict[str, List[Dict]]:
        """
        Get all events from Apple Calendar via Nylas categorized by type
        Returns: {
            'recurrent': [...],
            'special': [...],
            'all_day': [...]
        }
        """
        try:
            # Calculate time range
            starts_after = int(datetime.utcnow().timestamp())
            ends_before = int((datetime.utcnow() + timedelta(days=days_ahead)).timestamp())
            
            # Get events from Nylas
            response = requests.get(
                f"{self.base_url}/events",
                headers=self.headers,
                params={
                    'starts_after': starts_after,
                    'ends_before': ends_before,
                    'expand_recurring': 'false',  # Get recurring events as single items
                    'limit': 500
                }
            )
            response.raise_for_status()
            
            events = response.json()
            
            categorized = {
                'recurrent': [],
                'special': [],
                'all_day': []
            }
            
            for event in events:
                processed_event = self._process_nylas_event(event)
                
                if processed_event:
                    if processed_event['is_recurring']:
                        # For recurring events, get instances
                        expanded = self._expand_recurring_event_nylas(event['id'], starts_after, ends_before)
                        categorized['recurrent'].extend(expanded)
                    elif processed_event['is_all_day']:
                        categorized['all_day'].append(processed_event)
                    else:
                        categorized['special'].append(processed_event)
            
            return categorized
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to get events from Nylas: {str(e)}")
    
    def _process_nylas_event(self, event: Dict) -> Optional[Dict]:
        """Process a single Nylas event"""
        try:
            # Skip cancelled events
            if event.get('status') == 'cancelled':
                return None
            
            # Determine event type
            is_recurring = event.get('recurrence') is not None
            
            # Handle when field (Nylas uses Unix timestamps)
            when = event.get('when', {})
            
            # Check if all-day event
            is_all_day = when.get('object') == 'date'
            
            if is_all_day:
                start_date = datetime.fromtimestamp(when.get('start_date', 0)).date()
                end_date = datetime.fromtimestamp(when.get('end_date', 0)).date()
                start_time = None
                end_time = None
            else:
                # Time-based event
                start_datetime = datetime.fromtimestamp(when.get('start_time', 0))
                end_datetime = datetime.fromtimestamp(when.get('end_time', 0))
                start_date = start_datetime.date()
                end_date = end_datetime.date()
                start_time = start_datetime.time()
                end_time = end_datetime.time()
            
            return {
                'id': event['id'],
                'summary': event.get('title', 'Sin título'),
                'description': event.get('description', ''),
                'location': event.get('location', ''),
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'start_time': start_time.isoformat() if start_time else None,
                'end_time': end_time.isoformat() if end_time else None,
                'is_all_day': is_all_day,
                'is_recurring': is_recurring,
                'recurrence_rule': self._parse_nylas_recurrence(event.get('recurrence')) if is_recurring else None,
                'participants': len(event.get('participants', [])),
                'calendar_id': event.get('calendar_id'),
                'busy': event.get('busy', True),
                'read_only': event.get('read_only', False)
            }
            
        except Exception as e:
            print(f"Error processing Nylas event {event.get('id', 'unknown')}: {str(e)}")
            return None
    
    def _expand_recurring_event_nylas(self, event_id: str, starts_after: int, ends_before: int) -> List[Dict]:
        """Expand a recurring event into individual instances via Nylas"""
        try:
            # Get event instances
            response = requests.get(
                f"{self.base_url}/events",
                headers=self.headers,
                params={
                    'event_id': event_id,
                    'starts_after': starts_after,
                    'ends_before': ends_before,
                    'expand_recurring': 'true',
                    'limit': 100
                }
            )
            response.raise_for_status()
            
            instances = response.json()
            expanded_events = []
            
            for instance in instances:
                processed = self._process_nylas_event(instance)
                if processed:
                    processed['parent_event_id'] = event_id
                    expanded_events.append(processed)
            
            return expanded_events
            
        except requests.exceptions.RequestException as e:
            print(f"Error expanding recurring event: {str(e)}")
            return []
    
    def _parse_nylas_recurrence(self, recurrence: Optional[List[str]]) -> Dict:
        """Parse Nylas recurrence rules to determine pattern"""
        if not recurrence:
            return {}
        
        pattern = {
            'frequency': None,
            'interval': 1,
            'days_of_week': [],
            'day_of_month': None,
            'count': None,
            'until': None
        }
        
        # Nylas uses RRULE format similar to Google
        for rule in recurrence:
            if 'FREQ=' in rule:
                parts = dict(part.split('=') for part in rule.split(';') if '=' in part)
                
                pattern['frequency'] = parts.get('FREQ', '').lower()
                pattern['interval'] = int(parts.get('INTERVAL', 1))
                
                if 'BYDAY' in parts:
                    day_map = {'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5, 'SU': 6}
                    days = parts['BYDAY'].split(',')
                    pattern['days_of_week'] = [day_map.get(d[-2:], -1) for d in days]
                
                if 'COUNT' in parts:
                    pattern['count'] = int(parts['COUNT'])
                
                if 'UNTIL' in parts:
                    pattern['until'] = parts['UNTIL']
        
        return pattern
    
    def create_event(self, event_data: Dict) -> Dict:
        """Create a new event in Apple Calendar via Nylas"""
        try:
            # Build event body for Nylas
            event_body = {
                'title': event_data['summary'],
                'description': event_data.get('description', ''),
                'location': event_data.get('location', ''),
                'busy': True,
                'participants': []
            }
            
            # Handle date/time
            if event_data.get('all_day', False):
                # All-day event
                start_date = datetime.fromisoformat(event_data['start_date'])
                end_date = datetime.fromisoformat(event_data['end_date'])
                
                event_body['when'] = {
                    'object': 'date',
                    'start_date': int(start_date.timestamp()),
                    'end_date': int(end_date.timestamp())
                }
            else:
                # Time-based event
                start_datetime = datetime.fromisoformat(f"{event_data['start_date']}T{event_data['start_time']}")
                end_datetime = datetime.fromisoformat(f"{event_data['end_date']}T{event_data['end_time']}")
                
                event_body['when'] = {
                    'object': 'timespan',
                    'start_time': int(start_datetime.timestamp()),
                    'end_time': int(end_datetime.timestamp())
                }
            
            # Add recurrence if needed
            if event_data.get('recurrence'):
                event_body['recurrence'] = event_data['recurrence']
            
            # Set reminders if notifications are enabled
            if event_data.get('notifications', False):
                event_body['reminders'] = {
                    'use_default': False,
                    'overrides': [30]  # 30 minutes before
                }
            
            # Get primary calendar ID
            calendars = self.get_calendars()
            primary_calendar = next((cal for cal in calendars if cal.get('is_primary')), calendars[0] if calendars else None)
            
            if primary_calendar:
                event_body['calendar_id'] = primary_calendar['id']
            
            # Create the event
            response = requests.post(
                f"{self.base_url}/events",
                headers=self.headers,
                json=event_body
            )
            response.raise_for_status()
            
            created_event = response.json()
            
            return {
                'id': created_event['id'],
                'created': True
            }
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to create event in Nylas: {str(e)}")
    
    def update_event(self, event_id: str, event_data: Dict) -> Dict:
        """Update an existing event in Apple Calendar via Nylas"""
        try:
            # Build update body
            update_body = {}
            
            if 'summary' in event_data:
                update_body['title'] = event_data['summary']
            if 'description' in event_data:
                update_body['description'] = event_data['description']
            if 'location' in event_data:
                update_body['location'] = event_data['location']
            
            # Update date/time if provided
            if 'start_date' in event_data:
                if event_data.get('all_day', False):
                    start_date = datetime.fromisoformat(event_data['start_date'])
                    end_date = datetime.fromisoformat(event_data['end_date'])
                    
                    update_body['when'] = {
                        'object': 'date',
                        'start_date': int(start_date.timestamp()),
                        'end_date': int(end_date.timestamp())
                    }
                else:
                    start_datetime = datetime.fromisoformat(f"{event_data['start_date']}T{event_data['start_time']}")
                    end_datetime = datetime.fromisoformat(f"{event_data['end_date']}T{event_data['end_time']}")
                    
                    update_body['when'] = {
                        'object': 'timespan',
                        'start_time': int(start_datetime.timestamp()),
                        'end_time': int(end_datetime.timestamp())
                    }
            
            # Update the event
            response = requests.put(
                f"{self.base_url}/events/{event_id}",
                headers=self.headers,
                json=update_body
            )
            response.raise_for_status()
            
            return {
                'id': event_id,
                'updated': True
            }
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to update event in Nylas: {str(e)}")
    
    def delete_event(self, event_id: str) -> bool:
        """Delete an event from Apple Calendar via Nylas"""
        try:
            response = requests.delete(
                f"{self.base_url}/events/{event_id}",
                headers=self.headers
            )
            
            if response.status_code == 404:
                # Event already deleted
                return True
            
            response.raise_for_status()
            return True
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to delete event from Nylas: {str(e)}")
    
    def batch_create_events(self, events: List[Dict]) -> List[Dict]:
        """Create multiple events in batch"""
        results = []
        for event_data in events:
            try:
                result = self.create_event(event_data)
                results.append(result)
            except Exception as e:
                results.append({
                    'error': str(e),
                    'created': False,
                    'event_data': event_data
                })
        return results
    
    def batch_delete_events(self, event_ids: List[str]) -> Dict:
        """Delete multiple events in batch"""
        success_count = 0
        failed = []
        
        for event_id in event_ids:
            try:
                if self.delete_event(event_id):
                    success_count += 1
            except Exception as e:
                failed.append({
                    'event_id': event_id,
                    'error': str(e)
                })
        
        return {
            'deleted': success_count,
            'failed': failed
        }
    
    @staticmethod
    def get_oauth_url(nylas_client_id: str, redirect_uri: str, state: str = None) -> str:
        """Generate Nylas OAuth URL for Apple Calendar authentication"""
        params = {
            'client_id': nylas_client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scopes': 'calendar',
            'provider': 'icloud'
        }
        
        if state:
            params['state'] = state
        
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"https://api.nylas.com/oauth/authorize?{query_string}"
    
    @staticmethod
    def exchange_code_for_token(code: str, nylas_client_id: str, nylas_client_secret: str) -> Dict:
        """Exchange authorization code for access token"""
        try:
            response = requests.post(
                "https://api.nylas.com/oauth/token",
                json={
                    'client_id': nylas_client_id,
                    'client_secret': nylas_client_secret,
                    'grant_type': 'authorization_code',
                    'code': code
                }
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to exchange code for token: {str(e)}")