from pydantic_settings import BaseSettings, SettingsConfigDict


class ProducerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    careers_url: str = "https://wsc-sports.com/Careers"
    scrape_timeout_seconds: int = 30
    scrape_retries: int = 3

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "wsc-positions"
    kafka_security_protocol: str = "PLAINTEXT"


settings = ProducerSettings()
