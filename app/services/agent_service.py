from urllib.parse import urljoin
import re
import unicodedata

import httpx
from openai import APIConnectionError, APIError, AuthenticationError, OpenAI, RateLimitError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.conversation import Conversation, Message


SourceConfig = dict[str, object]


class AgentService:
    def __init__(self) -> None:
        self.provider = settings.llm_provider.strip().lower()
        self.groq_model_name = settings.groq_model
        self.groq_client = (
            OpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)
            if settings.groq_api_key
            else None
        )

    def run(
        self,
        db: Session,
        prompt: str,
        conversation_id: str | None,
        title: str,
        authorization: str | None = None,
    ) -> dict:
        conversation = self._get_or_create_conversation(db, conversation_id, title)
        application_context = self._build_application_context(prompt, authorization)
        prompt_for_model = self._merge_prompt_with_context(prompt, application_context)

        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=prompt,
        )
        db.add(user_message)
        db.flush()

        assistant_text, model_name = self._generate_response(
            prompt=prompt_for_model,
            conversation=conversation,
        )

        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=assistant_text,
            model_name=model_name,
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)

        return {
            "conversation_id": conversation.id,
            "user_message_id": user_message.id,
            "assistant_message_id": assistant_message.id,
            "model": model_name,
            "response": assistant_text,
        }

    def _get_or_create_conversation(
        self, db: Session, conversation_id: str | None, title: str
    ) -> Conversation:
        if conversation_id:
            conversation = db.get(Conversation, conversation_id)
            if conversation:
                return conversation

        conversation = Conversation(title=title)
        db.add(conversation)
        db.flush()
        return conversation

    def _generate_response(self, prompt: str, conversation: Conversation) -> tuple[str, str]:
        if self.provider == "mock":
            return self._build_fallback_response(
                prompt=prompt,
                conversation_id=conversation.id,
                reason="el proveedor configurado es mock para desarrollo o despliegue sin costo",
            )

        if self.provider == "ollama":
            return self._build_fallback_response(
                prompt=prompt,
                conversation_id=conversation.id,
                reason="el proveedor ollama no esta disponible en este despliegue",
            )

        if self.provider == "groq":
            return self._generate_groq_response(prompt=prompt, conversation=conversation)

        return self._build_fallback_response(
            prompt=prompt,
            conversation_id=conversation.id,
            reason=f"el proveedor '{self.provider}' no esta soportado por esta version",
        )

    def _generate_groq_response(self, prompt: str, conversation: Conversation) -> tuple[str, str]:
        if not self.groq_client:
            return self._build_fallback_response(
                prompt=prompt,
                conversation_id=conversation.id,
                reason="no hay GROQ_API_KEY configurada",
            )

        try:
            response = self.groq_client.chat.completions.create(
                model=self.groq_model_name,
                messages=[
                    {"role": "system", "content": settings.agent_system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content or ""
            return content, self.groq_model_name
        except RateLimitError:
            return self._build_fallback_response(
                prompt=prompt,
                conversation_id=conversation.id,
                reason="la cuenta de Groq alcanzo su limite o no tiene capacidad disponible",
            )
        except AuthenticationError:
            return self._build_fallback_response(
                prompt=prompt,
                conversation_id=conversation.id,
                reason="la GROQ_API_KEY no es valida o no tiene permisos",
            )
        except (APIConnectionError, APIError):
            return self._build_fallback_response(
                prompt=prompt,
                conversation_id=conversation.id,
                reason="hubo un problema temporal al conectar con Groq",
            )

    def _build_fallback_response(
        self, prompt: str, conversation_id: str, reason: str
    ) -> tuple[str, str]:
        count_matches = re.findall(r"- ([^:]+): ([0-9]+) (?:registros|modelos|reportes)", prompt)
        if count_matches:
            summary = "; ".join(
                f"{label.lower()}: {count}" for label, count in count_matches
            )
            return (
                f"Datos actuales de la aplicacion: {summary}.",
                "local-dev-fallback",
            )

        if "no se pudo consultar" in prompt:
            return (
                "No pude consultar uno o mas microservicios en este momento. "
                "Intenta nuevamente cuando los servicios esten disponibles.",
                "local-dev-fallback",
            )

        return (
            "Modo desarrollo activo: "
            f"{reason}. "
            f"Recibi el mensaje '{prompt}' en la conversacion {conversation_id}. "
            "La conversacion y los mensajes quedaron guardados correctamente en la base de datos.",
            "local-dev-fallback",
        )

    def _build_application_context(self, prompt: str, authorization: str | None) -> str | None:
        normalized_prompt = self._normalize_text(prompt)
        selected_sources = self._select_sources(normalized_prompt)

        if not selected_sources:
            return None

        context_lines = [
            "Contexto real consultado desde los microservicios de QZ Motor Center:"
        ]

        for source in selected_sources:
            context_lines.append(self._build_source_context(source, authorization))

        return "\n".join(context_lines)

    def _merge_prompt_with_context(self, prompt: str, application_context: str | None) -> str:
        if not application_context:
            return prompt

        return (
            f"{prompt}\n\n"
            f"{application_context}\n"
            "Responde usando ese dato real de la aplicacion. "
            "No inventes cifras si el contexto dice que no se pudo consultar."
        )

    def _build_source_context(self, source: SourceConfig, authorization: str | None) -> str:
        label = str(source["label"])
        try:
            payload = self._fetch_json(
                base_url=str(source["base_url"]),
                path=str(source["path"]),
                authorization=authorization if source.get("requires_auth") else None,
            )
            return self._summarize_payload(label, str(source["kind"]), payload)
        except httpx.HTTPError as exc:
            return f"- {label}: no se pudo consultar. Error: {exc}"

    def _fetch_json(self, base_url: str, path: str, authorization: str | None = None) -> object:
        url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
        headers = {"Authorization": authorization} if authorization else None
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

        return response.json()

    def _summarize_payload(self, label: str, kind: str, payload: object) -> str:
        items = self._extract_items(payload)
        count = len(items)

        if kind == "reports":
            report_total = self._extract_numeric(payload, "total")
            sales_total = sum(self._number(item.get("totalAmount")) for item in items)
            total_label = report_total if report_total is not None else count
            return (
                f"- {label}: {total_label} reportes registrados; "
                f"monto acumulado aproximado {sales_total:.2f}."
            )

        if kind == "electrobikes":
            stock_total = sum(self._number(item.get("stock")) for item in items)
            available = sum(
                1 for item in items
                if self._normalize_text(str(item.get("estado", ""))) == "disponible"
            )
            return (
                f"- {label}: {count} modelos registrados; "
                f"stock total {stock_total:.0f}; disponibles {available}."
            )

        inventory_value = sum(
            self._number(item.get("price"))
            or self._number(item.get("precio"))
            or self._number(item.get("unitPrice"))
            for item in items
        )
        sample_names = self._sample_item_names(items)
        sample_text = f" Ejemplos: {', '.join(sample_names)}." if sample_names else ""
        return (
            f"- {label}: {count} registros creados; "
            f"valor listado aproximado {inventory_value:.2f}.{sample_text}"
        )

    def _extract_items(self, payload: object) -> list[dict]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("data", "items", "results", "cars", "motorcycles", "motos", "electrobikes", "scooters", "usuarios"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

        return []

    def _extract_numeric(self, payload: object, key: str) -> float | None:
        if isinstance(payload, dict) and key in payload:
            return self._number(payload.get(key))
        return None

    def _number(self, value: object) -> float:
        try:
            if value is None or value == "":
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _sample_item_names(self, items: list[dict]) -> list[str]:
        names: list[str] = []
        for item in items[:3]:
            name = (
                item.get("modelo")
                or item.get("model")
                or item.get("productName")
                or item.get("nombre")
                or item.get("email")
            )
            brand = item.get("marca") or item.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("nombre")
            text = f"{brand or ''} {name or ''}".strip()
            if text:
                names.append(text)
        return names

    def _select_sources(self, normalized_prompt: str) -> list[SourceConfig]:
        sources = self._sources()
        asks_global = any(
            word in normalized_prompt
            for word in (
                "todo", "todos", "toda", "aplicacion", "inventario", "vehiculos",
                "catalogo", "stock", "tienda", "negocio", "resumen", "general",
            )
        )

        selected = [
            source for source in sources
            if any(keyword in normalized_prompt for keyword in source["keywords"])
        ]

        if asks_global:
            selected.extend(
                source for source in sources
                if source["kind"] in {"inventory", "electrobikes", "reports"}
            )

        unique: list[SourceConfig] = []
        seen: set[str] = set()
        for source in selected:
            key = str(source["key"])
            if key not in seen:
                unique.append(source)
                seen.add(key)

        return unique

    def _sources(self) -> list[SourceConfig]:
        return [
            {
                "key": "cars",
                "label": "Carros",
                "kind": "inventory",
                "base_url": settings.cars_api_url,
                "path": "/api/cars",
                "keywords": ("carro", "carros", "auto", "autos", "coche", "coches"),
            },
            {
                "key": "motorcycles",
                "label": "Motos",
                "kind": "inventory",
                "base_url": settings.motorcycles_api_url,
                "path": "/api/motorcycles/",
                "keywords": ("moto", "motos", "motocicleta", "motocicletas"),
            },
            {
                "key": "electrobikes",
                "label": "Electrobikes",
                "kind": "electrobikes",
                "base_url": settings.electrobikes_api_url,
                "path": "/api/electrobikes",
                "keywords": ("electrobike", "electrobikes", "bicicleta", "bicicletas", "electrica", "electricas"),
            },
            {
                "key": "scooters",
                "label": "Scooters",
                "kind": "inventory",
                "base_url": settings.scooters_api_url,
                "path": "/api/scooters",
                "keywords": ("scooter", "scooters", "patineta", "patinetas"),
            },
            {
                "key": "reports",
                "label": "Reportes de ventas",
                "kind": "reports",
                "base_url": settings.reports_api_url,
                "path": "/api/reports",
                "keywords": ("reporte", "reportes", "venta", "ventas", "ingreso", "ingresos", "facturacion"),
            },
            {
                "key": "users",
                "label": "Usuarios",
                "kind": "inventory",
                "base_url": settings.auth_api_url,
                "path": "/qzMotorCenter/auth",
                "requires_auth": True,
                "keywords": ("usuario", "usuarios", "cliente", "clientes", "cuenta", "cuentas"),
            },
        ]

    def _normalize_text(self, value: str) -> str:
        without_accents = "".join(
            char for char in unicodedata.normalize("NFD", value)
            if unicodedata.category(char) != "Mn"
        )
        return without_accents.lower()
