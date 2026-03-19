from datetime import datetime, timezone

import boto3
import pandas as pd
import pyarrow as pa
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from shared.logger import get_logger
from shared.parquet_io import write_parquet_bytes
from src.config import settings

logger = get_logger(__name__)

ENRICHED_SCHEMA = pa.schema([
    ("index", pa.int32()),
    ("title", pa.string()),
    ("category", pa.string()),
    ("seniority_level", pa.string()),
    ("years_of_experience", pa.int32()),
    ("skills_count", pa.int32()),
    ("complexity_score", pa.int32()),
])


def create_s3_client():
    """Create an S3 client, using endpoint URL for local development."""
    kwargs = {
        "service_name": "s3",
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    return boto3.client(**kwargs)


def generate_s3_key() -> str:
    """Generate a date-partitioned S3 key for the parquet file."""
    now = datetime.now(timezone.utc)
    return (
        f"positions/year={now.year}/month={now.month:02d}/day={now.day:02d}/"
        f"positions_{now.strftime('%Y%m%d%H%M%S')}.parquet"
    )


def df_to_parquet_bytes(df: pd.DataFrame) -> bytes:
    """Serialize enriched DataFrame to parquet bytes."""
    table = pa.Table.from_pandas(df, schema=ENRICHED_SCHEMA, preserve_index=False)
    return write_parquet_bytes(table)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(ClientError),
    before_sleep=lambda retry_state: logger.warning(
        "S3 upload attempt %d failed, retrying...", retry_state.attempt_number
    ),
)
def upload_to_s3(df: pd.DataFrame) -> str:
    """Upload enriched DataFrame as parquet to S3.

    Returns:
        The S3 key where the file was uploaded.
    """
    s3_client = create_s3_client()
    parquet_bytes = df_to_parquet_bytes(df)
    s3_key = generate_s3_key()

    s3_client.put_object(
        Bucket=settings.s3_bucket,
        Key=s3_key,
        Body=parquet_bytes,
        ContentType="application/octet-stream",
    )

    logger.info(
        "Uploaded enriched parquet to s3://%s/%s (%d bytes)",
        settings.s3_bucket,
        s3_key,
        len(parquet_bytes),
    )
    return s3_key
