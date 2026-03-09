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
    google_places_fields: str = Field(
        default="id,displayName,formattedAddress,location,types,googleMapsUri,rating,userRatingCount",
        alias="GOOGLE_PLACES_FIELDS",
    )

    @property
    def logger_level(self) -> int:
        return 10 if self.debug else INFO


settings = Settings()
