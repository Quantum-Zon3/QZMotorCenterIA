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
- `MOTORCYCLES_API_URL`
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

Cuando el prompt pregunta por la cantidad de motos, el agente consulta
`MOTORCYCLES_API_URL/api/motorcycles/` y usa ese dato real como contexto antes
de responder.

## Comportamiento del agente

El microservicio usa el proveedor definido en `LLM_PROVIDER`.

Si el proveedor falla, no esta disponible o no tiene credenciales validas, el servicio hace fallback automatico a una respuesta local y sigue guardando la conversacion en PostgreSQL.
