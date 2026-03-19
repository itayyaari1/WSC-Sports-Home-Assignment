from pydantic_settings import BaseSettings, SettingsConfigDict


class SharedBaseSettings(BaseSettings):
    """Base settings shared by all services."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "wsc-positions"
    kafka_security_protocol: str = "PLAINTEXT"

    careers_url: str = "https://wsc-sports.com/Careers"
