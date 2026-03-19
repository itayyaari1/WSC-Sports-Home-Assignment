from shared.config import SharedBaseSettings


class ConsumerSettings(SharedBaseSettings):
    kafka_group_id: str = "wsc-consumer-group"
    kafka_auto_offset_reset: str = "earliest"
    kafka_poll_timeout: float = 10.0

    s3_bucket: str = "wsc-positions-data"
    s3_endpoint_url: str | None = "http://localhost:4566"
    aws_region: str = "us-east-1"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"

    url_cache_path: str = "url_cache.json"


settings = ConsumerSettings()
