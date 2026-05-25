from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ai-agent-microservice"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/ai_agent_db"
    llm_provider: str = "groq"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    auth_api_url: str = "https://qzmotorcenter-api.onrender.com"
    cars_api_url: str = "https://qzmotorcenter-cars-api.onrender.com"
    motorcycles_api_url: str = "https://qzmotorcenter-motorcycles-api.onrender.com"
    electrobikes_api_url: str = "https://qzmotorcenter-electrobike-api.onrender.com"
    scooters_api_url: str = "https://qzmotorcenter-scooter-api.onrender.com"
    reports_api_url: str = "https://qzmotorcenterreports-1.onrender.com"
    agent_system_prompt: str = (
        "Eres un agente de IA empresarial. Responde con claridad, criterio y enfoque accionable."
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
