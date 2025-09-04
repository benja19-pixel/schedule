from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, validator
from typing import Optional
from datetime import datetime, timedelta
from database.connection import get_db
from models.user import User
from utils.security import (
    hash_password, verify_password, create_access_token, 
    decode_access_token, generate_device_fingerprint, check_suspicious_activity,
    generate_verification_code, validate_verification_code
)
from services.stripe_service import StripeService
from services.email_service import EmailService
from services.sms_service import SMSService
from services.google_oauth import GoogleOAuthService
from config import settings
import uuid
import redis
import json
import logging
import secrets

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)

# Initialize Redis for temporary storage
try:
    redis_client = redis.from_url("redis://localhost:6379", decode_responses=True)
    redis_client.ping()
    logger.info("Redis connected for verification codes")
except:
    redis_client = None
    logger.warning("Redis not available, using in-memory storage")
    temp_storage = {}

# Pydantic models
class UserPreRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    phone_number: str
    
    @validator('phone_number')
    def validate_phone(cls, v):
        # Remove spaces and dashes
        cleaned = v.replace(' ', '').replace('-', '')
        # Basic validation - must start with + and have 10-15 digits
        if not cleaned.startswith('+'):
            raise ValueError('El número debe incluir código de país (ej: +52 para México)')
        if len(cleaned) < 11 or len(cleaned) > 16:
            raise ValueError('Número de teléfono inválido')
        if not cleaned[1:].isdigit():
            raise ValueError('El número solo debe contener dígitos después del +')
        return cleaned

class GoogleAuthRequest(BaseModel):
    id_token: str

class GooglePhoneVerifyRequest(BaseModel):
    session_id: str
    phone_number: str
    
    @validator('phone_number')
    def validate_phone(cls, v):
        cleaned = v.replace(' ', '').replace('-', '')
        if not cleaned.startswith('+'):
            raise ValueError('El número debe incluir código de país (ej: +52 para México)')
        if len(cleaned) < 11 or len(cleaned) > 16:
            raise ValueError('Número de teléfono inválido')
        if not cleaned[1:].isdigit():
            raise ValueError('El número solo debe contener dígitos después del +')
        return cleaned

class GoogleVerifyCodeRequest(BaseModel):
    session_id: str
    sms_code: str

class LinkGoogleRequest(BaseModel):
    id_token: str

class VerifyCodesRequest(BaseModel):
    email: EmailStr
    email_code: str
    sms_code: str

class ResendCodeRequest(BaseModel):
    email: EmailStr
    code_type: str  # 'email' or 'sms'

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

# Helper functions for temporary storage
def store_temp_registration(email: str, data: dict, expiry_minutes: int = 15):
    """Store registration data temporarily"""
    key = f"reg:{email}"
    data['timestamp'] = datetime.utcnow().isoformat()
    
    if redis_client:
        redis_client.setex(key, expiry_minutes * 60, json.dumps(data))
    else:
        # Fallback to in-memory
        temp_storage[key] = {
            'data': data,
            'expires_at': datetime.utcnow() + timedelta(minutes=expiry_minutes)
        }

def get_temp_registration(email: str):
    """Get temporary registration data"""
    key = f"reg:{email}"
    
    if redis_client:
        data = redis_client.get(key)
        return json.loads(data) if data else None
    else:
        # Fallback to in-memory
        if key in temp_storage:
            if datetime.utcnow() < temp_storage[key]['expires_at']:
                return temp_storage[key]['data']
            else:
                # Expired
                del temp_storage[key]
        return None

def delete_temp_registration(email: str):
    """Delete temporary registration data"""
    key = f"reg:{email}"
    
    if redis_client:
        redis_client.delete(key)
    else:
        if key in temp_storage:
            del temp_storage[key]

# Google OAuth temporary storage
def store_google_temp_data(session_id: str, data: dict, expiry_minutes: int = 15):
    """Store Google OAuth data temporarily"""
    key = f"google:{session_id}"
    data['timestamp'] = datetime.utcnow().isoformat()
    
    if redis_client:
        redis_client.setex(key, expiry_minutes * 60, json.dumps(data))
    else:
        temp_storage[key] = {
            'data': data,
            'expires_at': datetime.utcnow() + timedelta(minutes=expiry_minutes)
        }

def get_google_temp_data(session_id: str):
    """Get Google OAuth temporary data"""
    key = f"google:{session_id}"
    
    if redis_client:
        data = redis_client.get(key)
        return json.loads(data) if data else None
    else:
        if key in temp_storage:
            if datetime.utcnow() < temp_storage[key]['expires_at']:
                return temp_storage[key]['data']
            else:
                del temp_storage[key]
        return None

def delete_google_temp_data(session_id: str):
    """Delete Google OAuth temporary data"""
    key = f"google:{session_id}"
    
    if redis_client:
        redis_client.delete(key)
    else:
        if key in temp_storage:
            del temp_storage[key]

# Helper function to get current user
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), 
                          db: Session = Depends(get_db)) -> User:
    token = credentials.credentials
    payload = decode_access_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user

# Google OAuth endpoints with enhanced logging
@router.get("/google/login")
async def google_login():
    """Initiate Google OAuth flow"""
    # DEBUGGING LOGS
    logger.info("="*50)
    logger.info("GOOGLE LOGIN ENDPOINT HIT")
    logger.info(f"Google Client ID: {settings.google_client_id}")
    logger.info(f"Google Client Secret present: {bool(settings.google_client_secret)}")
    logger.info(f"Google Redirect URI: {settings.google_redirect_uri}")
    logger.info(f"Feature enabled: {settings.FEATURE_GOOGLE_AUTH}")
    logger.info("="*50)
    
    if not settings.FEATURE_GOOGLE_AUTH:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google authentication is not enabled"
        )
    
    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    logger.info(f"Generated state: {state}")
    
    # Get authorization URL
    try:
        auth_url, _ = GoogleOAuthService.get_authorization_url(state)
        logger.info(f"Generated auth URL: {auth_url}")
        
        # Verify URL contains client_id
        if 'client_id=' not in auth_url:
            logger.error("AUTH URL MISSING CLIENT_ID!")
            logger.error(f"URL: {auth_url}")
        else:
            # Extract client_id from URL for debugging
            import urllib.parse
            parsed = urllib.parse.urlparse(auth_url)
            query_params = urllib.parse.parse_qs(parsed.query)
            logger.info(f"Client ID in URL: {query_params.get('client_id', ['NOT FOUND'])[0]}")
            
        return {"auth_url": auth_url}
        
    except Exception as e:
        logger.error(f"Error generating auth URL: {str(e)}")
        logger.exception("Full traceback:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating Google auth URL: {str(e)}"
        )

@router.get("/google/callback")
async def google_callback(code: str, state: str, db: Session = Depends(get_db)):
    """Handle Google OAuth callback"""
    logger.info("="*50)
    logger.info("GOOGLE CALLBACK HIT")
    logger.info(f"Code received: {code[:20]}...")
    logger.info(f"State received: {state}")
    logger.info("="*50)
    
    try:
        # Exchange code for user info
        google_user = GoogleOAuthService.exchange_code_for_token(code, state)
        logger.info(f"Google user received: {google_user.get('email')}")
        
        # Check if user exists
        existing_user = db.query(User).filter(User.email == google_user['email']).first()
        
        if existing_user:
            logger.info(f"Existing user found: {existing_user.email}")
            # User exists - check if Google is linked
            if not existing_user.google_id:
                # Link Google account
                existing_user.google_id = google_user['google_id']
                existing_user.profile_picture = google_user.get('picture')
                if existing_user.auth_method == "password":
                    existing_user.auth_method = "both"
                db.commit()
                logger.info("Linked Google account to existing user")
            
            # Create token and redirect to dashboard
            access_token = create_access_token(data={"sub": str(existing_user.id)})
            
            # Create redirect HTML
            redirect_url = f"{settings.frontend_url}/dashboard?google_auth=success&token={access_token}"
            html_content = GoogleOAuthService.create_redirect_html(redirect_url)
            
            logger.info(f"Redirecting to: {redirect_url}")
            return HTMLResponse(content=html_content)
        else:
            logger.info("New user - need phone verification")
            # New user - need phone verification
            session_id = secrets.token_urlsafe(32)
            
            # Store Google data temporarily
            store_google_temp_data(session_id, {
                'google_id': google_user['google_id'],
                'email': google_user['email'],
                'full_name': google_user.get('name', ''),
                'profile_picture': google_user.get('picture'),
                'email_verified': True  # Google already verified the email
            })
            
            # Redirect to phone verification
            redirect_url = f"{settings.frontend_url}/login?google_phone_verify=true&session_id={session_id}"
            html_content = GoogleOAuthService.create_redirect_html(redirect_url)
            
            logger.info(f"Redirecting to phone verification: {redirect_url}")
            return HTMLResponse(content=html_content)
            
    except Exception as e:
        logger.error(f"Google OAuth callback error: {str(e)}")
        logger.exception("Full traceback:")
        # Redirect to login with error
        redirect_url = f"{settings.frontend_url}/login?google_error=true"
        html_content = GoogleOAuthService.create_redirect_html(redirect_url)
        return HTMLResponse(content=html_content)

@router.post("/google/auth")
async def google_auth(request: GoogleAuthRequest, db: Session = Depends(get_db)):
    """Authenticate with Google ID token (for JS SDK)"""
    logger.info("Google auth endpoint hit (JS SDK)")
    
    try:
        # Verify the ID token
        google_user = GoogleOAuthService.verify_id_token(request.id_token)
        
        # Check if user exists
        existing_user = db.query(User).filter(User.email == google_user['email']).first()
        
        if existing_user:
            # User exists - check if Google is linked
            if not existing_user.google_id:
                # Link Google account
                existing_user.google_id = google_user['google_id']
                existing_user.profile_picture = google_user.get('picture')
                if existing_user.auth_method == "password":
                    existing_user.auth_method = "both"
                db.commit()
            
            # Update last login
            existing_user.last_login = datetime.utcnow()
            db.commit()
            
            # Create token
            access_token = create_access_token(data={"sub": str(existing_user.id)})
            
            return TokenResponse(
                access_token=access_token,
                user={
                    "id": str(existing_user.id),
                    "email": existing_user.email,
                    "full_name": existing_user.full_name,
                    "plan_type": existing_user.plan_type,
                    "is_verified": existing_user.is_verified,
                    "auth_method": existing_user.auth_method
                }
            )
        else:
            # New user - need phone verification
            session_id = secrets.token_urlsafe(32)
            
            # Store Google data temporarily
            store_google_temp_data(session_id, {
                'google_id': google_user['google_id'],
                'email': google_user['email'],
                'full_name': google_user.get('name', ''),
                'profile_picture': google_user.get('picture'),
                'email_verified': True
            })
            
            return {
                "requires_phone_verification": True,
                "session_id": session_id,
                "email": google_user['email'],
                "full_name": google_user.get('name', '')
            }
            
    except Exception as e:
        logger.error(f"Google auth error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.post("/google/verify-phone")
async def google_verify_phone(request: GooglePhoneVerifyRequest, db: Session = Depends(get_db)):
    """Send SMS verification for Google signup"""
    
    # Get Google data from session
    google_data = get_google_temp_data(request.session_id)
    if not google_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sesión expirada. Por favor inicia el proceso nuevamente."
        )
    
    # Check if phone already exists
    existing_phone = db.query(User).filter(User.phone_number == request.phone_number).first()
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este número de teléfono ya está registrado"
        )
    
    # Generate SMS code
    sms_code = generate_verification_code()
    
    # Update temp data with phone and code
    google_data['phone_number'] = request.phone_number
    google_data['sms_code'] = sms_code
    google_data['phone_attempts'] = 0
    store_google_temp_data(request.session_id, google_data)
    
    # Send SMS
    try:
        sms_sent = await SMSService.send_verification_code(
            phone_number=request.phone_number,
            code=sms_code
        )
        if not sms_sent:
            raise Exception("Failed to send SMS")
    except Exception as e:
        logger.error(f"SMS sending error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al enviar el código por SMS"
        )
    
    return {
        "message": "Código de verificación enviado",
        "phone_masked": request.phone_number[:6] + "****" + request.phone_number[-2:]
    }

@router.post("/google/verify-code", response_model=TokenResponse)
async def google_verify_code(request: GoogleVerifyCodeRequest, db: Session = Depends(get_db)):
    """Verify SMS code and create account for Google signup"""
    
    # Get Google data from session
    google_data = get_google_temp_data(request.session_id)
    if not google_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sesión expirada. Por favor inicia el proceso nuevamente."
        )
    
    # Check attempts
    if google_data.get('phone_attempts', 0) >= 5:
        delete_google_temp_data(request.session_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Por favor inicia el proceso nuevamente."
        )
    
    # Validate SMS code
    if not validate_verification_code(request.sms_code, google_data.get('sms_code')):
        # Increment attempts
        google_data['phone_attempts'] = google_data.get('phone_attempts', 0) + 1
        store_google_temp_data(request.session_id, google_data)
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Código incorrecto. Intentos restantes: {5 - google_data['phone_attempts']}"
        )
    
    # Create user account
    try:
        new_user = User(
            email=google_data['email'],
            full_name=google_data['full_name'],
            phone_number=google_data['phone_number'],
            google_id=google_data['google_id'],
            profile_picture=google_data.get('profile_picture'),
            auth_method='google',
            is_verified=True,  # Both email and phone verified
            verification_token=str(uuid.uuid4())
        )
        
        # Create Stripe customer
        stripe_result = await StripeService.create_customer(
            email=google_data['email'],
            name=google_data['full_name']
        )
        
        if stripe_result["success"]:
            new_user.stripe_customer_id = stripe_result["customer_id"]
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Delete temporary data
        delete_google_temp_data(request.session_id)
        
        # Create access token
        access_token = create_access_token(data={"sub": str(new_user.id)})
        
        # Send welcome email
        try:
            await EmailService.send_welcome_email(
                email=new_user.email,
                name=new_user.full_name or new_user.email
            )
        except Exception as e:
            logger.error(f"Failed to send welcome email: {str(e)}")
        
        return TokenResponse(
            access_token=access_token,
            user={
                "id": str(new_user.id),
                "email": new_user.email,
                "full_name": new_user.full_name,
                "plan_type": new_user.plan_type,
                "is_verified": True,
                "auth_method": new_user.auth_method
            }
        )
        
    except Exception as e:
        logger.error(f"Error creating Google user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la cuenta. Por favor intenta nuevamente."
        )

@router.post("/link-google")
async def link_google_account(
    request: LinkGoogleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Link Google account to existing user"""
    
    if current_user.google_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta cuenta ya tiene Google vinculado"
        )
    
    try:
        # Verify the ID token
        google_user = GoogleOAuthService.verify_id_token(request.id_token)
        
        # Check if this Google account is already linked to another user
        existing_google = db.query(User).filter(
            User.google_id == google_user['google_id']
        ).first()
        
        if existing_google:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta cuenta de Google ya está vinculada a otro usuario"
            )
        
        # Check if email matches
        if current_user.email != google_user['email']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El email de Google no coincide con tu cuenta"
            )
        
        # Link the account
        current_user.link_google_account(
            google_id=google_user['google_id'],
            profile_picture=google_user.get('picture')
        )
        
        db.commit()
        
        return {
            "message": "Cuenta de Google vinculada exitosamente",
            "auth_method": current_user.auth_method
        }
        
    except Exception as e:
        logger.error(f"Error linking Google account: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

# Original endpoints (unchanged)
@router.post("/pre-register")
async def pre_register(user_data: UserPreRegister, request: Request, db: Session = Depends(get_db)):
    """Step 1: Validate data and send verification codes"""
    
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este correo ya está registrado"
        )
    
    # Check if phone already exists
    existing_phone = db.query(User).filter(User.phone_number == user_data.phone_number).first()
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este número de teléfono ya está registrado"
        )
    
    # Check if already has pending registration
    existing_reg = get_temp_registration(user_data.email)
    if existing_reg:
        # Check if codes were sent recently (prevent spam)
        sent_time = datetime.fromisoformat(existing_reg['timestamp'])
        time_since_last = datetime.utcnow() - sent_time
        
        if time_since_last < timedelta(seconds=30):
            wait_seconds = 30 - int(time_since_last.total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Espera {wait_seconds} segundos antes de solicitar nuevos códigos"
            )
    
    # Generate verification codes
    email_code = generate_verification_code()
    sms_code = generate_verification_code()
    
    # Store registration data temporarily
    registration_data = {
        'email': user_data.email,
        'password_hash': hash_password(user_data.password),
        'full_name': user_data.full_name,
        'phone_number': user_data.phone_number,
        'email_code': email_code,
        'sms_code': sms_code,
        'attempts': 0,
        'auth_method': 'password'
    }
    
    store_temp_registration(user_data.email, registration_data)
    
    # Send email code
    try:
        email_sent = await EmailService.send_verification_code(
            email=user_data.email,
            name=user_data.full_name or "Usuario",
            code=email_code
        )
        if not email_sent:
            logger.error(f"Failed to send email to {user_data.email}")
    except Exception as e:
        logger.error(f"Email sending error: {str(e)}")
        delete_temp_registration(user_data.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al enviar el código de verificación por email"
        )
    
    # Send SMS code
    try:
        sms_sent = await SMSService.send_verification_code(
            phone_number=user_data.phone_number,
            code=sms_code
        )
        if not sms_sent:
            logger.error(f"Failed to send SMS to {user_data.phone_number}")
    except Exception as e:
        logger.error(f"SMS sending error: {str(e)}")
    
    return {
        "message": "Códigos de verificación enviados",
        "email": user_data.email,
        "phone_masked": user_data.phone_number[:6] + "****" + user_data.phone_number[-2:]
    }

@router.post("/verify-codes", response_model=TokenResponse)
async def verify_codes(verify_data: VerifyCodesRequest, request: Request, db: Session = Depends(get_db)):
    """Step 2: Verify codes and create account"""
    
    # Get registration data
    reg_data = get_temp_registration(verify_data.email)
    if not reg_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sesión de registro expirada. Por favor inicia el proceso nuevamente."
        )
    
    # Check attempts
    if reg_data['attempts'] >= 5:
        delete_temp_registration(verify_data.email)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos fallidos. Por favor inicia el proceso nuevamente."
        )
    
    # Validate codes
    email_valid = validate_verification_code(verify_data.email_code, reg_data['email_code'])
    sms_valid = validate_verification_code(verify_data.sms_code, reg_data['sms_code'])
    
    if not email_valid or not sms_valid:
        # Increment attempts
        reg_data['attempts'] += 1
        store_temp_registration(verify_data.email, reg_data)
        
        error_msg = []
        if not email_valid:
            error_msg.append("Código de email incorrecto")
        if not sms_valid:
            error_msg.append("Código de SMS incorrecto")
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=". ".join(error_msg) + f". Intentos restantes: {5 - reg_data['attempts']}"
        )
    
    # Codes are valid! Create the account
    try:
        # Create new user
        new_user = User(
            email=reg_data['email'],
            password_hash=reg_data['password_hash'],
            full_name=reg_data['full_name'],
            phone_number=reg_data['phone_number'],
            auth_method=reg_data.get('auth_method', 'password'),
            is_verified=True,  # Already verified both email and phone
            verification_token=str(uuid.uuid4())
        )
        
        # Create Stripe customer
        stripe_result = await StripeService.create_customer(
            email=reg_data['email'],
            name=reg_data['full_name']
        )
        
        if stripe_result["success"]:
            new_user.stripe_customer_id = stripe_result["customer_id"]
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Delete temporary registration data
        delete_temp_registration(verify_data.email)
        
        # Create access token
        access_token = create_access_token(data={"sub": str(new_user.id)})
        
        # Send welcome email
        try:
            await EmailService.send_welcome_email(
                email=new_user.email,
                name=new_user.full_name or new_user.email
            )
        except Exception as e:
            logger.error(f"Failed to send welcome email: {str(e)}")
        
        return TokenResponse(
            access_token=access_token,
            user={
                "id": str(new_user.id),
                "email": new_user.email,
                "full_name": new_user.full_name,
                "plan_type": new_user.plan_type,
                "is_verified": True,
                "auth_method": new_user.auth_method
            }
        )
        
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la cuenta. Por favor intenta nuevamente."
        )

@router.post("/resend-code")
async def resend_code(resend_data: ResendCodeRequest, db: Session = Depends(get_db)):
    """Resend verification code"""
    
    # Get registration data
    reg_data = get_temp_registration(resend_data.email)
    if not reg_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No hay sesión de registro activa"
        )
    
    # Check rate limiting
    sent_time = datetime.fromisoformat(reg_data['timestamp'])
    time_since_last = datetime.utcnow() - sent_time
    
    if time_since_last < timedelta(seconds=30):
        wait_seconds = 30 - int(time_since_last.total_seconds())
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Espera {wait_seconds} segundos antes de solicitar un nuevo código"
        )
    
    # Update timestamp
    reg_data['timestamp'] = datetime.utcnow().isoformat()
    
    if resend_data.code_type == 'email':
        # Resend email code
        try:
            email_sent = await EmailService.send_verification_code(
                email=reg_data['email'],
                name=reg_data['full_name'] or "Usuario",
                code=reg_data['email_code']
            )
            if not email_sent:
                raise Exception("Failed to send email")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al enviar el código por email"
            )
    elif resend_data.code_type == 'sms':
        # Resend SMS code
        try:
            sms_sent = await SMSService.send_verification_code(
                phone_number=reg_data['phone_number'],
                code=reg_data['sms_code']
            )
            if not sms_sent:
                raise Exception("Failed to send SMS")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al enviar el código por SMS"
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de código inválido"
        )
    
    # Update stored data
    store_temp_registration(resend_data.email, reg_data)
    
    return {"message": f"Código reenviado por {resend_data.code_type}"}

@router.post("/login", response_model=TokenResponse)
async def login(user_data: UserLogin, request: Request, db: Session = Depends(get_db)):
    """Login user"""
    # Find user
    user = db.query(User).filter(User.email == user_data.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos"
        )
    
    # Check if user can use password login
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta cuenta solo puede iniciar sesión con Google"
        )
    
    # Verify password
    if not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta inactiva"
        )
    
    # Get device fingerprint and IP
    user_agent = request.headers.get("user-agent", "")
    accept_language = request.headers.get("accept-language", "")
    accept_encoding = request.headers.get("accept-encoding", "")
    device_fingerprint = generate_device_fingerprint(user_agent, accept_language, accept_encoding)
    client_ip = request.client.host
    
    # Check for suspicious activity
    if check_suspicious_activity(
        user.ip_addresses or [],
        user.device_fingerprints or [],
        client_ip,
        device_fingerprint
    ):
        user.suspicious_activity_count += 1
        if user.suspicious_activity_count >= 3:
            user.is_active = False
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cuenta suspendida por actividad sospechosa. Contacta a soporte."
            )
    
    # Update tracking info
    if not user.ip_addresses:
        user.ip_addresses = []
    if not user.device_fingerprints:
        user.device_fingerprints = []
    
    if client_ip not in user.ip_addresses:
        user.ip_addresses.append(client_ip)
        user.ip_addresses = user.ip_addresses[-10:]  # Keep last 10 IPs
    
    if device_fingerprint not in user.device_fingerprints:
        user.device_fingerprints.append(device_fingerprint)
        user.device_fingerprints = user.device_fingerprints[-10:]  # Keep last 10 devices
    
    user.last_login = datetime.utcnow()
    db.commit()
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})
    
    return TokenResponse(
        access_token=access_token,
        user={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "plan_type": user.plan_type,
            "is_verified": user.is_verified,
            "auth_method": user.auth_method
        }
    )

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "plan_type": current_user.plan_type,
        "is_verified": current_user.is_verified,
        "created_at": current_user.created_at.isoformat(),
        "auth_method": current_user.auth_method,
        "has_password": current_user.password_hash is not None,
        "has_google": current_user.google_id is not None,
        "profile_picture": current_user.profile_picture
    }

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """Logout user"""
    return {"message": "Successfully logged out"}