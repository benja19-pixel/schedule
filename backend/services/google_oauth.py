import logging
from typing import Optional, Dict, Any
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from config import settings
import json

logger = logging.getLogger(__name__)

class GoogleOAuthService:
    """Service to handle Google OAuth authentication"""
    
    # Google OAuth scopes
    SCOPES = [
        'openid',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile'
    ]
    
    @staticmethod
    def get_google_auth_flow():
        """Create and return Google OAuth flow"""
        client_config = {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": [settings.google_redirect_uri]
            }
        }
        
        flow = Flow.from_client_config(
            client_config,
            scopes=GoogleOAuthService.SCOPES,
            redirect_uri=settings.google_redirect_uri
        )
        
        return flow
    
    @staticmethod
    def get_authorization_url(state: Optional[str] = None) -> tuple[str, str]:
        """
        Get Google OAuth authorization URL
        Returns: (authorization_url, state)
        """
        flow = GoogleOAuthService.get_google_auth_flow()
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='select_account',  # Always show account selection
            state=state
        )
        
        logger.info(f"Generated Google auth URL with state: {state}")
        return authorization_url, state
    
    @staticmethod
    def exchange_code_for_token(code: str, state: Optional[str] = None) -> Dict[str, Any]:
        """
        Exchange authorization code for access token
        Returns user info from Google
        """
        try:
            flow = GoogleOAuthService.get_google_auth_flow()
            
            # Exchange code for token
            flow.fetch_token(code=code)
            
            # Get credentials
            credentials = flow.credentials
            
            # Verify and decode ID token with clock skew tolerance
            idinfo = id_token.verify_oauth2_token(
                credentials.id_token,
                google_requests.Request(),
                settings.google_client_id,
                clock_skew_in_seconds=10  # AGREGADO: Tolera 10 segundos de diferencia
            )
            
            # Extract user info
            user_info = {
                'google_id': idinfo.get('sub'),
                'email': idinfo.get('email'),
                'email_verified': idinfo.get('email_verified', False),
                'name': idinfo.get('name'),
                'given_name': idinfo.get('given_name'),
                'family_name': idinfo.get('family_name'),
                'picture': idinfo.get('picture'),
                'locale': idinfo.get('locale', 'es')
            }
            
            logger.info(f"Successfully authenticated Google user: {user_info['email']}")
            return user_info
            
        except Exception as e:
            logger.error(f"Error exchanging Google code for token: {str(e)}")
            raise Exception("Error al autenticar con Google")
    
    @staticmethod
    def verify_id_token(token: str) -> Dict[str, Any]:
        """
        Verify Google ID token (for frontend authentication)
        Used when using Google Sign-In JavaScript library
        """
        try:
            # Verify the token with clock skew tolerance
            idinfo = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                settings.google_client_id,
                clock_skew_in_seconds=10  # AGREGADO: Tolera 10 segundos de diferencia
            )
            
            # Token is valid
            user_info = {
                'google_id': idinfo.get('sub'),
                'email': idinfo.get('email'),
                'email_verified': idinfo.get('email_verified', False),
                'name': idinfo.get('name'),
                'given_name': idinfo.get('given_name'),
                'family_name': idinfo.get('family_name'),
                'picture': idinfo.get('picture'),
                'locale': idinfo.get('locale', 'es')
            }
            
            return user_info
            
        except ValueError as e:
            logger.error(f"Invalid Google ID token: {str(e)}")
            raise Exception("Token de Google inválido")
        except Exception as e:
            logger.error(f"Error verifying Google ID token: {str(e)}")
            raise Exception("Error al verificar token de Google")
    
    @staticmethod
    def create_redirect_html(redirect_url: str) -> str:
        """
        Create HTML page for OAuth redirect
        This handles the redirect back to the frontend after OAuth
        """
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Autenticando...</title>
            <style>
                body {{
                    background: #000;
                    color: #fff;
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }}
                .container {{
                    text-align: center;
                }}
                .spinner {{
                    border: 3px solid rgba(255,255,255,0.3);
                    border-radius: 50%;
                    border-top: 3px solid #fff;
                    width: 40px;
                    height: 40px;
                    animation: spin 1s linear infinite;
                    margin: 0 auto 20px;
                }}
                @keyframes spin {{
                    0% {{ transform: rotate(0deg); }}
                    100% {{ transform: rotate(360deg); }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="spinner"></div>
                <p>Autenticando con Google...</p>
                <p style="color: #666; font-size: 14px;">Serás redirigido en un momento</p>
            </div>
            <script>
                // Redirect to the app with the result
                setTimeout(() => {{
                    window.location.href = "{redirect_url}";
                }}, 1000);
            </script>
        </body>
        </html>
        """
        return html
    
    @staticmethod
    def get_user_info_from_access_token(access_token: str) -> Dict[str, Any]:
        """
        Get user info using access token
        This calls Google's userinfo endpoint
        """
        try:
            import requests as req
            
            response = req.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={'Authorization': f'Bearer {access_token}'}
            )
            
            if response.status_code != 200:
                raise Exception("Error al obtener información del usuario")
            
            user_data = response.json()
            
            return {
                'google_id': user_data.get('id'),
                'email': user_data.get('email'),
                'email_verified': user_data.get('verified_email', False),
                'name': user_data.get('name'),
                'given_name': user_data.get('given_name'),
                'family_name': user_data.get('family_name'),
                'picture': user_data.get('picture'),
                'locale': user_data.get('locale', 'es')
            }
            
        except Exception as e:
            logger.error(f"Error getting user info from access token: {str(e)}")
            raise Exception("Error al obtener información del usuario de Google")
    
    @staticmethod
    def validate_email_domain(email: str, allowed_domains: Optional[list] = None) -> bool:
        """
        Validate if email domain is allowed
        Useful for restricting signups to specific domains
        """
        if not allowed_domains:
            return True
        
        domain = email.split('@')[1].lower()
        return domain in [d.lower() for d in allowed_domains]
    
    @staticmethod
    def format_user_data_for_registration(google_user_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format Google user data for registration
        """
        return {
            'email': google_user_info['email'],
            'full_name': google_user_info.get('name', ''),
            'google_id': google_user_info['google_id'],
            'profile_picture': google_user_info.get('picture'),
            'email_verified': google_user_info.get('email_verified', False),
            'auth_method': 'google'
        }

# Testing function
if __name__ == "__main__":
    # Test getting authorization URL
    auth_url, state = GoogleOAuthService.get_authorization_url()
    print(f"Authorization URL: {auth_url}")
    print(f"State: {state}")