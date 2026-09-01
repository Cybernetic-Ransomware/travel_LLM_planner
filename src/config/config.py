from logging import INFO

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("docker/.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    debug: bool = Field(default=False, alias="DEBUG")
    mongo_uri: str = Field(default="mongodb://localhost:27017", alias="MONGO_URI")
    mongo_db: str = Field(default="travel_planner", alias="MONGO_DB")
    mongo_pool_size: int = Field(default=10, alias="MONGO_POOL_SIZE")
    log_dir: str = Field(default="log", alias="LOG_DIR")
    google_places_api_key: str = Field(default="", alias="GOOGLE_PLACES_API_KEY")
    google_routes_api_key: str = Field(default="", alias="GOOGLE_ROUTES_API_KEY")
    google_places_fields: str = Field(
        default="id,displayName,formattedAddress,location,types,googleMapsUri,rating,userRatingCount,regularOpeningHours,currentOpeningHours",
        alias="GOOGLE_PLACES_FIELDS",
    )

    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    llm_model_name: str = Field(default="gpt-4o-mini", alias="LLM_MODEL_NAME")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_project: str = Field(default="travel-planner", alias="LANGSMITH_PROJECT")
    checkpoint_ttl_days: int = Field(default=30, alias="CHECKPOINT_TTL_DAYS")

    # Persisted trips + revision history (ADR-21). A file: URL selects the stdlib sqlite3
    # backend; a libsql:// URL selects the libsql driver (production).
    turso_database_url: str = Field(default="", alias="TURSO_DATABASE_URL")
    turso_auth_token: str = Field(default="", alias="TURSO_AUTH_TOKEN")
    # Require the Turso migration-complete marker at startup. True in prod; set False only
    # for local hacking against a hand-seeded Turso DB.
    trips_require_migration_marker: bool = Field(default=True, alias="TRIPS_REQUIRE_MIGRATION_MARKER")

    cors_allow_origins: str = Field(default="http://localhost:4321,http://127.0.0.1:4321", alias="CORS_ALLOW_ORIGINS")

    auth_enabled: bool = Field(default=False, alias="AUTH_ENABLED")
    auth0_domain: str = Field(default="", alias="AUTH0_DOMAIN")
    auth0_audience: str = Field(default="", alias="AUTH0_AUDIENCE")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def auth0_issuer(self) -> str:
        return f"https://{self.auth0_domain}/"

    @property
    def auth_active(self) -> bool:
        return self.auth_enabled and bool(self.auth0_domain) and bool(self.auth0_audience)

    @property
    def logger_level(self) -> int:
        return 10 if self.debug else INFO


settings = Settings()
