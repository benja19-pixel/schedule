# 🔍 TruthLens - AI Hallucination Detector

TruthLens es un verificador de alucinaciones de IA que detecta y corrige información falsa en textos generados por ChatGPT, Claude, Gemini y otras IAs.

## 🚀 Características

- **Detección precisa**: Identifica errores factuales con 95% de precisión
- **Corrección automática**: Corrige errores y sugiere fuentes confiables
- **Panel de cambios**: Revisa y edita cada cambio antes de aplicarlo
- **Planes flexibles**: Desde gratuito hasta empresarial
- **API para desarrolladores**: Integra TruthLens en tus aplicaciones

## 📋 Requisitos

- Python 3.13+
- PostgreSQL 13+
- Redis 6+
- Node.js 16+ (para herramientas de desarrollo)

## 🛠️ Instalación

### Instalación Rápida en macOS

```bash
# 1. Dar permisos de ejecución al script
chmod +x scripts/setup_macos.sh

# 2. Ejecutar el script de setup
./scripts/setup_macos.sh

# 3. ¡Listo! La aplicación estará en http://localhost:8000
```

### Instalación Manual

### 1. Clonar el repositorio

```bash
git clone https://github.com/yourusername/truthlens.git
cd truthlens
```

### 2. Configurar el entorno virtual

```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install -r backend/requirements.txt
```

### 4. Configurar variables de entorno

```bash
cp backend/.env.example backend/.env
```

Edita `backend/.env` con tus claves API:
- OpenAI API Key
- Perplexity API Key (proporcionada)
- Stripe Keys (proporcionadas)
- Database URL

### 5. Configurar la base de datos

#### Opción A: Usando Docker Compose (Recomendado)

```bash
# Usar el comando moderno (sin guión)
docker compose up -d postgres redis
```

#### Opción B: Instalación manual

```bash
# PostgreSQL
createuser truthlens -P
createdb truthlens_db -O truthlens

# Redis
redis-server
```

### 6. Ejecutar migraciones

```bash
python scripts/setup.py
```

### 7. Configurar Stripe

1. Los productos ya están creados con estos IDs:
   - **Pro**: prod_SRKKgTqdXSSGYp ($299/mes o $2,500/año)
   - **Premium**: prod_SRKKhox5Y30dmf ($599/mes o $6,000/año)
   - **Developer**: prod_SRKL2rVIVgFuqA ($1,999/mes o $15,000/año)

2. Configura el webhook endpoint en Stripe:
   - URL: `https://tudominio.com/api/webhooks/stripe`
   - Eventos a escuchar:
     - `checkout.session.completed`
     - `customer.subscription.created`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
     - `invoice.payment_succeeded`
     - `invoice.payment_failed`

3. Copia el webhook secret y actualiza `backend/.env`:
   ```
   STRIPE_WEBHOOK_SECRET=whsec_tu_webhook_secret_aqui
   ```

## 🚀 Ejecutar la aplicación

### Desarrollo

```bash
# Opción 1: Directamente
python backend/app.py

# Opción 2: Con Docker Compose
docker compose up
```

La aplicación estará disponible en: http://localhost:8000

### Producción

```bash
# Con Gunicorn
gunicorn backend.app:app -c config/gunicorn.conf.py

# Con Docker
docker compose --profile production up
```

## 📁 Estructura del proyecto

```
truthlens/
├── backend/           # API y lógica de negocio
│   ├── api/          # Endpoints
│   ├── core/         # Lógica principal
│   ├── models/       # Modelos de base de datos
│   ├── services/     # Servicios externos
│   └── utils/        # Utilidades
├── frontend/         # Interfaz de usuario
│   ├── static/       # CSS, JS, imágenes
│   ├── templates/    # Plantillas HTML
│   └── public/       # Archivos públicos
├── scripts/          # Scripts de utilidad
├── config/           # Configuraciones
└── tests/           # Pruebas
```

## 🧪 Pruebas

```bash
# Backend tests
pytest tests/backend/

# Frontend tests
npm test
```

## 📚 API Documentation

### Autenticación

```bash
POST /api/auth/register
POST /api/auth/login
GET  /api/auth/me
```

### Verificaciones

```bash
POST /api/verification/verify
GET  /api/verification/{id}
POST /api/verification/{id}/correct
POST /api/verification/{id}/improve-sources
```

### Suscripciones

```bash
POST /api/subscription/create-checkout-session
POST /api/subscription/cancel-subscription
GET  /api/subscription/current-subscription
```

## 🔐 Seguridad

- JWT para autenticación
- Rate limiting por plan
- Detección de compartición de cuentas
- Encriptación de datos sensibles
- CORS configurado correctamente

## 🤝 Contribuir

1. Fork el proyecto
2. Crea tu rama (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Ver `LICENSE` para más información.

## 📞 Soporte

- Email: support@truthlens.com
- Documentation: https://docs.truthlens.com
- Discord: https://discord.gg/truthlens

## 🚨 Notas importantes

1. **Claves API**: Las claves proporcionadas son temporales. Cámbialas antes de producción.
2. **Base de datos**: Realiza backups regulares de PostgreSQL.
3. **Monitoreo**: Configura Sentry o similar para monitoreo de errores.
4. **SSL**: Usa HTTPS en producción con Let's Encrypt.

---

Desarrollado con ❤️ por el equipo de TruthLens