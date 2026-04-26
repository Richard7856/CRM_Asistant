from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load .env explicitly — pydantic-settings' built-in dotenv reader
# has issues with iCloud paths containing spaces
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE, override=True)


class Settings(BaseSettings):
    app_name: str = "CRM Agents"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/crm_agents"
    database_echo: bool = False

    # API
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173"]

    # Auth
    api_key_header: str = "X-API-Key"
    jwt_secret_key: str = "CHANGE-ME-in-production-use-openssl-rand-hex-32"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # LLM — used by the agent execution engine to run internal agents
    anthropic_api_key: str = ""


settings = Settings()

# Fail fast in production if JWT secret was not changed from the insecure default
_INSECURE_JWT_DEFAULT = "CHANGE-ME-in-production-use-openssl-rand-hex-32"
if not settings.debug and settings.jwt_secret_key == _INSECURE_JWT_DEFAULT:
    raise RuntimeError(
        "FATAL: JWT_SECRET_KEY is still the default value. "
        "Set a secure secret via environment variable or .env file. "
        "Generate one with: openssl rand -hex 32"
    )
