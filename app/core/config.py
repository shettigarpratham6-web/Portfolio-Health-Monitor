"""
Portfolio Health Monitor
Core Application Configuration & Settings Management
"""

from enum import Enum
from functools import lru_cache
import json
import logging
from pathlib import Path
import sys
from typing import Any, List, Optional

from pydantic import (
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory of the repository (where .env is located)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"


class Environment(str, Enum):
    """Application deployment environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Supported standard logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ConfigurationError(Exception):
    """Raised when application configuration fails validation or required settings are missing."""
    pass


class Settings(BaseSettings):
    """
    Production-ready application settings managed via Pydantic v2 and pydantic-settings.
    Loads values from environment variables or .env file.
    """

    model_config = SettingsConfigDict(
        env_file=(str(ENV_PATH), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --------------------------------------------------------------------------
    # Application & Runtime
    # --------------------------------------------------------------------------
    PROJECT_NAME: str = Field(
        default="Portfolio Health Monitor",
        description="Human-readable project title",
    )
    VERSION: str = Field(
        default="0.1.0",
        description="SemVer application version",
    )
    API_V1_STR: str = Field(
        default="/api/v1",
        description="Base routing prefix for API v1",
    )
    ENVIRONMENT: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Target deployment environment",
    )
    DEBUG: bool = Field(
        default=False,
        description="Global debug flag (must be False in production)",
    )
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origin URLs",
    )

    # --------------------------------------------------------------------------
    # Security & Tokens
    # --------------------------------------------------------------------------
    SECRET_KEY: SecretStr = Field(
        ...,
        description="Cryptographic secret key for signing tokens and sessions",
    )
    ALGORITHM: str = Field(
        default="HS256",
        description="JWT signature algorithm",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=60 * 24 * 7,  # 7 days
        gt=0,
        description="Access token expiration window in minutes",
    )

    # --------------------------------------------------------------------------
    # Logging
    # --------------------------------------------------------------------------
    LOG_LEVEL: LogLevel = Field(
        default=LogLevel.INFO,
        description="Minimum log level for application output",
    )
    LOG_FORMAT: str = Field(
        default="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        description="Standard logging format string",
    )
    LOG_JSON_FORMAT: bool = Field(
        default=False,
        description="Whether to format logs as structured JSON lines",
    )

    # --------------------------------------------------------------------------
    # Database (PostgreSQL)
    # --------------------------------------------------------------------------
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="Full async PostgreSQL connection string",
    )
    POSTGRES_SERVER: str = Field(
        default="localhost",
        description="PostgreSQL hostname",
    )
    POSTGRES_PORT: int = Field(
        default=5432,
        ge=1,
        le=65535,
        description="PostgreSQL port number",
    )
    POSTGRES_USER: str = Field(
        default="postgres",
        description="PostgreSQL user name",
    )
    POSTGRES_PASSWORD: Optional[SecretStr] = Field(
        default=None,
        description="PostgreSQL user password",
    )
    POSTGRES_DB: str = Field(
        default="agentx",
        description="PostgreSQL database name",
    )
    DB_POOL_SIZE: int = Field(
        default=10,
        ge=1,
        description="SQLAlchemy connection pool size",
    )
    DB_MAX_OVERFLOW: int = Field(
        default=20,
        ge=0,
        description="SQLAlchemy max pool overflow",
    )
    DB_POOL_TIMEOUT: int = Field(
        default=30,
        gt=0,
        description="SQLAlchemy pool checkout timeout in seconds",
    )

    # --------------------------------------------------------------------------
    # LLM Gateway: OpenRouter
    # --------------------------------------------------------------------------
    OPENROUTER_API_KEY: Optional[SecretStr] = Field(
        default=None,
        description="OpenRouter API authentication key",
    )
    OPENROUTER_BASE_URL: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base endpoint",
    )
    OPENROUTER_DEFAULT_MODEL: str = Field(
        default="anthropic/claude-3.5-sonnet",
        description="Primary model identifier for portfolio reasoning",
    )
    OPENROUTER_FALLBACK_MODEL: str = Field(
        default="openai/gpt-4o-mini",
        description="Secondary fallback model identifier",
    )
    LLM_TEMPERATURE: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="LLM generation temperature",
    )
    LLM_MAX_RETRIES: int = Field(
        default=3,
        ge=0,
        description="Max retries for rate limits or transient errors",
    )
    LLM_TIMEOUT_SECONDS: float = Field(
        default=60.0,
        gt=0.0,
        description="LLM HTTP timeout in seconds",
    )

    # --------------------------------------------------------------------------
    # Research: Tavily Search
    # --------------------------------------------------------------------------
    TAVILY_API_KEY: Optional[SecretStr] = Field(
        default=None,
        description="Tavily Search API key for financial research",
    )
    TAVILY_SEARCH_DEPTH: str = Field(
        default="advanced",
        description="Tavily search depth mode (basic or advanced)",
    )
    TAVILY_MAX_RESULTS: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum search results per research query",
    )

    # --------------------------------------------------------------------------
    # Observability: LangSmith
    # --------------------------------------------------------------------------
    LANGCHAIN_TRACING_V2: bool = Field(
        default=False,
        description="Flag to enable LangSmith multi-agent tracing",
    )
    LANGCHAIN_API_KEY: Optional[SecretStr] = Field(
        default=None,
        description="LangSmith API key",
    )
    LANGCHAIN_PROJECT: str = Field(
        default="agentx-portfolio-health",
        description="LangSmith project name for traces",
    )
    LANGCHAIN_ENDPOINT: str = Field(
        default="https://api.smith.langchain.com",
        description="LangSmith ingestion endpoint",
    )

    # --------------------------------------------------------------------------
    # Model Context Protocol (MCP) Server Ports
    # --------------------------------------------------------------------------
    MCP_RESEARCH_SERVER_PORT: int = Field(
        default=8001,
        ge=1024,
        le=65535,
        description="MCP Research Server listening port",
    )
    MCP_DATABASE_SERVER_PORT: int = Field(
        default=8002,
        ge=1024,
        le=65535,
        description="MCP Database Server listening port",
    )
    MCP_ANALYSIS_SERVER_PORT: int = Field(
        default=8003,
        ge=1024,
        le=65535,
        description="MCP Analysis Server listening port",
    )

    # --------------------------------------------------------------------------
    # Field Validators & Helpers
    # --------------------------------------------------------------------------
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        """Parse comma-separated strings or JSON arrays into a list of origin strings."""
        if isinstance(v, str):
            trimmed = v.strip()
            if trimmed.startswith("[") and trimmed.endswith("]"):
                try:
                    parsed = json.loads(trimmed)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [origin.strip() for origin in trimmed.split(",") if origin.strip()]
        if isinstance(v, (list, tuple)):
            return [str(item).strip() for item in v if str(item).strip()]
        return []

    @property
    def async_database_url(self) -> str:
        """
        Produce a valid async SQLAlchemy connection string (postgresql+asyncpg://).
        Honors explicit DATABASE_URL if present, otherwise constructs from components.
        """
        if self.DATABASE_URL:
            url = str(self.DATABASE_URL)
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url

        password_part = ""
        if self.POSTGRES_PASSWORD:
            pwd = self.POSTGRES_PASSWORD.get_secret_value()
            if pwd:
                password_part = f":{pwd}"

        auth = f"{self.POSTGRES_USER}{password_part}@"
        return f"postgresql+asyncpg://{auth}{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # --------------------------------------------------------------------------
    # Model Cross-Field & Production Invariants Validation
    # --------------------------------------------------------------------------
    @model_validator(mode="after")
    def validate_production_invariants(self) -> "Settings":
        """
        Enforce strict safety checks and cross-field consistency.
        Specifically verifies production requirements and interdependent flags.
        """
        errors: List[str] = []

        # Production safety enforcement
        if self.ENVIRONMENT == Environment.PRODUCTION:
            if self.DEBUG:
                errors.append("DEBUG mode must be set to False in production environment.")

            secret = self.SECRET_KEY.get_secret_value()
            insecure_placeholders = {
                "secret", "changeme", "change-me", "your-secret-key",
                "default", "insecure", "agentx-secret", "replace-with-a-secure-random-secret-key-min-32-chars",
            }
            if len(secret) < 32 or secret.lower() in insecure_placeholders:
                errors.append(
                    "SECRET_KEY in production must be a secure random string of at least 32 characters."
                )

            if not self.OPENROUTER_API_KEY or not self.OPENROUTER_API_KEY.get_secret_value():
                errors.append("OPENROUTER_API_KEY is required in production environment.")

            has_db_pwd = bool(self.POSTGRES_PASSWORD and self.POSTGRES_PASSWORD.get_secret_value())
            if not self.DATABASE_URL and not has_db_pwd:
                errors.append(
                    "PostgreSQL password (POSTGRES_PASSWORD) or full DATABASE_URL is required in production."
                )

        # Observability tracing checks
        if self.LANGCHAIN_TRACING_V2:
            if not self.LANGCHAIN_API_KEY or not self.LANGCHAIN_API_KEY.get_secret_value():
                errors.append(
                    "LANGCHAIN_API_KEY must be provided whenever LANGCHAIN_TRACING_V2 is enabled."
                )

        if errors:
            raise ValueError("\n".join(errors))

        return self


Settings.model_rebuild()


# ------------------------------------------------------------------------------
# Structured JSON Formatter for Production Logging
# ------------------------------------------------------------------------------
class JsonLogFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


# ------------------------------------------------------------------------------
# Application Logging Setup
# ------------------------------------------------------------------------------
def setup_logging(settings: Optional[Settings] = None) -> logging.Logger:
    """
    Configures application-wide logging with appropriate formatting and log levels.
    Silences noisy third-party libraries while retaining critical diagnostics.
    """
    if settings is None:
        try:
            settings = get_settings()
        except Exception:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
                stream=sys.stdout,
                force=True,
            )
            fallback_logger = logging.getLogger("agentx")
            fallback_logger.warning("Application settings unavailable; running with fallback logger.")
            return fallback_logger

    log_level = getattr(logging, settings.LOG_LEVEL.value, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    if settings.LOG_JSON_FORMAT:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter(settings.LOG_FORMAT))

    root_logger.addHandler(handler)

    # Suppress verbose loggers from dependencies
    noisy_loggers = [
        "httpx",
        "httpcore",
        "urllib3",
        "uvicorn.access",
        "asyncio",
    ]
    for noisy in noisy_loggers:
        logging.getLogger(noisy).setLevel(max(log_level, logging.WARNING))

    app_logger = logging.getLogger("agentx")
    app_logger.setLevel(log_level)
    app_logger.debug(
        "Logging configured | level=%s | json=%s | env=%s",
        settings.LOG_LEVEL.value,
        settings.LOG_JSON_FORMAT,
        settings.ENVIRONMENT.value,
    )
    return app_logger


# ------------------------------------------------------------------------------
# Configuration Loader with Meaningful Startup Diagnostics
# ------------------------------------------------------------------------------
def load_settings() -> Settings:
    """
    Instantiate and validate application Settings.
    Formats ValidationError and ValueError into clear, actionable startup errors.
    """
    try:
        return Settings()
    except ValidationError as exc:
        missing_fields: List[str] = []
        invalid_fields: List[str] = []

        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", []))
            msg = err.get("msg", "Validation error")
            err_type = err.get("type", "")

            if "missing" in err_type:
                missing_fields.append(f"  • {loc.upper()} -> Required setting is missing.")
            else:
                invalid_fields.append(f"  • {loc} -> {msg}")

        lines = [
            "",
            "=" * 70,
            " [STARTUP CONFIGURATION ERROR] Missing or Invalid Settings",
            "=" * 70,
        ]

        if missing_fields:
            lines.append("\nMissing required environment variables:")
            lines.extend(missing_fields)

        if invalid_fields:
            lines.append("\nConfiguration validation failures:")
            lines.extend(invalid_fields)

        lines.extend([
            "",
            "Action Required:",
            f"  1. Ensure a valid .env file exists at '{ENV_PATH}'",
            "  2. Compare your .env against .env.example for required keys",
            "  3. Set required environment variables before starting the application",
            "=" * 70,
            "",
        ])

        formatted_message = "\n".join(lines)
        raise ConfigurationError(formatted_message) from exc
    except Exception as exc:
        raise ConfigurationError(
            f"\n[STARTUP CONFIGURATION ERROR] Unexpected failure loading configuration: {exc}"
        ) from exc


@lru_cache()
def get_settings() -> Settings:
    """
    Returns cached application Settings singleton.
    Use this function throughout the application to access validated configuration.
    """
    return load_settings()

