from urllib.parse import urljoin
import re
import unicodedata

import httpx
from openai import APIConnectionError, APIError, AuthenticationError, OpenAI, RateLimitError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.conversation import Conversation, Message


class AgentService:
    def __init__(self) -> None:
        self.provider = settings.llm_provider.strip().lower()
        self.groq_model_name = settings.groq_model
        self.groq_client = (
            OpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)
            if settings.groq_api_key
            else None
        )

    def run(self, db: Session, prompt: str, conversation_id: str | None, title: str) -> dict:
        conversation = self._get_or_create_conversation(db, conversation_id, title)
        application_context = self._build_application_context(prompt)
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
        motorcycles_count = re.search(r"hay (\d+) motos registradas", prompt)
        if motorcycles_count:
            return (
                f"Actualmente hay {motorcycles_count.group(1)} motos registradas en la tienda.",
                "local-dev-fallback",
            )

        if "no pude consultar el microservicio de motos" in prompt:
            return (
                "No pude consultar el microservicio de motos en este momento. "
                "Intenta nuevamente cuando el servicio este disponible.",
                "local-dev-fallback",
            )

        return (
            "Modo desarrollo activo: "
            f"{reason}. "
            f"Recibi el mensaje '{prompt}' en la conversacion {conversation_id}. "
            "La conversacion y los mensajes quedaron guardados correctamente en la base de datos.",
            "local-dev-fallback",
        )

    def _build_application_context(self, prompt: str) -> str | None:
        normalized_prompt = self._normalize_text(prompt)
        asks_about_motorcycles = any(
            word in normalized_prompt for word in ("moto", "motos", "motocicleta", "motocicletas")
        )
        asks_for_count = any(
            word in normalized_prompt for word in ("cuantas", "cuantos", "cantidad", "total", "hay")
        )

        if not asks_about_motorcycles or not asks_for_count:
            return None

        try:
            motorcycles_count = self._fetch_collection_count(
                base_url=settings.motorcycles_api_url,
                path="/api/motorcycles/",
            )
        except httpx.HTTPError as exc:
            return (
                "Contexto del sistema: el usuario pregunta por motos registradas, "
                f"pero no pude consultar el microservicio de motos. Error: {exc}"
            )

        return (
            "Contexto del sistema: el dato real actual indica que hay "
            f"{motorcycles_count} motos registradas en la tienda."
        )

    def _merge_prompt_with_context(self, prompt: str, application_context: str | None) -> str:
        if not application_context:
            return prompt

        return (
            f"{prompt}\n\n"
            f"{application_context}\n"
            "Responde usando ese dato real de la aplicacion. "
            "No inventes cifras si el contexto dice que no se pudo consultar."
        )

    def _fetch_collection_count(self, base_url: str, path: str) -> int:
        url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

        payload = response.json()
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            for key in ("data", "items", "results", "motorcycles", "motos"):
                value = payload.get(key)
                if isinstance(value, list):
                    return len(value)

        raise httpx.HTTPError("La respuesta del microservicio de motos no es una lista.")

    def _normalize_text(self, value: str) -> str:
        without_accents = "".join(
            char for char in unicodedata.normalize("NFD", value)
            if unicodedata.category(char) != "Mn"
        )
        return without_accents.lower()
