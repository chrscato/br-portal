"""
Django management command to process scanned bills through LLM extraction
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import os
import sys
import django

class Command(BaseCommand):
    help = 'Process all bills with SCANNED status through LLM extraction'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of bills to process',
        )

    def handle(self, *args, **options):
        # Add the jobs directory to the Python path
        jobs_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'jobs')
        sys.path.insert(0, jobs_dir)
        
        # Import and run the processor
        from intake_scrape_django import process_scanned_bills
        
        limit = options.get('limit')
        
        self.stdout.write(
            self.style.SUCCESS('Starting processing of scanned bills...')
        )
        
        try:
            process_scanned_bills(limit=limit)
            self.stdout.write(
                self.style.SUCCESS('Processing completed successfully!')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during processing: {str(e)}')
            )
            raise
