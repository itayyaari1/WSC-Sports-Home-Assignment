from pydantic_settings import BaseSettings


class ConsumerSettings(BaseSettings):
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "wsc-positions"
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_group_id: str = "wsc-consumer-group"
    kafka_auto_offset_reset: str = "earliest"
    kafka_poll_timeout: float = 10.0

    s3_bucket: str = "wsc-positions-data"
    s3_endpoint_url: str | None = "http://localhost:4566"
    aws_region: str = "us-east-1"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"

    careers_url: str = "https://wsc-sports.com/Careers"
    url_cache_path: str = "url_cache.json"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = ConsumerSettings()
