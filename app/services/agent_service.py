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

        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=prompt,
        )
        db.add(user_message)
        db.flush()

        assistant_text, model_name = self._generate_response(prompt=prompt, conversation=conversation)

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
            return self._generate_ollama_response(prompt=prompt, conversation=conversation)

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
            response = self.groq_client.responses.create(
                model=self.groq_model_name,
                instructions=settings.agent_system_prompt,
                input=prompt,
            )
            return response.output_text, self.groq_model_name
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
        return (
            "Modo desarrollo activo: "
            f"{reason}. "
            f"Recibi el mensaje '{prompt}' en la conversacion {conversation_id}. "
            "La conversacion y los mensajes quedaron guardados correctamente en la base de datos.",
            "local-dev-fallback",
        )
