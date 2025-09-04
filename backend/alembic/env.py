from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys
from pathlib import Path
import importlib
import pkgutil

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Import your Base
from database.connection import Base

# ====== IMPORTACIÓN DINÁMICA DE TODOS LOS MODELOS ======
def import_all_models():
    """
    Importa dinámicamente todos los modelos del directorio models/
    No necesitas modificar esto cuando agregues nuevos modelos
    """
    import models
    
    # Obtener la ruta del paquete models
    models_path = Path(models.__file__).parent
    
    # Importar todos los módulos .py en el directorio models/
    for file in models_path.glob("*.py"):
        if file.name.startswith("_"):
            continue  # Saltar __init__.py, __pycache__, etc.
            
        module_name = file.stem  # nombre sin .py
        try:
            # Importar el módulo dinámicamente
            module = importlib.import_module(f"models.{module_name}")
            print(f"✓ Imported models.{module_name}")
            
            # Importar todas las clases que hereden de Base
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, Base) and 
                    attr is not Base):
                    print(f"  - Found model: {attr_name}")
                    
        except Exception as e:
            print(f"⚠ Could not import models.{module_name}: {e}")

# Importar todos los modelos automáticamente
print("=" * 50)
print("Loading all models for Alembic...")
print("=" * 50)
import_all_models()
print("=" * 50)

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Override with environment variable if available
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        configuration = config.get_section(config.config_ini_section)
        configuration['sqlalchemy.url'] = database_url
    
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()