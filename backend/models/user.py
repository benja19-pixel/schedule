from sqlalchemy import Column, String, DateTime, Boolean, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from database.connection import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # Nullable para usuarios de Google
    full_name = Column(String(255))
    phone_number = Column(String(20), unique=True, nullable=True, index=True)
    
    # OAuth fields
    google_id = Column(String(255), unique=True, nullable=True, index=True)  # Google user ID
    auth_method = Column(String(50), default="password", nullable=False)  # password, google
    profile_picture = Column(String(500), nullable=True)  # URL de la foto de perfil
    
    # Plan information
    plan_type = Column(String(50), default="free", nullable=False)  # free, pro, premium, developer
    stripe_customer_id = Column(String(255))
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    verification_token = Column(String(255))
    
    # Trial tracking
    has_used_trial = Column(Boolean, default=False, nullable=False)
    trial_used_date = Column(DateTime)
    trial_plan_type = Column(String(50))
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Security tracking
    ip_addresses = Column(JSON, default=list)  # List of recent IPs
    device_fingerprints = Column(JSON, default=list)  # List of device fingerprints
    suspicious_activity_count = Column(Integer, default=0)
    
    # Usage tracking
    verifications_today = Column(Integer, default=0)
    corrections_today = Column(Integer, default=0)
    last_usage_reset = Column(DateTime, default=datetime.utcnow)
    
    # Subscription tracking
    last_subscription_end = Column(DateTime)
    subscription_history = Column(JSON, default=list)
    
    # Additional data for future use
    extra_data = Column(JSON, default=dict)
    
    def __repr__(self):
        return f"<User {self.email}>"
    
    def mark_trial_used(self, plan_type: str):
        """Marca que el usuario ya usó su trial lifetime"""
        self.has_used_trial = True
        self.trial_used_date = datetime.utcnow()
        self.trial_plan_type = plan_type
    
    def add_to_subscription_history(self, plan_type: str, action: str):
        """Agrega evento al historial de suscripciones"""
        if not self.subscription_history:
            self.subscription_history = []
        
        self.subscription_history.append({
            "plan_type": plan_type,
            "action": action,  # "started", "cancelled", "expired", "trial_started", "trial_ended"
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Mantener solo los últimos 50 eventos
        if len(self.subscription_history) > 50:
            self.subscription_history = self.subscription_history[-50:]
    
    def can_use_password_login(self):
        """Verifica si el usuario puede hacer login con password"""
        return self.password_hash is not None
    
    def can_use_google_login(self):
        """Verifica si el usuario puede hacer login con Google"""
        return self.google_id is not None
    
    def link_google_account(self, google_id: str, profile_picture: str = None):
        """Vincula una cuenta de Google al usuario"""
        self.google_id = google_id
        if profile_picture:
            self.profile_picture = profile_picture
        if self.auth_method == "password":
            self.auth_method = "both"  # Puede usar ambos métodos
    
    def set_password(self, password_hash: str):
        """Establece una contraseña para el usuario"""
        self.password_hash = password_hash
        if self.auth_method == "google":
            self.auth_method = "both"  # Puede usar ambos métodos