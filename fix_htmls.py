#!/usr/bin/env python3
"""
Script para agregar el mock-auth.js a todos los HTMLs
"""

import os
from pathlib import Path

def fix_html_files():
    """Agrega el script mock-auth.js a todos los HTMLs"""
    
    # Ruta a los templates
    templates_dir = Path("frontend/templates")
    
    # HTMLs que necesitan ser arreglados
    html_files = [
        "patients.html",
        "miagenda.html", 
        "configurar-horario.html",
        "configurar-servicios.html",
        "mis-consultorios.html"
    ]
    
    mock_auth_line = '    <script src="/static/js/mock-auth.js"></script>\n'
    
    for html_file in html_files:
        file_path = templates_dir / html_file
        
        if not file_path.exists():
            print(f"⚠️  {html_file} no encontrado")
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Verificar si ya tiene el mock-auth
        if 'mock-auth.js' in content:
            print(f"✅ {html_file} ya tiene mock-auth.js")
            continue
        
        # Buscar dónde insertar (después de Font Awesome)
        if '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome' in content:
            lines = content.split('\n')
            new_lines = []
            inserted = False
            
            for line in lines:
                new_lines.append(line)
                # Insertar después de Font Awesome
                if not inserted and 'font-awesome' in line and '</link>' not in line:
                    new_lines.append('')
                    new_lines.append('    <!-- Mock Auth para desarrollo -->')
                    new_lines.append(mock_auth_line.rstrip())
                    inserted = True
            
            if inserted:
                new_content = '\n'.join(new_lines)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"✅ {html_file} actualizado con mock-auth.js")
            else:
                print(f"⚠️  No se pudo actualizar {html_file}")
        else:
            print(f"⚠️  {html_file} no tiene Font Awesome, agregando al head...")
            # Buscar </head> y agregar antes
            if '</head>' in content:
                content = content.replace(
                    '</head>',
                    f'    <!-- Mock Auth para desarrollo -->\n{mock_auth_line}</head>'
                )
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"✅ {html_file} actualizado con mock-auth.js")

if __name__ == "__main__":
    print("\n=== Arreglando archivos HTML ===\n")
    fix_html_files()
    print("\n✅ Proceso completado")
    print("\nAhora los HTMLs deberían funcionar correctamente.")
    print("Reinicia el servidor con: python backend/app.py")