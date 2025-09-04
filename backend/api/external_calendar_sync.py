from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta
import uuid
import json
import traceback
from database.connection import get_db
from models.user import User
from models.horarios import HorarioTemplate, HorarioException
from models.calendar_sync import CalendarConnection, SyncedEvent
from api.auth import get_current_user
from services.google_calendar_service import GoogleCalendarService
from services.google_calendar_writer_service import GoogleCalendarWriterService
from services.apple_calendar_service import AppleCalendarService
from services.calendar_sync_service import CalendarSyncService
from google.auth.transport import requests as google_requests
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError
import os
from config import settings
from fastapi.responses import HTMLResponse
import requests
import logging
import asyncio
from typing import Set

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# Set OAuth environment variables
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' if settings.environment == 'development' else '0'

router = APIRouter()

# OAuth configuration
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'openid'
]

# Track auto-sync tasks
auto_sync_tasks: Dict[str, asyncio.Task] = {}

# Pydantic models
class CalendarConnectionResponse(BaseModel):
    connected: bool
    provider: Optional[str] = None
    email: Optional[str] = None
    calendar_email: Optional[str] = None  # Add this field
    settings: Dict = {}
    last_sync: Optional[datetime] = None

class SyncRequest(BaseModel):
    merge_calendars: bool = True  # Changed default to True
    receive_notifications: bool = False

class ConflictResolution(BaseModel):
    event_id: str
    resolution_type: str  # 'merge_sum', 'merge_combine', 'keep_external', 'keep_internal'
    group_id: Optional[str] = None  # For grouped resolutions
    merge_start: Optional[str] = None
    merge_end: Optional[str] = None

class RecurrentEventClassification(BaseModel):
    external_event_id: str
    classification: str  # 'administrative', 'lunch', 'break'

class SyncResponse(BaseModel):
    success: bool
    synced_events: int
    conflicts_found: List[Dict] = []
    recurrent_events: List[Dict] = []
    special_events: List[Dict] = []
    all_day_events: List[Dict] = []
    error: Optional[str] = None
    debug_info: Optional[Dict] = None
    synced_event_ids: List[str] = []  # Track synced event IDs

# Connection Status
@router.get("/status")
async def get_connection_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> CalendarConnectionResponse:
    """Get current calendar connection status"""
    try:
        logger.info(f"Getting connection status for user {current_user.id}")
        
        connection = db.query(CalendarConnection).filter(
            CalendarConnection.user_id == current_user.id,
            CalendarConnection.is_active == True
        ).first()
        
        if not connection:
            logger.info("No active connection found")
            return CalendarConnectionResponse(connected=False)
        
        logger.info(f"Found active connection: {connection.provider} - {connection.calendar_email}")
        
        # Ensure merge_calendars is True by default
        if not connection.sync_settings:
            connection.sync_settings = {'merge_calendars': True, 'receive_notifications': False}
        elif 'merge_calendars' not in connection.sync_settings:
            connection.sync_settings['merge_calendars'] = True
        
        return CalendarConnectionResponse(
            connected=True,
            provider=connection.provider,
            email=connection.calendar_email,
            calendar_email=connection.calendar_email,  # Include both fields
            settings=connection.sync_settings or {'merge_calendars': True},
            last_sync=connection.last_sync_at
        )
    except Exception as e:
        logger.error(f"Error getting connection status: {str(e)}")
        return CalendarConnectionResponse(connected=False)

# Google OAuth Flow
@router.get("/google/auth")
async def google_calendar_auth(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Initiate Google Calendar OAuth flow"""
    try:
        logger.info(f"Starting Google auth for user {current_user.id}")
        
        from google_auth_oauthlib.flow import Flow
        import base64
        import json
        
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=GOOGLE_SCOPES
        )
        
        flow.redirect_uri = settings.google_calendar_redirect_uri or "http://localhost:8000/api/calendar-sync/google/callback"
        
        # Create state with user_id embedded
        state_data = {
            'user_id': str(current_user.id),
            'random': str(uuid.uuid4())
        }
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()
        
        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='select_account',
            state=state
        )
        
        logger.info(f"Generated auth URL: {authorization_url}")
        
        return {
            "auth_url": authorization_url,
            "state": state
        }
    except Exception as e:
        logger.error(f"Error initiating Google auth: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error initiating Google auth: {str(e)}")

@router.get("/google/callback")
async def google_calendar_callback(
    code: str = Query(...),
    state: str = Query(...),
    scope: str = Query(None),
    authuser: str = Query(None),
    prompt: str = Query(None),
    db: Session = Depends(get_db)
):
    """Handle Google Calendar OAuth callback"""
    try:
        logger.info("Received Google callback")
        
        import base64
        import json
        
        # Decode state to get user_id
        try:
            state_data = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
            user_id = state_data.get('user_id')
            
            logger.info(f"Decoded user_id from state: {user_id}")
            
            if not user_id:
                raise Exception("User ID not found in state")
                
            from models.user import User
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise Exception(f"User not found: {user_id}")
                
        except Exception as e:
            logger.error(f"Error decoding state: {e}")
            user_id = None
        
        # Exchange code for token
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            'code': code,
            'client_id': settings.google_client_id,
            'client_secret': settings.google_client_secret,
            'redirect_uri': settings.google_calendar_redirect_uri or "http://localhost:8000/api/calendar-sync/google/callback",
            'grant_type': 'authorization_code'
        }
        
        logger.info("Exchanging code for token...")
        
        token_response = requests.post(token_url, data=token_data)
        
        if token_response.status_code != 200:
            logger.error(f"Token exchange failed: {token_response.text}")
            raise Exception(f"Token exchange failed: {token_response.text}")
        
        token_info = token_response.json()
        logger.info("Token exchange successful")
        
        # Create credentials object
        credentials = Credentials(
            token=token_info['access_token'],
            refresh_token=token_info.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=token_info.get('scope', '').split(' ') if token_info.get('scope') else None,
            expiry=datetime.utcnow() + timedelta(seconds=token_info.get('expires_in', 3599))
        )
        
        # Get user info
        google_service = GoogleCalendarService(credentials)
        user_info = google_service.get_user_info()
        
        logger.info(f"Got user info: {user_info['email']}")
        
        # If we couldn't get user_id from state, try to find by email
        if not user_id:
            from models.user import User
            user = db.query(User).filter(User.email == user_info['email']).first()
            if user:
                user_id = str(user.id)
            else:
                raise Exception(f"No user found with email: {user_info['email']}")
        
        # Track pre-existing events before first sync
        sync_service = CalendarSyncService(db)
        sync_service.track_pre_existing_events(user_id)
        
        # Find or create calendar connection
        existing = db.query(CalendarConnection).filter(
            CalendarConnection.user_id == user_id,
            CalendarConnection.provider == 'google'
        ).first()
        
        if existing:
            logger.info(f"Updating existing connection for user {user_id}")
            existing.calendar_email = user_info['email']
            existing.access_token = credentials.token
            existing.refresh_token = credentials.refresh_token or existing.refresh_token
            existing.token_expiry = credentials.expiry
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
            # Set merge_calendars to True by default
            if not existing.sync_settings:
                existing.sync_settings = {'merge_calendars': True, 'receive_notifications': False}
            else:
                existing.sync_settings['merge_calendars'] = True
            db.commit()
            connection_id = existing.id
        else:
            logger.info(f"Creating new connection for user {user_id}")
            connection = CalendarConnection(
                user_id=user_id,
                provider='google',
                calendar_email=user_info['email'],
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                token_expiry=credentials.expiry,
                sync_settings={
                    'merge_calendars': True,  # Default to True
                    'receive_notifications': False
                }
            )
            db.add(connection)
            db.commit()
            connection_id = connection.id
        
        logger.info("Calendar connection saved successfully")
        
        # Setup auto-sync task
        await setup_auto_sync(user_id, connection_id)
        
        # Redirect to success page
        success_url = f"/calendar-sync-success?provider=google&email={user_info['email']}&syncing=true"
        
        html_content = f"""
        <html>
            <head>
                <title>Conexión Exitosa</title>
            </head>
            <body>
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{
                            type: 'calendar-connected',
                            success: true,
                            provider: 'google',
                            email: '{user_info['email']}'
                        }}, '*');
                        window.close();
                    }} else {{
                        window.location.href = '{success_url}';
                    }}
                </script>
                <p>Conexión exitosa. Redirigiendo...</p>
            </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error in Google Calendar callback: {str(e)}")
        logger.error(f"Full error details: {repr(e)}")
        logger.error(traceback.format_exc())
        
        error_html = f"""
        <html>
            <head>
                <title>Error de Conexión</title>
            </head>
            <body>
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{
                            type: 'calendar-error',
                            success: false,
                            error: '{str(e).replace("'", "")}'
                        }}, '*');
                        setTimeout(() => window.close(), 3000);
                    }} else {{
                        setTimeout(() => {{
                            window.location.href = '/configurar-horario';
                        }}, 3000);
                    }}
                </script>
                <p>Error al conectar calendario: {str(e)}</p>
                <p>Redirigiendo...</p>
            </body>
        </html>
        """
        
        return HTMLResponse(content=error_html, status_code=400)

# Disconnect calendar
@router.delete("/disconnect")
async def disconnect_calendar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect calendar and clean up synced events"""
    try:
        logger.info(f"Disconnecting calendar for user {current_user.id}")
        
        connection = db.query(CalendarConnection).filter(
            CalendarConnection.user_id == current_user.id,
            CalendarConnection.is_active == True
        ).first()
        
        if not connection:
            raise HTTPException(status_code=404, detail="No active calendar connection found")
        
        sync_service = CalendarSyncService(db)
        
        # Stop auto-sync task
        await stop_auto_sync(str(current_user.id))
        
        # If Google Calendar and merge was enabled, remove pre-existing events from Google
        if connection.provider == 'google' and connection.sync_settings.get('merge_calendars'):
            try:
                # Refresh token if needed
                credentials = Credentials(
                    token=connection.access_token,
                    refresh_token=connection.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=settings.google_client_id,
                    client_secret=settings.google_client_secret,
                    expiry=connection.token_expiry
                )
                
                if connection.token_expiry and connection.token_expiry < datetime.utcnow():
                    request_obj = google_requests.Request()
                    credentials.refresh(request_obj)
                
                writer_service = GoogleCalendarWriterService(credentials)
                
                # Get all events synced from internal to external (pre-existing events)
                synced_events = db.query(SyncedEvent).filter(
                    SyncedEvent.user_id == current_user.id,
                    SyncedEvent.connection_id == connection.id,
                    SyncedEvent.sync_direction == 'internal_to_external'
                ).all()
                
                # Delete them from Google Calendar
                for event in synced_events:
                    try:
                        writer_service.delete_event(event.external_event_id)
                    except:
                        pass  # Ignore individual deletion errors
                
            except Exception as e:
                logger.warning(f"Could not cleanup Google Calendar events: {str(e)}")
        
        # Remove all synced events from database
        removed_count = sync_service.cleanup_synced_events(current_user.id, connection.id)
        
        logger.info(f"Removed {removed_count} synced events")
        
        # Deactivate connection
        connection.is_active = False
        connection.updated_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "success": True,
            "message": "Calendar disconnected successfully",
            "events_removed": removed_count
        }
    except Exception as e:
        logger.error(f"Error disconnecting calendar: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error disconnecting calendar: {str(e)}")

# Sync calendars - Enhanced with grouping and auto-sync
@router.post("/sync")
async def sync_calendars(
    request: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict:
    """Perform calendar synchronization with improved grouping and conflict detection"""
    try:
        logger.info(f"Starting sync for user {current_user.id}")
        logger.info(f"Sync settings: merge={request.merge_calendars}, notifications={request.receive_notifications}")
        
        connection = db.query(CalendarConnection).filter(
            CalendarConnection.user_id == current_user.id,
            CalendarConnection.is_active == True
        ).first()
        
        if not connection:
            logger.warning("No active calendar connection found")
            return {
                "success": False,
                "synced_events": 0,
                "error": "No active calendar connection found"
            }
        
        logger.info(f"Found connection: {connection.provider} - {connection.calendar_email}")
        
        # Update sync settings (ensure merge_calendars stays True if it was True)
        if connection.sync_settings and connection.sync_settings.get('merge_calendars'):
            request.merge_calendars = True
        
        connection.sync_settings = {
            'merge_calendars': request.merge_calendars,
            'receive_notifications': request.receive_notifications
        }
        
        # Initialize appropriate service
        if connection.provider == 'google':
            try:
                logger.info("Initializing Google Calendar service...")
                
                # Check if token needs refresh
                if connection.token_expiry and connection.token_expiry < datetime.utcnow():
                    logger.info("Token expired, refreshing...")
                    credentials = Credentials(
                        token=None,
                        refresh_token=connection.refresh_token,
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=settings.google_client_id,
                        client_secret=settings.google_client_secret
                    )
                    
                    request_obj = google_requests.Request()
                    credentials.refresh(request_obj)
                    
                    connection.access_token = credentials.token
                    connection.token_expiry = credentials.expiry
                    db.commit()
                    
                    logger.info("Token refreshed successfully")
                else:
                    credentials = Credentials(
                        token=connection.access_token,
                        refresh_token=connection.refresh_token,
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=settings.google_client_id,
                        client_secret=settings.google_client_secret,
                        expiry=connection.token_expiry
                    )
                
                calendar_service = GoogleCalendarService(credentials)
                writer_service = GoogleCalendarWriterService(credentials) if request.merge_calendars else None
                logger.info("Google Calendar services initialized")
                
            except Exception as e:
                logger.error(f"Error initializing Google Calendar service: {str(e)}")
                logger.error(traceback.format_exc())
                return {
                    "success": False,
                    "synced_events": 0,
                    "error": f"Error connecting to Google Calendar: {str(e)}"
                }
        else:
            # Apple calendar service
            try:
                calendar_service = AppleCalendarService(connection.access_token)
                writer_service = None
            except Exception as e:
                logger.error(f"Error initializing Apple Calendar service: {str(e)}")
                return {
                    "success": False,
                    "synced_events": 0,
                    "error": f"Error connecting to Apple Calendar: {str(e)}"
                }
        
        sync_service = CalendarSyncService(db)
        
        try:
            logger.info("Step 1: Fetching events from external calendar...")
            
            # Fetch events from external calendar (now with grouping)
            external_events = calendar_service.get_all_events()
            
            # Count raw events
            raw_event_count = (
                len(external_events.get('recurrent', [])) +
                len(external_events.get('special', [])) +
                len(external_events.get('all_day', []))
            )
            
            # Count grouped recurring events
            grouped_count = len(external_events.get('grouped_recurring', {}))
            
            logger.info(f"Retrieved events - Recurrent: {len(external_events.get('recurrent', []))}, "
                       f"Special: {len(external_events.get('special', []))}, "
                       f"All-day: {len(external_events.get('all_day', []))}, "
                       f"Grouped recurring: {grouped_count}")
            
            # Process events with grouping and improved conflict detection
            logger.info("Step 2: Processing external events with grouping...")
            result = sync_service.process_external_events(
                user_id=current_user.id,
                connection_id=connection.id,
                external_events=external_events,
                provider=connection.provider
            )
            
            # Step 3: BIDIRECTIONAL SYNC - Write MediConnect events to Google Calendar
            write_stats = {'events_written': 0}
            if request.merge_calendars and writer_service:
                logger.info("Step 3: Writing MediConnect events to Google Calendar...")
                
                # Clean up old synced events first
                synced_to_delete = db.query(SyncedEvent).filter(
                    SyncedEvent.user_id == current_user.id,
                    SyncedEvent.connection_id == connection.id,
                    SyncedEvent.sync_direction == 'internal_to_external'
                ).all()
                
                for event in synced_to_delete:
                    try:
                        writer_service.delete_event(event.external_event_id)
                        db.delete(event)
                    except:
                        pass
                
                # Get all templates and sync breaks
                templates = db.query(HorarioTemplate).filter(
                    HorarioTemplate.user_id == current_user.id,
                    HorarioTemplate.is_active == True
                ).all()
                
                for template in templates:
                    if template.time_blocks:
                        for block in template.time_blocks:
                            # Only sync internal breaks (not from external calendar)
                            if block.get('type') != 'consultation' and not block.get('external_event_id'):
                                try:
                                    event_id = writer_service.sync_break_to_calendar(
                                        break_info=block,
                                        date_info={
                                            'is_recurring': True,
                                            'day_of_week': template.day_of_week
                                        }
                                    )
                                    
                                    if event_id:
                                        synced = SyncedEvent(
                                            user_id=current_user.id,
                                            connection_id=connection.id,
                                            external_event_id=event_id,
                                            local_event_id=template.id,
                                            local_event_type='template',
                                            sync_direction='internal_to_external',
                                            sync_status='completed',
                                            event_title=f"Descanso - {block.get('type', 'break')}",
                                            event_metadata={'break_type': block.get('type')}
                                        )
                                        db.add(synced)
                                        write_stats['events_written'] += 1
                                        
                                except Exception as e:
                                    logger.error(f"Error syncing break to calendar: {str(e)}")
                
                # Sync exceptions
                exceptions = db.query(HorarioException).filter(
                    HorarioException.user_id == current_user.id,
                    HorarioException.date >= date.today()
                ).all()
                
                for exception in exceptions:
                    # Skip if already synced from external
                    if exception.sync_source and exception.sync_source != 'manual':
                        continue
                    
                    try:
                        if not exception.is_working_day:
                            event_id = writer_service.sync_closed_day_to_calendar(
                                date_str=exception.date.isoformat(),
                                reason=exception.reason
                            )
                        elif exception.is_special_open or (exception.opens_at != template.opens_at):
                            event_id = writer_service.sync_special_hours_to_calendar(
                                date_str=exception.date.isoformat(),
                                opens_at=exception.opens_at.strftime("%H:%M"),
                                closes_at=exception.closes_at.strftime("%H:%M")
                            )
                            
                            if exception.time_blocks:
                                for block in exception.time_blocks:
                                    if block.get('type') != 'consultation':
                                        writer_service.sync_break_to_calendar(
                                            break_info=block,
                                            date_info={
                                                'is_recurring': False,
                                                'date': exception.date.isoformat()
                                            }
                                        )
                        else:
                            event_id = None
                        
                        if event_id:
                            synced = SyncedEvent(
                                user_id=current_user.id,
                                connection_id=connection.id,
                                external_event_id=event_id,
                                local_event_id=exception.id,
                                local_event_type='exception',
                                sync_direction='internal_to_external',
                                sync_status='completed',
                                event_date=exception.date,
                                event_metadata={'exception_type': 'closed' if not exception.is_working_day else 'special'}
                            )
                            db.add(synced)
                            write_stats['events_written'] += 1
                            
                    except Exception as e:
                        logger.error(f"Error syncing exception to calendar: {str(e)}")
                
                db.commit()
                logger.info(f"Wrote {write_stats['events_written']} events to external calendar")
            
            # Add debug info
            debug_info = result.get('debug_info', {})
            if not debug_info:
                debug_info = {
                    'total_raw_events': raw_event_count,
                    'filtered_events': (
                        len(result.get('recurrent', [])) +
                        len(result.get('special', [])) +
                        len(result.get('all_day', []))
                    ),
                    'has_any_events': raw_event_count > 0,
                    'events_written_to_external': write_stats['events_written'],
                    'grouped_recurring_count': grouped_count
                }
            else:
                debug_info['events_written_to_external'] = write_stats['events_written']
                debug_info['grouped_recurring_count'] = grouped_count
            
            logger.info(f"Processing result - Synced: {len(result.get('synced', []))}, "
                       f"Conflicts: {len(result.get('conflicts', []))}, "
                       f"Recurrent: {len(result.get('recurrent', []))}, "
                       f"Special: {len(result.get('special', []))}, "
                       f"All-day: {len(result.get('all_day', []))}, "
                       f"Written to external: {write_stats['events_written']}")
            
            # Update last sync time
            connection.last_sync_at = datetime.utcnow()
            connection.last_sync_status = 'success'
            connection.last_sync_error = None
            connection.sync_count = (connection.sync_count or 0) + 1
            db.commit()
            
            logger.info("Sync completed successfully")
            
            # Create response
            response_dict = {
                "success": True,
                "synced_events": len(result.get('synced', [])) + write_stats['events_written'],
                "conflicts_found": result.get('conflicts', []),
                "recurrent_events": result.get('recurrent', []),
                "special_events": result.get('special', []),
                "all_day_events": result.get('all_day', []),
                "synced_event_ids": result.get('synced_event_ids', []),
                "debug_info": debug_info
            }
            
            return response_dict
            
        except Exception as e:
            logger.error(f"Error during sync process: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            connection.last_sync_at = datetime.utcnow()
            connection.last_sync_status = 'failed'
            connection.last_sync_error = str(e)
            db.commit()
            
            return {
                "success": False,
                "synced_events": 0,
                "error": f"Error during synchronization: {str(e)}"
            }
            
    except Exception as e:
        logger.error(f"Unexpected error in sync_calendars: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return {
            "success": False,
            "synced_events": 0,
            "error": f"Unexpected error: {str(e)}"
        }

# Resolve conflicts with grouping support
@router.post("/resolve-conflicts")
async def resolve_conflicts(
    resolutions: List[ConflictResolution],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Resolve detected conflicts between calendars with group support"""
    try:
        logger.info(f"Resolving {len(resolutions)} conflicts for user {current_user.id}")
        
        sync_service = CalendarSyncService(db)
        
        # Group resolutions by group_id
        grouped_resolutions = {}
        individual_resolutions = []
        
        for resolution in resolutions:
            if resolution.group_id:
                if resolution.group_id not in grouped_resolutions:
                    grouped_resolutions[resolution.group_id] = []
                grouped_resolutions[resolution.group_id].append(resolution)
            else:
                individual_resolutions.append(resolution)
        
        results = []
        
        # Process grouped resolutions
        for group_id, group_resolutions in grouped_resolutions.items():
            # Apply the same resolution to all events in the group
            for res in group_resolutions:
                result = sync_service.resolve_conflict(
                    user_id=current_user.id,
                    event_id=res.event_id,
                    resolution_type=res.resolution_type,
                    merge_start=res.merge_start,
                    merge_end=res.merge_end
                )
                results.append(result)
        
        # Process individual resolutions
        for resolution in individual_resolutions:
            result = sync_service.resolve_conflict(
                user_id=current_user.id,
                event_id=resolution.event_id,
                resolution_type=resolution.resolution_type,
                merge_start=resolution.merge_start,
                merge_end=resolution.merge_end
            )
            results.append(result)
        
        db.commit()
        
        logger.info(f"Resolved {len(results)} conflicts")
        
        return {
            "success": True,
            "resolved": len(results),
            "results": results
        }
    except Exception as e:
        logger.error(f"Error resolving conflicts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error resolving conflicts: {str(e)}")

# Classify recurrent events
@router.post("/classify-recurrent")
async def classify_recurrent_events(
    classifications: List[RecurrentEventClassification],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Classify recurrent events from external calendar"""
    try:
        logger.info(f"Classifying {len(classifications)} recurrent events for user {current_user.id}")
        
        sync_service = CalendarSyncService(db)
        
        for classification in classifications:
            sync_service.classify_recurrent_event(
                user_id=current_user.id,
                external_event_id=classification.external_event_id,
                classification=classification.classification
            )
        
        db.commit()
        
        logger.info(f"Classified {len(classifications)} events")
        
        return {
            "success": True,
            "classified": len(classifications)
        }
    except Exception as e:
        logger.error(f"Error classifying events: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error classifying events: {str(e)}")

# Manual sync trigger
@router.post("/sync-now")
async def sync_now(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Trigger immediate synchronization"""
    try:
        logger.info(f"Manual sync triggered for user {current_user.id}")
        
        connection = db.query(CalendarConnection).filter(
            CalendarConnection.user_id == current_user.id,
            CalendarConnection.is_active == True
        ).first()
        
        if not connection:
            raise HTTPException(status_code=404, detail="No active calendar connection found")
        
        # Ensure merge_calendars is True if it was True
        merge_calendars = connection.sync_settings.get('merge_calendars', True)
        
        sync_request = SyncRequest(
            merge_calendars=merge_calendars,
            receive_notifications=connection.sync_settings.get('receive_notifications', False)
        )
        
        return await sync_calendars(sync_request, current_user, db)
    except Exception as e:
        logger.error(f"Error in sync-now: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error triggering sync: {str(e)}")

# Update sync settings
@router.put("/settings")
async def update_sync_settings(
    settings_update: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update synchronization settings"""
    try:
        logger.info(f"Updating sync settings for user {current_user.id}: {settings_update}")
        
        connection = db.query(CalendarConnection).filter(
            CalendarConnection.user_id == current_user.id,
            CalendarConnection.is_active == True
        ).first()
        
        if not connection:
            raise HTTPException(status_code=404, detail="No active calendar connection found")
        
        # Ensure merge_calendars stays True if it was True
        if connection.sync_settings and connection.sync_settings.get('merge_calendars'):
            settings_update['merge_calendars'] = True
        
        connection.sync_settings = settings_update
        connection.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info("Settings updated successfully")
        
        return {"success": True, "settings": settings_update}
    except Exception as e:
        logger.error(f"Error updating settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating settings: {str(e)}")

# Auto-sync setup functions
async def setup_auto_sync(user_id: str, connection_id: str):
    """Setup automatic synchronization task"""
    try:
        # Cancel existing task if any
        await stop_auto_sync(user_id)
        
        # Create new auto-sync task
        task = asyncio.create_task(auto_sync_task(user_id, connection_id))
        auto_sync_tasks[user_id] = task
        
        logger.info(f"Auto-sync task created for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error setting up auto-sync: {str(e)}")

async def stop_auto_sync(user_id: str):
    """Stop automatic synchronization task"""
    if user_id in auto_sync_tasks:
        task = auto_sync_tasks[user_id]
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        del auto_sync_tasks[user_id]
        logger.info(f"Auto-sync task stopped for user {user_id}")

async def auto_sync_task(user_id: str, connection_id: str):
    """Background task for automatic synchronization"""
    while True:
        try:
            # Wait 5 minutes
            await asyncio.sleep(300)
            
            # Perform sync
            logger.info(f"Auto-sync triggered for user {user_id}")
            
            # Get database session
            db = next(get_db())
            
            try:
                connection = db.query(CalendarConnection).filter(
                    CalendarConnection.id == connection_id,
                    CalendarConnection.is_active == True
                ).first()
                
                if connection:
                    # Create sync request
                    sync_request = SyncRequest(
                        merge_calendars=connection.sync_settings.get('merge_calendars', True),
                        receive_notifications=connection.sync_settings.get('receive_notifications', False)
                    )
                    
                    # Get user
                    from models.user import User
                    user = db.query(User).filter(User.id == user_id).first()
                    
                    if user:
                        # Perform sync
                        await sync_calendars(sync_request, user, db)
                        logger.info(f"Auto-sync completed for user {user_id}")
                
            finally:
                db.close()
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in auto-sync task for user {user_id}: {str(e)}")
            await asyncio.sleep(60)  # Wait a minute before retrying

# Get sync history
@router.get("/sync-history")
async def get_sync_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get synchronization history"""
    try:
        synced_events = db.query(SyncedEvent).filter(
            SyncedEvent.user_id == current_user.id
        ).order_by(SyncedEvent.created_at.desc()).limit(50).all()
        
        return {
            "events": [
                {
                    "id": str(event.id),
                    "type": event.sync_type,
                    "direction": event.sync_direction,
                    "external_id": event.external_event_id,
                    "local_id": str(event.local_event_id),
                    "status": event.sync_status,
                    "created_at": event.created_at.isoformat()
                }
                for event in synced_events
            ]
        }
    except Exception as e:
        logger.error(f"Error getting sync history: {str(e)}")
        return {"events": []}