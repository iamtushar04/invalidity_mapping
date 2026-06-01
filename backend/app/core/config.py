from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI-Assisted Patent Invalidity Analysis Tool"
    API_V1_STR: str = "/api"

    # Security
    SECRET_KEY: str = Field(
        default="supersecretjwtkeythatshouldbechangedinproduction",
        validation_alias="SECRET_KEY"
    )

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    AUTH_URL: str = Field(
        default="",
        validation_alias="AUTH_URL"
    )

    PATENT_API_BASE_URL: str = Field(
        default="",
        validation_alias="PATENT_API_BASE_URL"
    )

    # Database
    DATABASE_URL: str = Field(
        default="",
        validation_alias="DATABASE_URL"
    )

    # OpenAI APIs
    OPENAI_API_KEY: str = Field(
        default="",
        validation_alias="OPENAI_API_KEY"
    )


    LLM_MODEL_ROUTINE: str = Field(
    default="gpt-4.1-mini",  # fast and cheap
    validation_alias="LLM_MODEL_ROUTINE"
    )

    LLM_MODEL_REASONING: str = Field(
    default="gpt-4.1",  # for complex reasoning tasks
    validation_alias="LLM_MODEL_REASONING"
    )

    # Qdrant configuration
    QDRANT_HOST: str = Field(
        default="localhost",
        validation_alias="QDRANT_HOST"
    )
    QDRANT_PORT: int = Field(
        default=6333,
        validation_alias="QDRANT_PORT"
    )
    QDRANT_API_KEY: str = Field(
        default="",
        validation_alias="QDRANT_API_KEY"
    )

    # Redis configuration
    REDIS_URL: str = Field(
        default="",
        validation_alias="REDIS_URL"
    )

    # Token Budget
    MAX_TOKENS_PER_CALL: int = 16000
    SESSION_TOKEN_BUDGET: int = 500000

    # Patent APIs
    GOOGLE_PATENTS_API_KEY: str = Field(
        default="",
        validation_alias="GOOGLE_PATENTS_API_KEY"
    )

    LENS_API_KEY: str = Field(
        default="",
        validation_alias="LENS_API_KEY"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()