#!/usr/bin/env python3
"""
Setup Script para MediConnect Development - VERSION AUTOMÁTICA
Crea la base de datos, tablas y datos iniciales de prueba
TOTALMENTE AUTOMÁTICO - No requiere configuración manual
"""

import os
import sys
import psycopg2
from psycopg2 import sql
from datetime import datetime, date, timedelta
import uuid
from pathlib import Path
import getpass
import platform

# Colores para la terminal
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_step(message):
    """Imprime un paso del proceso"""
    print(f"{Colors.OKBLUE}► {message}{Colors.ENDC}")

def print_success(message):
    """Imprime un mensaje de éxito"""
    print(f"{Colors.OKGREEN}✓ {message}{Colors.ENDC}")

def print_error(message):
    """Imprime un mensaje de error"""
    print(f"{Colors.FAIL}✗ {message}{Colors.ENDC}")

def print_warning(message):
    """Imprime una advertencia"""
    print(f"{Colors.WARNING}⚠ {message}{Colors.ENDC}")

def detect_postgres_config():
    """Detecta automáticamente la configuración de PostgreSQL"""
    print_step("Detectando configuración de PostgreSQL...")
    
    # Obtener el usuario actual del sistema
    current_user = getpass.getuser()
    system_platform = platform.system()
    
    print(f"  Sistema operativo: {system_platform}")
    print(f"  Usuario del sistema: {current_user}")
    
    # Configuraciones comunes por plataforma
    configs_to_try = []
    
    if system_platform == 'Darwin':  # macOS
        configs_to_try.extend([
            {'user': current_user, 'password': ''},  # Usuario del sistema sin password (común en Mac)
            {'user': 'postgres', 'password': 'postgres'},  # Default postgres
            {'user': 'postgres', 'password': ''},  # Postgres sin password
        ])
    elif system_platform == 'Windows':
        configs_to_try.extend([
            {'user': 'postgres', 'password': 'postgres'},  # Más común en Windows
            {'user': 'postgres', 'password': 'admin'},  # Otro default común
            {'user': 'postgres', 'password': '1234'},  # Password simple común
            {'user': 'postgres', 'password': ''},  # Sin password
            {'user': current_user, 'password': ''},  # Usuario del sistema
        ])
    else:  # Linux
        configs_to_try.extend([
            {'user': 'postgres', 'password': 'postgres'},  # Default más común
            {'user': 'postgres', 'password': ''},  # Sin password
            {'user': current_user, 'password': ''},  # Usuario del sistema
        ])
    
    # Intentar cada configuración
    for config in configs_to_try:
        try:
            print(f"  Probando con usuario: {config['user']}")
            connect_params = {
                'host': 'localhost',
                'user': config['user'],
                'port': 5432,
                'database': 'postgres',
                'connect_timeout': 3
            }
            
            if config['password']:
                connect_params['password'] = config['password']
            
            conn = psycopg2.connect(**connect_params)
            conn.close()
            
            print_success(f"  Conexión exitosa con usuario: {config['user']}")
            return {
                'host': 'localhost',
                'user': config['user'],
                'password': config['password'],
                'port': 5432
            }
            
        except Exception as e:
            continue
    
    # Si ninguna configuración automática funciona, pedir al usuario
    print_warning("No se pudo detectar automáticamente la configuración")
    print("\nPor favor, ingresa tu configuración de PostgreSQL:")
    
    db_config = {
        'host': input("Host [localhost]: ") or 'localhost',
        'user': input("Usuario de PostgreSQL: "),
        'password': getpass.getpass("Contraseña (dejar vacío si no tiene): "),
        'port': input("Puerto [5432]: ") or 5432
    }
    
    # Convertir puerto a entero si es string
    if isinstance(db_config['port'], str):
        db_config['port'] = int(db_config['port'])
    
    return db_config

def create_database():
    """Crea la base de datos PostgreSQL automáticamente"""
    print_step("Configurando base de datos...")
    
    # Detectar configuración automáticamente
    db_config = detect_postgres_config()
    
    try:
        # Conectar a PostgreSQL
        connect_params = {
            'host': db_config['host'],
            'user': db_config['user'],
            'port': db_config['port'],
            'database': 'postgres'
        }
        
        if db_config['password']:
            connect_params['password'] = db_config['password']
            
        conn = psycopg2.connect(**connect_params)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Verificar si la base de datos ya existe
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'mediconnect_dev'")
        exists = cursor.fetchone()
        
        if exists:
            print_warning("La base de datos 'mediconnect_dev' ya existe")
            print("  Recreando para empezar limpio...")
            
            # Cerrar conexiones existentes
            cursor.execute("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = 'mediconnect_dev' AND pid <> pg_backend_pid()
            """)
            
            cursor.execute('DROP DATABASE IF EXISTS mediconnect_dev')
            cursor.execute('CREATE DATABASE mediconnect_dev')
            print_success("Base de datos recreada")
        else:
            cursor.execute('CREATE DATABASE mediconnect_dev')
            print_success("Base de datos creada")
        
        cursor.close()
        conn.close()
        
        # Actualizar el archivo .env
        update_env_file(db_config)
        
        return db_config
        
    except psycopg2.OperationalError as e:
        print_error(f"Error de conexión: {e}")
        print("\n" + "="*50)
        print("SOLUCIÓN SEGÚN TU SISTEMA OPERATIVO:")
        
        if platform.system() == 'Darwin':
            print("\nMac OS:")
            print("1. Instalar PostgreSQL:")
            print("   brew install postgresql")
            print("2. Iniciar el servicio:")
            print("   brew services start postgresql")
            print("3. Crear usuario si es necesario:")
            print("   createuser -s postgres")
        elif platform.system() == 'Windows':
            print("\nWindows:")
            print("1. Descargar PostgreSQL desde:")
            print("   https://www.postgresql.org/download/windows/")
            print("2. Durante la instalación, recordar la contraseña del usuario 'postgres'")
            print("3. Asegurarse de que el servicio PostgreSQL esté corriendo en Servicios de Windows")
        else:
            print("\nLinux:")
            print("1. Instalar PostgreSQL:")
            print("   sudo apt-get install postgresql postgresql-contrib  # Ubuntu/Debian")
            print("   sudo yum install postgresql-server  # CentOS/RHEL")
            print("2. Iniciar el servicio:")
            print("   sudo service postgresql start")
            print("3. Configurar usuario:")
            print("   sudo -u postgres createuser --superuser $(whoami)")
        
        print("="*50)
        sys.exit(1)
    except Exception as e:
        print_error(f"Error al crear la base de datos: {e}")
        sys.exit(1)

def update_env_file(db_config):
    """Actualiza o crea el archivo .env EN LA CARPETA BACKEND"""
    print_step("Configurando archivo .env...")
    
    # IMPORTANTE: El .env debe estar en backend/
    env_path = Path('backend/.env')
    
    # Crear directorio backend si no existe
    env_path.parent.mkdir(exist_ok=True)
    
    # Eliminar cualquier .env de la raíz (si existe)
    root_env = Path('.env')
    if root_env.exists():
        root_env.unlink()
        print_warning("Eliminado .env de la raíz (debe estar solo en backend/)")
    
    # Construir DATABASE_URL
    if db_config['password']:
        db_url = f"postgresql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/mediconnect_dev"
    else:
        db_url = f"postgresql://{db_config['user']}@{db_config['host']}:{db_config['port']}/mediconnect_dev"
    
    # Contenido del .env
    env_content = f"""# ==========================================
# MEDICONNECT - CONFIGURACIÓN DE DESARROLLO
# Generado automáticamente por setup.py
# ==========================================

# === BASE DE DATOS ===
DATABASE_URL={db_url}

# === APLICACIÓN ===
APP_NAME=MediConnect
APP_URL=http://localhost:8000
FRONTEND_URL=http://localhost:8000
ENVIRONMENT=development
DEBUG=True

# === SEGURIDAD (Solo desarrollo) ===
JWT_SECRET_KEY=development-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# === REDIS (Opcional) ===
REDIS_URL=redis://localhost:6379

# === EMAIL (Deshabilitado en desarrollo) ===
SENDGRID_API_KEY=
FROM_EMAIL=noreply@mediconnect.com
SUPPORT_EMAIL=support@mediconnect.com
RESEND_API_KEY=

# === STRIPE (Deshabilitado en desarrollo) ===
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=

# === GOOGLE (Opcional - agregar keys si necesitas) ===
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_MAPS_API_KEY=

# === CALENDAR SYNC ===
CALENDAR_SYNC_ENABLED=True
CALENDAR_SYNC_INTERVAL_MINUTES=5
GOOGLE_CALENDAR_REDIRECT_URI=http://localhost:8000/api/calendar-sync/google/callback

# === FEATURE FLAGS ===
FEATURE_APPLE_CALENDAR=False
FEATURE_GOOGLE_AUTH=False

# === OPENAI (Opcional) ===
OPENAI_API_KEY=

# === MONITORING (Opcional) ===
SENTRY_DSN=
"""
    
    # Escribir el archivo
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print_success(f"Archivo backend/.env creado con configuración automática")
    print(f"  Usuario BD: {db_config['user']}")
    print(f"  Base de datos: mediconnect_dev")

def create_tables_directly():
    """Crea las tablas directamente usando SQLAlchemy"""
    print_step("Creando tablas en la base de datos...")
    
    # Cambiar al directorio backend para importar correctamente
    original_dir = os.getcwd()
    backend_dir = os.path.join(original_dir, 'backend')
    
    if not os.path.exists(backend_dir):
        print_error("No se encuentra el directorio 'backend'")
        return False
    
    os.chdir(backend_dir)
    sys.path.insert(0, backend_dir)
    
    try:
        # Importar después de cambiar el directorio
        from database.connection import engine, Base
        
        # Importar todos los modelos necesarios
        print("  Importando modelos...")
        from models.user import User
        from models.patient import Patient, PatientAppointment, Payment, ClinicalNote
        from models.horarios import HorarioTemplate, HorarioException
        from models.servicios import ServicioMedico
        from models.consultorio import Consultorio
        from models.calendar_sync import CalendarConnection, SyncedEvent
        
        # Crear todas las tablas
        Base.metadata.create_all(bind=engine)
        print_success("Tablas creadas correctamente")
        
        return True
        
    except ImportError as e:
        print_error(f"Error al importar: {e}")
        print("  Asegúrate de tener todas las dependencias instaladas:")
        print("  pip install -r requirements.txt")
        return False
    except Exception as e:
        print_error(f"Error al crear tablas: {e}")
        return False
    finally:
        os.chdir(original_dir)

def create_test_data():
    """Crea datos de prueba iniciales"""
    print_step("Creando datos de prueba...")
    
    # Cambiar al directorio backend
    original_dir = os.getcwd()
    backend_dir = os.path.join(original_dir, 'backend')
    
    os.chdir(backend_dir)
    sys.path.insert(0, backend_dir)
    
    # Variable para guardar el ID del usuario antes de cerrar la sesión
    user_id_to_return = None
    
    try:
        from database.connection import SessionLocal
        from models.user import User
        from models.patient import Patient
        from models.consultorio import Consultorio
        from models.servicios import ServicioMedico, TipoPrecio
        from models.horarios import HorarioTemplate
        
        db = SessionLocal()
        
        # 1. Crear usuario de prueba
        print_step("  Creando usuario de prueba...")
        test_user = db.query(User).filter(User.email == "demo@mediconnect.com").first()
        
        if not test_user:
            # Generar ID para el usuario
            user_id_to_return = str(uuid.uuid4())
            
            # Crear usuario con el ID generado
            test_user = User(
                id=user_id_to_return,
                email="demo@mediconnect.com",
                full_name="Dr. Demo",
                is_active=True,
                is_verified=True,
                plan_type="premium",
                created_at=datetime.utcnow()
            )
            
            # Manejar el campo de password según el modelo
            if hasattr(test_user, 'hashed_password'):
                test_user.hashed_password = "not_used_in_development"
            elif hasattr(test_user, 'password_hash'):
                test_user.password_hash = "not_used_in_development"
            elif hasattr(test_user, 'password'):
                test_user.password = "not_used_in_development"
            
            db.add(test_user)
            db.commit()
            print_success("  Usuario de prueba creado")
        else:
            # Si ya existe, guardar su ID
            user_id_to_return = test_user.id
            print_warning("  Usuario de prueba ya existe")
        
        # 2. Crear consultorio principal
        print_step("  Creando consultorio principal...")
        consultorio = db.query(Consultorio).filter(
            Consultorio.user_id == user_id_to_return,
            Consultorio.es_principal == True
        ).first()
        
        if not consultorio:
            consultorio = Consultorio(
                user_id=user_id_to_return,
                nombre="Consultorio Principal",
                es_principal=True,
                pais="México",
                estado="Ciudad de México",
                ciudad="Coyoacán",
                calle="Av. Universidad",
                numero="3000",
                colonia="Ciudad Universitaria",
                codigo_postal="04510",
                tiene_estacionamiento=True,
                telefono_consultorio="555-0123-4567",
                email_consultorio="consultorio@mediconnect.com",
                activo=True
            )
            db.add(consultorio)
            db.commit()
            
            # Refrescar para obtener el ID generado
            db.refresh(consultorio)
            consultorio_id = consultorio.id
            
            print_success("  Consultorio principal creado")
        else:
            consultorio_id = consultorio.id
            print_warning("  Consultorio principal ya existe")
        
        # 3. Crear servicios médicos
        print_step("  Creando servicios médicos...")
        servicios_count = db.query(ServicioMedico).filter(
            ServicioMedico.user_id == user_id_to_return
        ).count()
        
        if servicios_count == 0:
            servicios = [
                ServicioMedico(
                    user_id=user_id_to_return,
                    nombre="Consulta inicial",
                    descripcion="Evaluación completa del paciente, historia clínica y diagnóstico inicial",
                    duracion_minutos=60,
                    tipo_precio=TipoPrecio.PRECIO_FIJO,
                    precio=80000,
                    color="#9333ea",
                    display_order=0
                ),
                ServicioMedico(
                    user_id=user_id_to_return,
                    nombre="Consulta de seguimiento",
                    descripcion="Revisión de avances y ajuste de tratamiento",
                    duracion_minutos=30,
                    tipo_precio=TipoPrecio.PRECIO_FIJO,
                    precio=50000,
                    color="#3b82f6",
                    display_order=1
                ),
                ServicioMedico(
                    user_id=user_id_to_return,
                    nombre="Urgencia",
                    descripcion="Atención inmediata para casos urgentes",
                    duracion_minutos=45,
                    tipo_precio=TipoPrecio.PRECIO_POR_EVALUAR,
                    color="#ef4444",
                    display_order=2
                )
            ]
            for servicio in servicios:
                db.add(servicio)
            db.commit()
            print_success("  Servicios médicos creados")
        else:
            print_warning("  Servicios médicos ya existen")
        
        # 4. Crear horarios
        print_step("  Configurando horarios de trabajo...")
        for day in range(7):
            template = db.query(HorarioTemplate).filter(
                HorarioTemplate.user_id == user_id_to_return,
                HorarioTemplate.day_of_week == day
            ).first()
            
            if not template:
                is_active = day < 5  # Lunes a Viernes
                template = HorarioTemplate(
                    user_id=user_id_to_return,
                    day_of_week=day,
                    is_active=is_active,
                    opens_at=datetime.strptime("09:00", "%H:%M").time() if is_active else None,
                    closes_at=datetime.strptime("19:00", "%H:%M").time() if is_active else None,
                    consultorio_id=consultorio_id if is_active else None,
                    time_blocks=[
                        {"start": "13:00", "end": "14:00", "type": "lunch"}
                    ] if is_active else []
                )
                db.add(template)
        
        db.commit()
        print_success("  Horarios configurados")
        
        # 5. Crear pacientes de ejemplo
        print_step("  Creando pacientes de ejemplo...")
        patients_count = db.query(Patient).filter(
            Patient.doctor_id == user_id_to_return
        ).count()
        
        if patients_count == 0:
            patients_data = [
                {
                    "first_name": "María",
                    "last_name": "García López",
                    "age": 32,
                    "sex": "F",
                    "phone": "555-0123-0001",
                    "email": "maria.garcia@email.com",
                    "balance": -50000
                },
                {
                    "first_name": "Juan",
                    "last_name": "Hernández Martínez",
                    "age": 45,
                    "sex": "M",
                    "phone": "555-0123-0002",
                    "email": "juan.hernandez@email.com",
                    "balance": 0
                },
                {
                    "first_name": "Ana",
                    "last_name": "Rodríguez Silva",
                    "age": 28,
                    "sex": "F",
                    "phone": "555-0123-0003",
                    "whatsapp": "555-0123-0003",
                    "balance": 20000
                }
            ]
            
            for patient_data in patients_data:
                patient = Patient(
                    doctor_id=user_id_to_return,
                    **patient_data
                )
                db.add(patient)
            
            db.commit()
            print_success("  Pacientes de ejemplo creados")
        else:
            print_warning("  Pacientes de ejemplo ya existen")
        
        # Cerrar la sesión ANTES de imprimir
        db.close()
        
        print_success("\n✓ Datos de prueba creados correctamente")
        print(f"\n{Colors.BOLD}Usuario de prueba:{Colors.ENDC}")
        print(f"  Email: demo@mediconnect.com")
        print(f"  Nombre: Dr. Demo")
        print(f"  ID: {user_id_to_return}")
        
        return user_id_to_return
        
    except Exception as e:
        print_error(f"Error al crear datos de prueba: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        os.chdir(original_dir)

def verify_installation():
    """Verifica que todo esté instalado correctamente"""
    print_step("Verificando instalación...")
    
    all_good = True
    
    # Verificar Python
    python_version = sys.version_info
    if python_version.major >= 3 and python_version.minor >= 8:
        print_success(f"  Python {python_version.major}.{python_version.minor} ✓")
    else:
        print_error(f"  Python {python_version.major}.{python_version.minor} - Se requiere 3.8+")
        all_good = False
    
    # Verificar PostgreSQL
    try:
        import psycopg2
        print_success("  psycopg2 instalado ✓")
    except ImportError:
        print_error("  psycopg2 no instalado - ejecuta: pip install psycopg2-binary")
        all_good = False
    
    # Verificar que existe requirements.txt
    if Path('requirements.txt').exists():
        print_success("  requirements.txt encontrado ✓")
    else:
        print_error("  requirements.txt no encontrado")
        all_good = False
    
    # Verificar estructura de directorios
    if Path('backend').is_dir() and Path('frontend').is_dir():
        print_success("  Estructura de directorios correcta ✓")
    else:
        print_error("  Faltan directorios backend/ o frontend/")
        all_good = False
    
    return all_good

def main():
    """Función principal del setup - TOTALMENTE AUTOMÁTICA"""
    print(f"\n{Colors.BOLD}{Colors.HEADER}====================================")
    print("   MediConnect - Setup Automático")
    print(f"===================================={Colors.ENDC}\n")
    
    # Verificar instalación
    if not verify_installation():
        print_error("\nHay problemas con la instalación. Por favor, corrige los errores arriba.")
        sys.exit(1)
    
    print_success("Instalación verificada correctamente\n")
    
    # Proceso automático
    try:
        # 1. Crear base de datos (detecta configuración automáticamente)
        db_config = create_database()
        
        # 2. Crear tablas
        if create_tables_directly():
            # 3. Crear datos de prueba
            user_id = create_test_data()
        else:
            user_id = None
            print_error("No se pudieron crear las tablas")
            sys.exit(1)
        
    except KeyboardInterrupt:
        print_warning("\n\nInstalación cancelada por el usuario")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nError inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Instrucciones finales
    print(f"\n{Colors.BOLD}{Colors.OKGREEN}====================================")
    print("   ✓ SETUP COMPLETADO EXITOSAMENTE")
    print(f"===================================={Colors.ENDC}\n")
    
    print(f"{Colors.BOLD}Para iniciar la aplicación:{Colors.ENDC}")
    print("1. cd backend")
    print("2. python app.py")
    print("")
    print(f"{Colors.BOLD}Luego abre en tu navegador:{Colors.ENDC}")
    print("   http://localhost:8000")
    print("")
    print(f"{Colors.BOLD}Páginas disponibles:{Colors.ENDC}")
    print("  • /patients - Gestión de pacientes")
    print("  • /miagenda - Calendario de citas")
    print("  • /configurar-horario - Configuración de horarios")
    print("  • /configurar-servicios - Servicios médicos")
    print("  • /mis-consultorios - Gestión de consultorios")
    
    print(f"\n{Colors.BOLD}Información importante:{Colors.ENDC}")
    print("  • Usuario de prueba: demo@mediconnect.com")
    print("  • No se requiere login (autenticación simulada)")
    print("  • Base de datos: mediconnect_dev")
    print("  • Configuración: backend/.env")
    
    if user_id:
        print(f"  • ID del usuario: {user_id}")
    
    print(f"\n{Colors.OKGREEN}¡Todo listo para empezar a desarrollar!{Colors.ENDC}")

if __name__ == "__main__":
    main()