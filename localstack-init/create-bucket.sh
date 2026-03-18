#!/bin/bash
echo "Creating S3 bucket..."
awslocal s3 mb s3://wsc-positions-data
echo "Bucket created successfully"
