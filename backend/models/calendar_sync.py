from sqlalchemy import Column, String, DateTime, Boolean, JSON, ForeignKey, Text, Integer, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from database.connection import Base


class CalendarConnection(Base):
    """Calendar connection configuration for external calendar sync"""
    __tablename__ = "calendar_connections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Provider information
    provider = Column(String(50), nullable=False)  # 'google' or 'apple'
    calendar_email = Column(String(255), nullable=False)
    calendar_name = Column(String(255), nullable=True)
    
    # Authentication tokens
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_expiry = Column(DateTime, nullable=True)
    
    # Additional OAuth data
    oauth_state = Column(String(255), nullable=True)
    scope = Column(Text, nullable=True)
    
    # Sync configuration - Default merge_calendars to True
    sync_settings = Column(JSON, default={
        'merge_calendars': True,  # Changed to True by default
        'receive_notifications': False,
        'sync_interval_minutes': 30,
        'auto_sync': True
    })
    
    # Calendar preferences
    primary_calendar_id = Column(String(255), nullable=True)  # For selecting specific calendar
    calendars_list = Column(JSON, nullable=True)  # Cache available calendars
    
    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Sync tracking
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)  # 'success', 'failed', 'partial'
    last_sync_error = Column(Text, nullable=True)
    sync_count = Column(Integer, default=0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="calendar_connections")
    synced_events = relationship("SyncedEvent", backref="connection", cascade="all, delete-orphan")


class SyncedEvent(Base):
    """Track synced events between external calendars and MediConnect"""
    __tablename__ = "synced_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("calendar_connections.id"), nullable=False)
    
    # External event reference
    external_event_id = Column(String(255), nullable=False)
    external_calendar_id = Column(String(255), nullable=True)  # Which calendar in the account
    
    # Local event reference
    local_event_id = Column(UUID(as_uuid=True), nullable=False)
    local_event_type = Column(String(50), nullable=False)  # 'template', 'exception', 'vacation'
    
    # Sync information
    sync_direction = Column(String(50), nullable=False)  # 'external_to_internal', 'internal_to_external', 'bidirectional'
    sync_status = Column(String(50), default='pending')  # 'pending', 'completed', 'failed', 'conflict'
    sync_type = Column(String(50), nullable=True)  # 'recurrent', 'special', 'all_day', 'vacation'
    
    # NEW FIELDS for enhanced sync
    existed_before_sync = Column(Boolean, default=False)  # Track if event existed before sync was enabled
    recurring_group_id = Column(String(255), nullable=True)  # Group ID for recurring events
    is_master_event = Column(Boolean, default=False)  # Marks the master event in a recurring series
    
    # Event details cache
    event_title = Column(String(255), nullable=True)
    event_description = Column(Text, nullable=True)
    event_start = Column(DateTime, nullable=True)
    event_end = Column(DateTime, nullable=True)
    event_date = Column(Date, nullable=True)  # Specific date for the event
    is_all_day = Column(Boolean, default=False)
    
    # Conflict resolution
    conflict_resolution = Column(String(50), nullable=True)  # 'merge_sum', 'merge_combine', 'keep_external', 'keep_internal'
    conflict_resolved_at = Column(DateTime, nullable=True)
    conflict_resolved_by = Column(UUID(as_uuid=True), nullable=True)
    
    # Classification for recurrent events
    classification = Column(String(50), nullable=True)  # 'lunch', 'break', 'administrative'
    
    # Metadata
    event_metadata = Column(JSON, default={})
    original_data = Column(JSON, nullable=True)  # Store original event data for reference
    
    # Tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime, nullable=True)
    sync_attempts = Column(Integer, default=0)
    
    # Relationships
    user = relationship("User", backref="synced_events")


class CalendarSyncLog(Base):
    """Log of all sync operations for debugging and history"""
    __tablename__ = "calendar_sync_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("calendar_connections.id"), nullable=True)
    
    # Operation details
    operation = Column(String(100), nullable=False)  # 'sync', 'connect', 'disconnect', 'resolve_conflict', etc.
    status = Column(String(50), nullable=False)  # 'started', 'completed', 'failed'
    
    # Statistics
    events_processed = Column(Integer, default=0)
    events_created = Column(Integer, default=0)
    events_updated = Column(Integer, default=0)
    events_deleted = Column(Integer, default=0)
    conflicts_found = Column(Integer, default=0)
    conflicts_resolved = Column(Integer, default=0)
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    
    # Performance
    duration_seconds = Column(Integer, nullable=True)
    
    # Metadata
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="sync_logs")
    connection = relationship("CalendarConnection", backref="sync_logs")


class CalendarWebhook(Base):
    """Store webhook configurations for real-time sync"""
    __tablename__ = "calendar_webhooks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("calendar_connections.id"), nullable=False)
    
    # Webhook details
    webhook_id = Column(String(255), nullable=False)  # External webhook ID
    webhook_url = Column(Text, nullable=False)
    webhook_token = Column(String(255), nullable=True)
    
    # Configuration
    resource_type = Column(String(50), nullable=False)  # 'calendar', 'events'
    resource_id = Column(String(255), nullable=False)  # Calendar ID being watched
    
    # Status
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    connection = relationship("CalendarConnection", backref="webhooks")