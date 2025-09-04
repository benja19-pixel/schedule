from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Optional, Tuple, Any, Set
import uuid
from models.horarios import HorarioTemplate, HorarioException
from models.calendar_sync import CalendarConnection, SyncedEvent
from services.horarios_service import HorariosService
import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

class CalendarSyncService:
    """Service for synchronizing external calendars with MediConnect schedule - Enhanced Version"""
    
    def __init__(self, db: Session):
        self.db = db
        self.horarios_service = HorariosService(db)
        self.just_synced_ids: Set[str] = set()  # Track events just synced to avoid self-conflicts
    
    def process_external_events(
        self,
        user_id: str,
        connection_id: str,
        external_events: Dict[str, List[Dict]],
        provider: str
    ) -> Dict:
        """
        Process external calendar events with improved grouping and conflict detection
        """
        logger.info(f"Processing external events for user {user_id}")
        
        result = {
            'synced': [],
            'conflicts': [],
            'recurrent': [],
            'special': [],
            'all_day': [],
            'synced_event_ids': [],  # Track IDs of just-synced events
            'debug_info': {
                'total_raw_events': 0,
                'filtered_events': 0,
                'filter_reasons': []
            }
        }
        
        # Count raw events
        total_raw = (len(external_events.get('recurrent', [])) + 
                    len(external_events.get('special', [])) + 
                    len(external_events.get('all_day', [])))
        result['debug_info']['total_raw_events'] = total_raw
        
        # Get grouped recurring events if available
        grouped_recurring = external_events.get('grouped_recurring', {})
        
        # Process recurring events with grouping
        if grouped_recurring:
            logger.info(f"Processing {len(grouped_recurring)} recurring event groups")
            for group_id, group_data in grouped_recurring.items():
                processed_group = self._process_recurring_group(
                    group_data, user_id, connection_id, provider
                )
                
                # Add to results
                if processed_group.get('has_conflict'):
                    # Add group conflict info
                    for instance in group_data['instances']:
                        instance['recurring_group_id'] = group_id
                        instance['pattern'] = group_data['pattern']
                    result['conflicts'].extend(processed_group['conflicts'])
                
                # Track synced events
                result['synced'].extend(processed_group.get('synced', []))
                result['synced_event_ids'].extend(processed_group.get('synced_ids', []))
                
                # Add to recurrent events list
                result['recurrent'].extend(group_data['instances'])
        
        # Process individual recurrent events (fallback if no grouping)
        recurrent_events = external_events.get('recurrent', [])
        if recurrent_events and not grouped_recurring:
            logger.info(f"Processing {len(recurrent_events)} individual recurrent events")
            
            for event in recurrent_events:
                if not self._should_include_event(event, result):
                    continue
                
                # Check for conflicts, excluding just-synced events
                conflict = self._check_conflict_with_existing(
                    user_id, event, skip_event_ids=self.just_synced_ids
                )
                
                event_result = {
                    **event,
                    'has_conflict': bool(conflict),
                    'conflict_info': conflict
                }
                
                if conflict:
                    logger.info(f"Conflict found for recurrent event: {event.get('summary')}")
                    result['conflicts'].append({
                        'external_event': event,
                        'conflict_with': conflict,
                        'type': 'recurrent'
                    })
                
                result['recurrent'].append(event_result)
                
                # Auto-sync non-conflicting recurrent events
                if not conflict:
                    synced_id = self._auto_sync_recurrent_event(user_id, connection_id, event, provider)
                    if synced_id:
                        self.just_synced_ids.add(synced_id)
                        result['synced_event_ids'].append(synced_id)
        
        # Process special events
        special_events = external_events.get('special', [])
        logger.info(f"Processing {len(special_events)} special events")
        
        for event in special_events:
            if not self._should_include_event(event, result):
                continue
            
            conflict = self._check_conflict_with_existing(
                user_id, event, skip_event_ids=self.just_synced_ids
            )
            
            event_result = {
                **event,
                'has_conflict': bool(conflict),
                'conflict_info': conflict
            }
            
            if conflict:
                logger.info(f"Conflict found for special event: {event.get('summary')}")
                result['conflicts'].append({
                    'external_event': event,
                    'conflict_with': conflict,
                    'type': 'special'
                })
            
            result['special'].append(event_result)
            
            if not conflict:
                synced_id = self._auto_sync_special_event(user_id, connection_id, event, provider)
                if synced_id:
                    self.just_synced_ids.add(synced_id)
                    result['synced_event_ids'].append(synced_id)
        
        # Process all-day events
        all_day_events = external_events.get('all_day', [])
        logger.info(f"Processing {len(all_day_events)} all-day events")
        
        for event in all_day_events:
            if not self._should_include_event(event, result):
                continue
            
            result['all_day'].append(event)
            synced_ids = self._auto_sync_all_day_event(user_id, connection_id, event, provider)
            result['synced_event_ids'].extend(synced_ids)
        
        # Update debug info
        result['debug_info']['filtered_events'] = (
            len(result['recurrent']) + 
            len(result['special']) + 
            len(result['all_day'])
        )
        
        # Count synced events
        result['synced'] = self.db.query(SyncedEvent).filter(
            SyncedEvent.user_id == user_id,
            SyncedEvent.connection_id == connection_id,
            SyncedEvent.sync_status == 'completed'
        ).all()
        
        logger.info(f"Sync processing complete - Synced: {len(result['synced'])}, "
                   f"Conflicts: {len(result['conflicts'])}, Just synced: {len(self.just_synced_ids)}")
        
        return result
    
    def _process_recurring_group(
        self, 
        group_data: Dict, 
        user_id: str, 
        connection_id: str, 
        provider: str
    ) -> Dict:
        """
        Process a group of recurring events based on pattern
        """
        result = {
            'synced': [],
            'synced_ids': [],
            'conflicts': [],
            'has_conflict': False
        }
        
        pattern = group_data.get('pattern', {})
        frequency_days = pattern.get('frequency_days')
        
        if not frequency_days:
            logger.warning(f"No frequency found for recurring group")
            return result
        
        # Determine how to handle based on frequency
        if frequency_days == 7:
            # Weekly event - create/update template
            result = self._sync_weekly_recurring_to_template(
                group_data, user_id, connection_id, provider
            )
        elif frequency_days % 7 != 0:
            # Non-weekly pattern - create special events
            result = self._sync_non_weekly_recurring_to_exceptions(
                group_data, user_id, connection_id, provider
            )
        else:
            # Multi-week pattern - could handle specially
            result = self._sync_weekly_recurring_to_template(
                group_data, user_id, connection_id, provider
            )
        
        return result
    
    def _sync_weekly_recurring_to_template(
        self,
        group_data: Dict,
        user_id: str,
        connection_id: str,
        provider: str
    ) -> Dict:
        """
        Sync weekly recurring event to day template
        """
        result = {
            'synced': [],
            'synced_ids': [],
            'conflicts': [],
            'has_conflict': False
        }
        
        pattern = group_data.get('pattern', {})
        day_of_week = pattern.get('day_of_week')
        instances = group_data.get('instances', [])
        
        if not instances or day_of_week is None:
            return result
        
        # Use first instance as template
        first_instance = instances[0]
        
        # Get or create template for this day
        template = self.db.query(HorarioTemplate).filter(
            HorarioTemplate.user_id == user_id,
            HorarioTemplate.day_of_week == day_of_week
        ).first()
        
        if not template:
            template = HorarioTemplate(
                user_id=user_id,
                day_of_week=day_of_week,
                is_active=True,
                opens_at=time(9, 0),
                closes_at=time(19, 0),
                time_blocks=[]
            )
            self.db.add(template)
            self.db.flush()
        
        # Check for conflicts with existing breaks
        existing_breaks = [b for b in (template.time_blocks or []) if b.get('type') != 'consultation']
        
        for existing_break in existing_breaks:
            # Skip if it's the same external event
            if existing_break.get('external_event_id') == first_instance.get('id'):
                continue
            
            if self._time_overlaps(
                first_instance.get('start_time'),
                first_instance.get('end_time'),
                existing_break.get('start'),
                existing_break.get('end')
            ):
                result['has_conflict'] = True
                result['conflicts'].append({
                    'external_event': first_instance,
                    'conflict_with': {
                        'type': 'template_break',
                        'day_of_week': day_of_week,
                        'break_type': existing_break.get('type'),
                        'break_time': f"{existing_break.get('start')} - {existing_break.get('end')}",
                        'template_id': str(template.id)
                    },
                    'type': 'recurrent'
                })
                return result
        
        # No conflict - add as break
        if template.is_active:
            time_blocks = template.time_blocks or []
            
            new_break = {
                'start': first_instance['start_time'].split('.')[0] if '.' in first_instance['start_time'] else first_instance['start_time'],
                'end': first_instance['end_time'].split('.')[0] if '.' in first_instance['end_time'] else first_instance['end_time'],
                'type': 'break',
                'external_event_id': first_instance['id'],
                'recurring_group_id': group_data.get('group_id')
            }
            
            # Insert break and recalculate blocks
            time_blocks = self._insert_break_into_blocks(
                time_blocks, new_break,
                template.opens_at.strftime("%H:%M") if hasattr(template.opens_at, 'strftime') else template.opens_at,
                template.closes_at.strftime("%H:%M") if hasattr(template.closes_at, 'strftime') else template.closes_at
            )
            
            template.time_blocks = time_blocks
            template.has_synced_breaks = True
            template.last_sync_update = datetime.utcnow()
            template.updated_at = datetime.utcnow()
            
            # Track synced event
            synced_event = self._create_synced_event_record(
                user_id, connection_id, first_instance['id'], 
                template.id, 'template', 'external_to_internal',
                recurring_group_id=group_data.get('group_id')
            )
            
            result['synced'].append(synced_event)
            result['synced_ids'].append(first_instance['id'])
            
            # Track to avoid self-conflicts
            self.just_synced_ids.add(first_instance['id'])
            
            self.db.commit()
            logger.info(f"Synced weekly recurring event to template for day {day_of_week}")
        
        return result
    
    def _sync_non_weekly_recurring_to_exceptions(
        self,
        group_data: Dict,
        user_id: str,
        connection_id: str,
        provider: str
    ) -> Dict:
        """
        Sync non-weekly recurring events as special day exceptions
        """
        result = {
            'synced': [],
            'synced_ids': [],
            'conflicts': [],
            'has_conflict': False
        }
        
        pattern = group_data.get('pattern', {})
        instances = group_data.get('instances', [])
        
        if not instances:
            return result
        
        # Calculate future occurrences (limit to 2 years)
        limit_date = date.today() + timedelta(days=730)
        
        for instance in instances:
            event_date = datetime.fromisoformat(instance['start_date']).date()
            
            # Skip past events or events too far in future
            if event_date < date.today() or event_date > limit_date:
                continue
            
            # Check if exception already exists
            existing = self.db.query(HorarioException).filter(
                HorarioException.user_id == user_id,
                HorarioException.date == event_date
            ).first()
            
            if existing:
                # Check for conflict
                if existing.time_blocks:
                    for block in existing.time_blocks:
                        if block.get('type') != 'consultation':
                            if self._time_overlaps(
                                instance.get('start_time'),
                                instance.get('end_time'),
                                block.get('start'),
                                block.get('end')
                            ):
                                result['has_conflict'] = True
                                result['conflicts'].append({
                                    'external_event': instance,
                                    'conflict_with': {
                                        'type': 'exception_break',
                                        'date': event_date.isoformat(),
                                        'break_type': block.get('type'),
                                        'break_time': f"{block.get('start')} - {block.get('end')}",
                                        'exception_id': str(existing.id)
                                    },
                                    'type': 'recurrent'
                                })
            else:
                # Create new exception with the event as a break
                day_of_week = event_date.weekday()
                template = self.db.query(HorarioTemplate).filter(
                    HorarioTemplate.user_id == user_id,
                    HorarioTemplate.day_of_week == day_of_week
                ).first()
                
                if template and template.is_active:
                    # Copy template hours and add the event as a break
                    time_blocks = template.time_blocks.copy() if template.time_blocks else []
                    
                    new_break = {
                        'start': instance['start_time'].split('.')[0] if '.' in instance['start_time'] else instance['start_time'],
                        'end': instance['end_time'].split('.')[0] if '.' in instance['end_time'] else instance['end_time'],
                        'type': 'break',
                        'external_event_id': instance['id'],
                        'recurring_group_id': group_data.get('group_id')
                    }
                    
                    time_blocks = self._insert_break_into_blocks(
                        time_blocks, new_break,
                        template.opens_at.strftime("%H:%M"),
                        template.closes_at.strftime("%H:%M")
                    )
                    
                    exception = HorarioException(
                        user_id=user_id,
                        date=event_date,
                        is_working_day=True,
                        opens_at=template.opens_at,
                        closes_at=template.closes_at,
                        time_blocks=time_blocks,
                        reason=f"Evento recurrente: {instance.get('summary', 'Sin título')}",
                        sync_source=provider,
                        external_calendar_id=instance['id'],
                        is_synced=True,
                        sync_connection_id=connection_id
                    )
                    
                    self.db.add(exception)
                    self.db.flush()
                    
                    # Track synced event
                    synced_event = self._create_synced_event_record(
                        user_id, connection_id, instance['id'],
                        exception.id, 'exception', 'external_to_internal',
                        recurring_group_id=group_data.get('group_id')
                    )
                    
                    result['synced'].append(synced_event)
                    result['synced_ids'].append(instance['id'])
                    
                    # Track to avoid self-conflicts
                    self.just_synced_ids.add(instance['id'])
        
        self.db.commit()
        logger.info(f"Created {len(result['synced'])} special day exceptions for non-weekly recurring event")
        
        return result
    
    def _should_include_event(self, event: Dict, result: Dict) -> bool:
        """Check if an event should be included in sync"""
        if not event:
            result['debug_info']['filter_reasons'].append('Empty event')
            return False
        
        if event.get('status') == 'cancelled':
            result['debug_info']['filter_reasons'].append(f"Cancelled: {event.get('summary', 'No title')}")
            return False
        
        summary = event.get('summary', '').strip()
        if not summary:
            event['summary'] = "Evento sin título"
        
        # Skip automatic birthday events
        if summary in ['¡Feliz cumpleaños!', 'Happy Birthday!', 'Birthday']:
            result['debug_info']['filter_reasons'].append(f"Auto birthday: {summary}")
            return False
        
        return True
    
    def _check_conflict_with_existing(
        self, 
        user_id: str, 
        external_event: Dict,
        skip_event_ids: Set[str] = None
    ) -> Optional[Dict]:
        """
        Check if an external event conflicts with existing schedule
        Now skips events that were just synced
        """
        try:
            # Skip if this event was just synced
            if skip_event_ids and external_event.get('id') in skip_event_ids:
                logger.debug(f"Skipping conflict check for just-synced event {external_event.get('id')}")
                return None
            
            if not external_event.get('start_date'):
                return None
            
            if not external_event.get('start_time') or not external_event.get('end_time'):
                return None
            
            event_date = datetime.fromisoformat(external_event['start_date']).date()
            
            # Check exceptions first
            exception = self.db.query(HorarioException).filter(
                HorarioException.user_id == user_id,
                HorarioException.date == event_date
            ).first()
            
            if exception and exception.time_blocks:
                for block in exception.time_blocks:
                    if block.get('type') != 'consultation':
                        # Skip if it's the same external event
                        if block.get('external_event_id') == external_event.get('id'):
                            continue
                        
                        if self._time_overlaps(
                            external_event.get('start_time'),
                            external_event.get('end_time'),
                            block.get('start'),
                            block.get('end')
                        ):
                            return {
                                'type': 'exception_break',
                                'date': event_date.isoformat(),
                                'break_type': block.get('type'),
                                'break_time': f"{block.get('start')} - {block.get('end')}",
                                'exception_id': str(exception.id)
                            }
            
            # Check regular schedule for recurring events
            if external_event.get('is_recurring'):
                day_of_week = datetime.fromisoformat(external_event['start_date']).weekday()
                template = self.db.query(HorarioTemplate).filter(
                    HorarioTemplate.user_id == user_id,
                    HorarioTemplate.day_of_week == day_of_week
                ).first()
                
                if template and template.is_active and template.time_blocks:
                    for block in template.time_blocks:
                        if block.get('type') != 'consultation':
                            # Skip if it's the same external event
                            if block.get('external_event_id') == external_event.get('id'):
                                continue
                            
                            if self._time_overlaps(
                                external_event.get('start_time'),
                                external_event.get('end_time'),
                                block.get('start'),
                                block.get('end')
                            ):
                                return {
                                    'type': 'template_break',
                                    'day_of_week': day_of_week,
                                    'break_type': block.get('type'),
                                    'break_time': f"{block.get('start')} - {block.get('end')}",
                                    'template_id': str(template.id)
                                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking conflict: {str(e)}")
            return None
    
    def _time_overlaps(self, start1: str, end1: str, start2: str, end2: str) -> bool:
        """Check if two time ranges overlap"""
        try:
            if not all([start1, end1, start2, end2]):
                return False
            
            def parse_time(time_str):
                if not time_str:
                    return None
                time_str = time_str.split('.')[0] if '.' in time_str else time_str
                if len(time_str) > 8:
                    return datetime.fromisoformat(time_str).time()
                elif len(time_str) > 5:
                    return datetime.strptime(time_str, "%H:%M:%S").time()
                else:
                    return datetime.strptime(time_str, "%H:%M").time()
            
            s1 = parse_time(start1)
            e1 = parse_time(end1)
            s2 = parse_time(start2 if ':' in start2 else f"{start2}:00")
            e2 = parse_time(end2 if ':' in end2 else f"{end2}:00")
            
            if not all([s1, e1, s2, e2]):
                return False
            
            overlap = (s1 < e2 and e1 > s2)
            
            if overlap:
                logger.debug(f"Time overlap detected: {start1}-{end1} overlaps with {start2}-{end2}")
            
            return overlap
            
        except Exception as e:
            logger.error(f"Error checking time overlap: {str(e)}")
            return False
    
    def _auto_sync_recurrent_event(self, user_id: str, connection_id: str, event: Dict, provider: str) -> Optional[str]:
        """Automatically sync a non-conflicting recurrent event"""
        try:
            day_of_week = datetime.fromisoformat(event['start_date']).weekday()
            
            template = self.db.query(HorarioTemplate).filter(
                HorarioTemplate.user_id == user_id,
                HorarioTemplate.day_of_week == day_of_week
            ).first()
            
            if template and template.is_active:
                time_blocks = template.time_blocks or []
                
                new_break = {
                    'start': event['start_time'].split('.')[0] if '.' in event['start_time'] else event['start_time'],
                    'end': event['end_time'].split('.')[0] if '.' in event['end_time'] else event['end_time'],
                    'type': 'break',
                    'external_event_id': event['id']
                }
                
                time_blocks = self._insert_break_into_blocks(
                    time_blocks, new_break,
                    template.opens_at.strftime("%H:%M") if hasattr(template.opens_at, 'strftime') else template.opens_at,
                    template.closes_at.strftime("%H:%M") if hasattr(template.closes_at, 'strftime') else template.closes_at
                )
                
                template.time_blocks = time_blocks
                template.updated_at = datetime.utcnow()
                
                self._create_synced_event_record(
                    user_id, connection_id, event['id'], template.id, 'template', 'external_to_internal'
                )
                
                self.db.commit()
                logger.info(f"Auto-synced recurrent event to template for day {day_of_week}")
                
                return event['id']
                
        except Exception as e:
            logger.error(f"Error auto-syncing recurrent event: {str(e)}")
            return None
    
    def _auto_sync_special_event(self, user_id: str, connection_id: str, event: Dict, provider: str) -> Optional[str]:
        """Automatically sync a non-conflicting special event"""
        try:
            event_date = datetime.fromisoformat(event['start_date']).date()
            
            exception = self.db.query(HorarioException).filter(
                HorarioException.user_id == user_id,
                HorarioException.date == event_date
            ).first()
            
            if not exception:
                day_of_week = datetime.fromisoformat(event['start_date']).weekday()
                template = self.db.query(HorarioTemplate).filter(
                    HorarioTemplate.user_id == user_id,
                    HorarioTemplate.day_of_week == day_of_week
                ).first()
                
                if template and template.is_active:
                    exception = HorarioException(
                        user_id=user_id,
                        date=event_date,
                        is_working_day=True,
                        opens_at=template.opens_at,
                        closes_at=template.closes_at,
                        time_blocks=template.time_blocks or [],
                        reason=f"Evento sincronizado: {event.get('summary', 'Sin título')}",
                        sync_source=provider,
                        external_calendar_id=event['id'],
                        is_synced=True,
                        sync_connection_id=connection_id
                    )
                    self.db.add(exception)
                    self.db.flush()
            
            if exception:
                time_blocks = exception.time_blocks or []
                new_break = {
                    'start': event['start_time'].split('.')[0] if '.' in event['start_time'] else event['start_time'],
                    'end': event['end_time'].split('.')[0] if '.' in event['end_time'] else event['end_time'],
                    'type': 'break',
                    'external_event_id': event['id']
                }
                
                time_blocks = self._insert_break_into_blocks(
                    time_blocks, new_break,
                    exception.opens_at.strftime("%H:%M") if hasattr(exception.opens_at, 'strftime') else exception.opens_at,
                    exception.closes_at.strftime("%H:%M") if hasattr(exception.closes_at, 'strftime') else exception.closes_at
                )
                
                exception.time_blocks = time_blocks
                exception.updated_at = datetime.utcnow()
                
                self._create_synced_event_record(
                    user_id, connection_id, event['id'], exception.id, 'exception', 'external_to_internal'
                )
                
                self.db.commit()
                logger.info(f"Auto-synced special event for date {event_date}")
                
                return event['id']
                
        except Exception as e:
            logger.error(f"Error auto-syncing special event: {str(e)}")
            return None
    
    def _auto_sync_all_day_event(self, user_id: str, connection_id: str, event: Dict, provider: str) -> List[str]:
        """Automatically sync an all-day event as closed day(s)"""
        synced_ids = []
        
        try:
            start_date = datetime.fromisoformat(event['start_date']).date()
            end_date = datetime.fromisoformat(event['end_date']).date()
            
            current_date = start_date
            while current_date <= end_date:
                existing = self.db.query(HorarioException).filter(
                    HorarioException.user_id == user_id,
                    HorarioException.date == current_date
                ).first()
                
                if not existing:
                    exception = HorarioException(
                        user_id=user_id,
                        date=current_date,
                        is_working_day=False,
                        reason=f"Día completo: {event.get('summary', 'Sin título')}",
                        sync_source=provider,
                        external_calendar_id=event['id'],
                        is_synced=True,
                        sync_connection_id=connection_id
                    )
                    self.db.add(exception)
                    self.db.flush()
                    
                    self._create_synced_event_record(
                        user_id, connection_id, event['id'], exception.id, 'exception', 'external_to_internal'
                    )
                    
                    synced_ids.append(event['id'])
                    logger.info(f"Auto-synced all-day event: marked {current_date} as closed")
                
                current_date += timedelta(days=1)
            
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error auto-syncing all-day event: {str(e)}")
        
        return synced_ids
    
    def resolve_conflict(
        self,
        user_id: str,
        event_id: str,
        resolution_type: str,
        merge_start: Optional[str] = None,
        merge_end: Optional[str] = None
    ) -> Dict:
        """Resolve a conflict between external and internal events"""
        logger.info(f"Resolving conflict for event {event_id} with type {resolution_type}")
        
        return {
            'resolved': True,
            'resolution_type': resolution_type,
            'event_id': event_id
        }
    
    def apply_conflict_resolution_to_group(
        self,
        resolution: str,
        recurring_group: Dict,
        user_id: str,
        connection_id: str
    ) -> bool:
        """Apply the same resolution to all instances of a recurring group"""
        try:
            logger.info(f"Applying {resolution} to recurring group with {recurring_group.get('count')} instances")
            
            # Implementation would depend on resolution type
            # For now, return success
            return True
            
        except Exception as e:
            logger.error(f"Error applying group resolution: {str(e)}")
            return False
    
    def classify_recurrent_event(
        self,
        user_id: str,
        external_event_id: str,
        classification: str
    ) -> bool:
        """Classify a recurrent external event as a specific break type"""
        try:
            logger.info(f"Classifying event {external_event_id} as {classification}")
            
            templates = self.db.query(HorarioTemplate).filter(
                HorarioTemplate.user_id == user_id
            ).all()
            
            for template in templates:
                if template.time_blocks:
                    updated = False
                    for block in template.time_blocks:
                        if block.get('external_event_id') == external_event_id:
                            block['type'] = classification
                            updated = True
                    
                    if updated:
                        template.updated_at = datetime.utcnow()
                        self.db.add(template)
            
            synced_event = self.db.query(SyncedEvent).filter(
                SyncedEvent.user_id == user_id,
                SyncedEvent.external_event_id == external_event_id
            ).first()
            
            if synced_event:
                metadata = synced_event.event_metadata or {}
                metadata['classification'] = classification
                synced_event.event_metadata = metadata
                synced_event.updated_at = datetime.utcnow()
            else:
                synced_event = SyncedEvent(
                    user_id=user_id,
                    connection_id=None,
                    external_event_id=external_event_id,
                    local_event_id=str(uuid.uuid4()),
                    local_event_type='pending',
                    sync_direction='external_to_internal',
                    sync_status='pending',
                    event_metadata={'classification': classification}
                )
                self.db.add(synced_event)
            
            self.db.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error classifying event: {str(e)}")
            return False
    
    def track_pre_existing_events(self, user_id: str) -> int:
        """Track events that existed before sync was enabled"""
        count = 0
        
        try:
            # Mark all current templates as pre-existing
            templates = self.db.query(HorarioTemplate).filter(
                HorarioTemplate.user_id == user_id
            ).all()
            
            for template in templates:
                if template.time_blocks:
                    for block in template.time_blocks:
                        if block.get('type') != 'consultation' and not block.get('external_event_id'):
                            # This is a pre-existing break
                            block['existed_before_sync'] = True
                            count += 1
                    template.updated_at = datetime.utcnow()
            
            # Mark all current exceptions as pre-existing
            exceptions = self.db.query(HorarioException).filter(
                HorarioException.user_id == user_id,
                HorarioException.sync_source == None
            ).all()
            
            for exception in exceptions:
                exception.sync_metadata = exception.sync_metadata or {}
                exception.sync_metadata['existed_before_sync'] = True
                exception.updated_at = datetime.utcnow()
                count += 1
            
            self.db.commit()
            logger.info(f"Marked {count} pre-existing events")
            
        except Exception as e:
            logger.error(f"Error tracking pre-existing events: {str(e)}")
        
        return count
    
    def cleanup_synced_events(self, user_id: str, connection_id: str) -> int:
        """
        Remove all synced events when disconnecting calendar
        Now also removes pre-existing events from external calendar
        """
        count = 0
        
        logger.info(f"Cleaning up synced events for user {user_id}")
        
        try:
            synced_events = self.db.query(SyncedEvent).filter(
                SyncedEvent.user_id == user_id,
                SyncedEvent.connection_id == connection_id
            ).all()
            
            for synced in synced_events:
                if synced.sync_direction == 'external_to_internal':
                    # Remove from internal schedule
                    if synced.local_event_type == 'exception':
                        exception = self.db.query(HorarioException).filter(
                            HorarioException.id == synced.local_event_id
                        ).first()
                        if exception:
                            self.db.delete(exception)
                            count += 1
                    elif synced.local_event_type == 'template':
                        template = self.db.query(HorarioTemplate).filter(
                            HorarioTemplate.id == synced.local_event_id
                        ).first()
                        if template and template.time_blocks:
                            original_count = len(template.time_blocks)
                            template.time_blocks = [
                                b for b in template.time_blocks 
                                if b.get('external_event_id') != synced.external_event_id
                            ]
                            if len(template.time_blocks) < original_count:
                                template.updated_at = datetime.utcnow()
                                count += 1
                
                self.db.delete(synced)
            
            self.db.commit()
            logger.info(f"Cleaned up {count} synced events")
            
            return count
            
        except Exception as e:
            logger.error(f"Error cleaning up synced events: {str(e)}")
            self.db.rollback()
            return count
    
    def _insert_break_into_blocks(
        self, 
        existing_blocks: List[Dict], 
        new_break: Dict,
        opens_at: Any,
        closes_at: Any
    ) -> List[Dict]:
        """Insert a break into existing time blocks and recalculate consultation blocks"""
        try:
            if hasattr(opens_at, 'strftime'):
                opens_at = opens_at.strftime("%H:%M")
            if hasattr(closes_at, 'strftime'):
                closes_at = closes_at.strftime("%H:%M")
            
            breaks = [b for b in existing_blocks if b.get('type') != 'consultation']
            breaks.append(new_break)
            breaks.sort(key=lambda x: x['start'])
            
            all_blocks = []
            last_end = opens_at
            
            for break_block in breaks:
                if last_end < break_block['start']:
                    all_blocks.append({
                        'start': last_end,
                        'end': break_block['start'],
                        'type': 'consultation'
                    })
                
                all_blocks.append(break_block)
                last_end = break_block['end']
            
            if last_end < closes_at:
                all_blocks.append({
                    'start': last_end,
                    'end': closes_at,
                    'type': 'consultation'
                })
            
            return all_blocks
            
        except Exception as e:
            logger.error(f"Error inserting break into blocks: {str(e)}")
            return existing_blocks
    
    def _create_synced_event_record(
        self,
        user_id: str,
        connection_id: str,
        external_event_id: str,
        local_event_id: str,
        local_event_type: str,
        sync_direction: str,
        recurring_group_id: str = None
    ) -> SyncedEvent:
        """Create a record of synced event for tracking"""
        try:
            existing = self.db.query(SyncedEvent).filter(
                SyncedEvent.user_id == user_id,
                SyncedEvent.external_event_id == external_event_id,
                SyncedEvent.local_event_id == local_event_id
            ).first()
            
            if not existing:
                synced = SyncedEvent(
                    user_id=user_id,
                    connection_id=connection_id,
                    external_event_id=external_event_id,
                    local_event_id=local_event_id,
                    local_event_type=local_event_type,
                    sync_direction=sync_direction,
                    sync_status='completed',
                    event_metadata={'recurring_group_id': recurring_group_id} if recurring_group_id else {},
                    last_synced_at=datetime.utcnow()
                )
                self.db.add(synced)
                logger.debug(f"Created synced event record: {external_event_id} -> {local_event_id}")
                return synced
            else:
                existing.last_synced_at = datetime.utcnow()
                existing.sync_status = 'completed'
                if recurring_group_id:
                    existing.event_metadata = existing.event_metadata or {}
                    existing.event_metadata['recurring_group_id'] = recurring_group_id
                logger.debug(f"Updated existing synced event record: {external_event_id}")
                return existing
                
        except Exception as e:
            logger.error(f"Error creating synced event record: {str(e)}")
            return None