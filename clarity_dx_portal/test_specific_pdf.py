import os
from dotenv import load_dotenv
import boto3

# Load environment variables
load_dotenv()

# Test S3 connection
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_S3_REGION_NAME')
)

bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME')

# Test with a bill ID that we know has a PDF
test_bill_id = '304d9e99-d27c-4419-88fb-398a88b1891a'  # From the search results

print(f'Testing PDF retrieval for bill ID: {test_bill_id}')

# Test the exact same logic as the Django app
search_locations = [
    'data/ProviderBills/pdf/',
    'data/ProviderBills/pdf/archive/',
    'data/hcfa_pdf/',
    ''
]

extensions = ['.pdf', '.PDF']

for location in search_locations:
    for ext in extensions:
        possible_keys = [
            f"{location}{test_bill_id}{ext}",
            f"{location}{test_bill_id}_{ext}",
            f"{location}{test_bill_id}-{ext}",
            f"{location}{test_bill_id}.{ext}",
        ]
        
        for key in possible_keys:
            try:
                s3_client.head_object(Bucket=bucket_name, Key=key)
                print(f'  FOUND: {key}')
                
                # Generate pre-signed URL like the Django app does
                pre_signed_url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': bucket_name,
                        'Key': key,
                        'ResponseContentType': 'application/pdf',
                        'ResponseContentDisposition': 'inline; filename="' + key.split('/')[-1] + '"'
                    },
                    ExpiresIn=3600
                )
                print(f'  Pre-signed URL: {pre_signed_url}')
                break
                
            except s3_client.exceptions.NoSuchKey:
                print(f'  NOT FOUND: {key}')
            except Exception as e:
                print(f'  ERROR checking {key}: {e}')

print('No PDF found for this bill ID')
