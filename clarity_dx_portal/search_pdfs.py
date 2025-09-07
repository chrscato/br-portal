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
print(f'Searching for PDF files in bucket: {bucket_name}')

# Search in different locations
search_locations = [
    'data/ProviderBills/pdf/',
    'data/ProviderBills/pdf/archive/',
    'data/hcfa_pdf/',
    'data/'
]

for location in search_locations:
    print(f'\n=== Searching in: {location} ===')
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket_name, 
            Prefix=location,
            MaxKeys=10
        )
        
        pdf_files = [obj['Key'] for obj in response.get('Contents', []) if obj['Key'].endswith('.pdf')]
        
        if pdf_files:
            print(f'Found {len(pdf_files)} PDF files:')
            for pdf in pdf_files[:5]:  # Show first 5
                print(f'  - {pdf}')
            if len(pdf_files) > 5:
                print(f'  ... and {len(pdf_files) - 5} more')
        else:
            print('No PDF files found in this location')
            
    except Exception as e:
        print(f'Error searching {location}: {e}')

# Also search for any files containing the bill ID
bill_id = '1815ac4b-1b32-4896-a8a6-eb8b220dabb3'
print(f'\n=== Searching for files containing bill ID: {bill_id} ===')

try:
    response = s3_client.list_objects_v2(
        Bucket=bucket_name,
        MaxKeys=1000
    )
    
    matching_files = [obj['Key'] for obj in response.get('Contents', []) if bill_id in obj['Key']]
    
    if matching_files:
        print(f'Found {len(matching_files)} files containing the bill ID:')
        for file in matching_files:
            print(f'  - {file}')
    else:
        print('No files found containing the bill ID')
        
except Exception as e:
    print(f'Error searching for bill ID: {e}')
