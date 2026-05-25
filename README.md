# AI Agent Microservice

Microservicio base para un agente de IA con:

- `FastAPI` para exponer la API
- `PostgreSQL` para persistencia
- `SQLAlchemy` para acceso a datos
- `Docker` y `docker-compose` para despliegue local
- Proveedor de IA configurable: `mock` o `Groq`

## Estructura

```text
app/
  api/
  core/
  db/
  models/
  schemas/
  services/
```

## Variables de entorno

1. Copia `.env.example` a `.env`
2. Ajusta las credenciales si hace falta

Variables clave:

- `DATABASE_URL`
- `LLM_PROVIDER`
- `GROQ_API_KEY`
- `GROQ_MODEL`
- `GROQ_BASE_URL`
- `AUTH_API_URL`
- `CARS_API_URL`
- `MOTORCYCLES_API_URL`
- `ELECTROBIKES_API_URL`
- `SCOOTERS_API_URL`
- `REPORTS_API_URL`
- `AGENT_SYSTEM_PROMPT`

Ejemplo de conexion local para PostgreSQL:

- Host: `127.0.0.1`
- Puerto: `5432`
- Usuario: `postgres`
- Password: `postgres`
- Schema: `ai_agent_db`

## Levantar con Docker

```bash
docker compose up --build
```

API disponible en `http://localhost:8000`

Documentacion Swagger en `http://localhost:8000/docs`

## Proveedores de IA

`LLM_PROVIDER=mock`

Sirve para desplegar la API sin costo de inferencia. Responde con fallback local y valida todo el flujo de negocio, API y PostgreSQL.

`LLM_PROVIDER=groq`

Sirve para desplegar con inferencia real usando Groq como proveedor administrado. Requiere `GROQ_API_KEY`.

## Endpoints

- `GET /health`
- `GET /api/v1/conversations`
- `POST /api/v1/conversations`
- `GET /api/v1/conversations/{conversation_id}`
- `POST /api/v1/agent/run`

Ejemplo por API Gateway:

```http
POST https://qz-gateway.onrender.com/api/v1/agent/run
Authorization: Bearer TU_TOKEN
Content-Type: application/json
```

```json
{
  "prompt": "Cuantas motos hay en la tienda?"
}
```

Cuando el prompt pregunta por datos reales de la aplicacion, el agente consulta
los microservicios correspondientes y usa ese contexto antes de responder:

- Carros: `CARS_API_URL/api/cars`
- Motos: `MOTORCYCLES_API_URL/api/motorcycles/`
- Electrobikes: `ELECTROBIKES_API_URL/api/electrobikes`
- Scooters: `SCOOTERS_API_URL/api/scooters`
- Reportes de ventas: `REPORTS_API_URL/api/reports`
- Usuarios: `AUTH_API_URL/qzMotorCenter/auth` usando el token reenviado por el gateway

Ejemplos de prompts:

- `Cuantas motos hay en la tienda?`
- `Dame un resumen del inventario`
- `Cuantos carros y scooters hay?`
- `Cuantas ventas hay registradas?`
- `Cuantos usuarios existen?`

## Comportamiento del agente

El microservicio usa el proveedor definido en `LLM_PROVIDER`.

Si el proveedor falla, no esta disponible o no tiene credenciales validas, el servicio hace fallback automatico a una respuesta local y sigue guardando la conversacion en PostgreSQL.
