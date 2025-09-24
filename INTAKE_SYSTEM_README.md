# PDF Intake System

This document describes the new PDF intake system that allows users to upload large PDF batches, automatically split them into individual pages, and create ProviderBill records for each page.

## Overview

The intake system consists of:
1. **Backend Job**: `jobs/pdf_intake_split.py` - Handles PDF splitting and S3 upload
2. **Django Views**: New views for intake queue and PDF upload
3. **Database Model**: Updated ProviderBill model with 'SCANNED' status
4. **UI Components**: Intake queue page with upload functionality

## Features

- **PDF Upload**: Users can upload multi-page PDF files through the web interface
- **Automatic Splitting**: Each page is automatically extracted as a separate PDF
- **S3 Storage**: Individual page PDFs are uploaded to S3 in the standard location
- **Database Records**: Each page creates a ProviderBill record with:
  - Unique ID (UUID)
  - Status: 'SCANNED'
  - Source file: Original filename + page number
  - Uploaded by: Current logged-in user
  - Created at: Current timestamp (EST)

## File Structure

```
├── jobs/
│   └── pdf_intake_split.py          # Main PDF processing job
├── clarity_dx_portal/
│   └── billing/
│       ├── models.py                 # Updated with SCANNED status
│       ├── views.py                  # New intake views
│       ├── urls.py                   # New intake URLs
│       └── templates/billing/
│           ├── intake_queue.html     # Intake queue UI
│           └── dashboard.html        # Updated with intake queue
├── test_intake_system.py            # Test script
└── INTAKE_SYSTEM_README.md          # This documentation
```

## Usage

### Web Interface

1. Navigate to the **Intake Queue** from the dashboard
2. Click **"Upload PDF Batch"** button
3. Select a multi-page PDF file
4. Click **"Upload & Process"**
5. The system will:
   - Split the PDF into individual pages
   - Upload each page to S3
   - Create ProviderBill records
   - Show success message with count of created records

### Command Line

```bash
# Process a PDF file directly
python jobs/pdf_intake_split.py /path/to/file.pdf username

# Run the test script
python test_intake_system.py
```

## Database Schema

The ProviderBill model has been updated to include:

```python
STATUS_CHOICES = [
    # ... existing statuses ...
    ('SCANNED', 'Scanned'),  # New status for intake
]
```

## S3 Storage

PDFs are stored in S3 with the following structure:
- **Location**: `data/ProviderBills/pdf/`
- **Filename**: `{unique_id}.pdf` (where unique_id is a UUID)
- **Example**: `data/ProviderBills/pdf/a1b2c3d4e5f6.pdf`

## Configuration

The system uses existing S3 configuration from Django settings:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_STORAGE_BUCKET_NAME`
- `AWS_S3_REGION_NAME`

## Workflow

1. **Upload**: User uploads PDF through web interface
2. **Split**: System splits PDF into individual pages
3. **Upload**: Each page is uploaded to S3
4. **Database**: ProviderBill record created for each page
5. **Queue**: Bills appear in Intake Queue with 'SCANNED' status
6. **Processing**: Bills can be moved to other queues (Validation, Mapping, etc.)

## Error Handling

- File validation (PDF format only)
- S3 upload error handling
- Database transaction rollback on errors
- User-friendly error messages
- Comprehensive logging

## Testing

Run the test script to verify the system:

```bash
python test_intake_system.py
```

The test script will:
1. Test database connection
2. Test S3 connection
3. Process a test PDF (if available)
4. Verify created records

## Security

- File type validation (PDF only)
- User authentication required
- S3 credentials from environment variables
- Database transactions for data integrity

## Performance

- Temporary file cleanup
- Efficient PDF processing with PyPDF2
- Batch database operations
- S3 upload optimization

## Troubleshooting

### Common Issues

1. **S3 Connection Failed**
   - Check AWS credentials in .env file
   - Verify bucket name and region

2. **PDF Processing Error**
   - Ensure file is a valid PDF
   - Check file permissions

3. **Database Error**
   - Verify monolith.db is accessible
   - Check database permissions

### Logs

Check Django logs for detailed error information:
```bash
# Django development server logs
python manage.py runserver

# Or check application logs
tail -f /path/to/django/logs
```

## Future Enhancements

- Batch processing progress indicators
- Email notifications on completion
- PDF metadata extraction
- Duplicate detection
- Bulk status updates
- Advanced file validation
