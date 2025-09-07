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
print(f'Testing S3 connection to bucket: {bucket_name}')

try:
    # Test connection by listing objects
    response = s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=5)
    print('S3 connection successful!')
    print('Sample objects:')
    for obj in response.get('Contents', [])[:3]:
        print(f'  - {obj["Key"]}')
    
    # Test specific PDF search for the bill ID
    bill_id = '1815ac4b-1b32-4896-a8a6-eb8b220dabb3'
    search_locations = [
        'data/ProviderBills/pdf/',
        'data/ProviderBills/pdf/archive/',
        'data/hcfa_pdf/',
        ''
    ]
    
    print(f'\nSearching for PDF with bill ID: {bill_id}')
    for location in search_locations:
        if location:
            key = f'{location}{bill_id}.pdf'
        else:
            key = f'{bill_id}.pdf'
        
        try:
            s3_client.head_object(Bucket=bucket_name, Key=key)
            print(f'  FOUND: {key}')
        except s3_client.exceptions.NoSuchKey:
            print(f'  NOT FOUND: {key}')
        except Exception as e:
            print(f'  ERROR checking {key}: {e}')
            
except Exception as e:
    print(f'S3 connection failed: {e}')
