from shared.config import SharedBaseSettings


class ProducerSettings(SharedBaseSettings):
    scrape_timeout_seconds: int = 30
    scrape_retries: int = 3


settings = ProducerSettings()
