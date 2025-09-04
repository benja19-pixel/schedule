# models/__init__.py
"""
Importación dinámica de todos los modelos.
No necesitas modificar este archivo cuando agregues nuevos modelos.
"""

import os
import importlib
from pathlib import Path

# Obtener el directorio actual
current_dir = Path(__file__).parent

# Lista para almacenar todos los modelos encontrados
__all__ = []

# Diccionario para almacenar los modelos importados
_models = {}

def import_all_models():
    """
    Importa dinámicamente todos los archivos .py en este directorio
    """
    for file_path in current_dir.glob("*.py"):
        # Saltar __init__.py y archivos que empiecen con _
        if file_path.name.startswith("_"):
            continue
            
        module_name = file_path.stem
        
        try:
            # Importar el módulo
            module = importlib.import_module(f".{module_name}", package="models")
            
            # Buscar todas las clases en el módulo
            for item_name in dir(module):
                item = getattr(module, item_name)
                
                # Si es una clase y no es importada de otro lado
                if (isinstance(item, type) and 
                    item.__module__.startswith('models.') and
                    not item_name.startswith('_')):
                    
                    # Agregar al namespace actual
                    globals()[item_name] = item
                    _models[item_name] = item
                    __all__.append(item_name)
                    
        except ImportError as e:
            print(f"Warning: Could not import models.{module_name}: {e}")
        except Exception as e:
            print(f"Error loading models.{module_name}: {e}")

# Ejecutar la importación automática
import_all_models()

# Función de utilidad para listar todos los modelos
def list_all_models():
    """Retorna una lista de todos los modelos cargados"""
    return list(_models.keys())

def get_model(name):
    """Obtiene un modelo por nombre"""
    return _models.get(name)

# Imprimir resumen (opcional, puedes comentar esto en producción)
if __all__:
    print(f"Models package loaded {len(__all__)} models: {', '.join(sorted(__all__))}")