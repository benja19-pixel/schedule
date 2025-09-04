from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Optional, Tuple, Any
import uuid
import logging

logger = logging.getLogger(__name__)

class ConflictResolutionService:
    """Service for detecting and resolving conflicts between external calendar events and internal schedule"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def detect_conflict(self, external_event: Dict, internal_schedule: Dict) -> Optional[Dict]:
        """
        Detect if an external event conflicts with internal schedule breaks
        Returns conflict details if found, None otherwise
        """
        if not external_event.get('start_time') or not external_event.get('end_time'):
            return None
            
        external_start = self._parse_time(external_event['start_time'])
        external_end = self._parse_time(external_event['end_time'])
        
        # Check against breaks in the schedule
        for block in internal_schedule.get('time_blocks', []):
            if block.get('type') != 'consultation':  # It's a break
                block_start = self._parse_time(block['start'])
                block_end = self._parse_time(block['end'])
                
                # Check for overlap
                if self._times_overlap(external_start, external_end, block_start, block_end):
                    return {
                        'type': 'break_conflict',
                        'external_event': external_event,
                        'internal_break': block,
                        'overlap_type': self._get_overlap_type(
                            external_start, external_end, block_start, block_end
                        )
                    }
        
        return None
    
    def resolve_conflict(self, conflict: Dict, resolution_type: str) -> Dict:
        """
        Apply a resolution strategy to a conflict
        resolution_type: 'merge_sum', 'merge_combine', 'keep_external', 'keep_internal'
        """
        external_event = conflict['external_event']
        internal_break = conflict['internal_break']
        
        if resolution_type == 'merge_sum':
            # Sum the duration of both events
            return self._merge_sum(external_event, internal_break)
        elif resolution_type == 'merge_combine':
            # Combine into one continuous block
            return self._merge_combine(external_event, internal_break)
        elif resolution_type == 'keep_external':
            # Replace internal with external
            return {
                'action': 'replace',
                'new_break': {
                    'start': external_event['start_time'],
                    'end': external_event['end_time'],
                    'type': internal_break.get('type', 'break'),
                    'external_event_id': external_event['id'],
                    'reason': f"Sincronizado: {external_event.get('summary', 'Evento externo')}"
                }
            }
        elif resolution_type == 'keep_internal':
            # Keep internal, ignore external
            return {
                'action': 'keep',
                'break': internal_break
            }
        else:
            raise ValueError(f"Unknown resolution type: {resolution_type}")
    
    def _merge_sum(self, external_event: Dict, internal_break: Dict) -> Dict:
        """Sum the duration of both events"""
        external_start = self._parse_time(external_event['start_time'])
        external_end = self._parse_time(external_event['end_time'])
        internal_start = self._parse_time(internal_break['start'])
        internal_end = self._parse_time(internal_break['end'])
        
        # Calculate total duration in minutes
        external_duration = self._time_diff_minutes(external_start, external_end)
        internal_duration = self._time_diff_minutes(internal_start, internal_end)
        total_duration = external_duration + internal_duration
        
        # Use the earlier start time
        new_start = min(external_start, internal_start)
        new_end = self._add_minutes_to_time(new_start, total_duration)
        
        return {
            'action': 'merge',
            'new_break': {
                'start': self._time_to_string(new_start),
                'end': self._time_to_string(new_end),
                'type': internal_break.get('type', 'break'),
                'external_event_id': external_event['id'],
                'reason': f"Fusionado (suma): {external_event.get('summary', '')} + descanso existente"
            }
        }
    
    def _merge_combine(self, external_event: Dict, internal_break: Dict) -> Dict:
        """Combine events into one continuous block from earliest start to latest end"""
        external_start = self._parse_time(external_event['start_time'])
        external_end = self._parse_time(external_event['end_time'])
        internal_start = self._parse_time(internal_break['start'])
        internal_end = self._parse_time(internal_break['end'])
        
        # Take earliest start and latest end
        new_start = min(external_start, internal_start)
        new_end = max(external_end, internal_end)
        
        return {
            'action': 'merge',
            'new_break': {
                'start': self._time_to_string(new_start),
                'end': self._time_to_string(new_end),
                'type': internal_break.get('type', 'break'),
                'external_event_id': external_event['id'],
                'reason': f"Combinado: {external_event.get('summary', '')} con descanso existente"
            }
        }
    
    def _times_overlap(self, start1: time, end1: time, start2: time, end2: time) -> bool:
        """Check if two time ranges overlap"""
        return start1 < end2 and end1 > start2
    
    def _get_overlap_type(self, start1: time, end1: time, start2: time, end2: time) -> str:
        """Determine the type of overlap between two time ranges"""
        if start1 <= start2 and end1 >= end2:
            return 'external_contains_internal'
        elif start2 <= start1 and end2 >= end1:
            return 'internal_contains_external'
        elif start1 < start2 < end1:
            return 'partial_overlap_start'
        else:
            return 'partial_overlap_end'
    
    def _parse_time(self, time_str: str) -> time:
        """Parse time string to time object"""
        if isinstance(time_str, time):
            return time_str
        
        # Remove microseconds if present
        if '.' in time_str:
            time_str = time_str.split('.')[0]
        
        # Handle different time formats
        for fmt in ['%H:%M:%S', '%H:%M', '%H:%M:%S.%f']:
            try:
                return datetime.strptime(time_str, fmt).time()
            except ValueError:
                continue
        
        raise ValueError(f"Cannot parse time: {time_str}")
    
    def _time_to_string(self, t: time) -> str:
        """Convert time object to string HH:MM"""
        return t.strftime('%H:%M')
    
    def _time_diff_minutes(self, start: time, end: time) -> int:
        """Calculate difference between two times in minutes"""
        start_dt = datetime.combine(date.today(), start)
        end_dt = datetime.combine(date.today(), end)
        return int((end_dt - start_dt).total_seconds() / 60)
    
    def _add_minutes_to_time(self, t: time, minutes: int) -> time:
        """Add minutes to a time object"""
        dt = datetime.combine(date.today(), t)
        dt += timedelta(minutes=minutes)
        return dt.time()
    
    def batch_resolve_conflicts(self, conflicts: List[Dict], resolutions: List[Dict]) -> List[Dict]:
        """
        Resolve multiple conflicts at once
        Returns list of resolved breaks
        """
        resolved = []
        
        for conflict, resolution in zip(conflicts, resolutions):
            result = self.resolve_conflict(conflict, resolution['resolution_type'])
            resolved.append(result)
        
        return resolved
    
    def merge_overlapping_breaks(self, breaks: List[Dict]) -> List[Dict]:
        """
        Merge overlapping breaks after conflict resolution
        """
        if not breaks:
            return []
        
        # Sort breaks by start time
        sorted_breaks = sorted(breaks, key=lambda x: self._parse_time(x['start']))
        merged = [sorted_breaks[0]]
        
        for current_break in sorted_breaks[1:]:
            last_merged = merged[-1]
            
            if self._parse_time(current_break['start']) <= self._parse_time(last_merged['end']):
                # Overlapping, merge them
                last_merged['end'] = self._time_to_string(
                    max(self._parse_time(last_merged['end']), 
                        self._parse_time(current_break['end']))
                )
                # Combine reasons if they have them
                if 'reason' in current_break:
                    last_merged['reason'] = last_merged.get('reason', '') + ' + ' + current_break['reason']
            else:
                # No overlap, add as new break
                merged.append(current_break)
        
        return merged