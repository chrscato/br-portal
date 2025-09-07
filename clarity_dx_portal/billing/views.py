"""
Views for the Clarity Dx Bill Review Portal
"""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from django.core.serializers.json import DjangoJSONEncoder
from django.core.paginator import Paginator
from datetime import datetime
import json
from .models import ProviderBill, BillLineItem, Order, OrderLineItem, Provider, PPO, OTA
from .s3_utils import s3_pdf_service


def format_dos_date(dos_string):
    """Format DOS date string to a consistent format"""
    if not dos_string or dos_string.strip() == '':
        return None
    
    dos_string = dos_string.strip()
    
    # Common date formats to try
    date_formats = [
        '%m/%d/%Y',  # MM/DD/YYYY
        '%m/%d/%y',  # MM/DD/YY
        '%Y-%m-%d',  # YYYY-MM-DD
        '%m-%d-%Y',  # MM-DD-YYYY
        '%m-%d-%y',  # MM-DD-YY
        '%d/%m/%Y',  # DD/MM/YYYY
        '%d/%m/%y',  # DD/MM/YY
        '%d-%m-%Y',  # DD-MM-YYYY
        '%d-%m-%y',  # DD-MM-YY
    ]
    
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(dos_string, fmt).date()
            return parsed_date.strftime('%m/%d/%Y')  # Return in consistent format
        except ValueError:
            continue
    
    # If no format matches, return the original string
    return dos_string


def get_unique_dos_dates(line_items):
    """Get unique, formatted DOS dates from line items"""
    dos_dates = []
    for line_item in line_items:
        if line_item.dos:
            formatted_date = format_dos_date(line_item.dos)
            if formatted_date and formatted_date not in dos_dates:
                dos_dates.append(formatted_date)
    return dos_dates


def add_date_search_to_query(order_query, dos_date):
    """Add date search logic to order query"""
    if dos_date:
        try:
            # Parse the input date - try multiple formats
            target_date = None
            input_formats = ['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y', '%m-%d-%y']
            
            for fmt in input_formats:
                try:
                    target_date = datetime.strptime(dos_date, fmt).date()
                    break
                except ValueError:
                    continue
            
            if target_date:
                # Calculate date range (60 days before and after)
                start_date = target_date - timedelta(days=60)
                end_date = target_date + timedelta(days=60)
                
                # Try different date formats that might be in the DOS field
                date_formats = [
                    '%m/%d/%y',  # MM/DD/YY
                    '%m/%d/%Y',  # MM/DD/YYYY
                    '%Y-%m-%d',  # YYYY-MM-DD
                    '%m-%d-%y',  # MM-DD-YY
                    '%m-%d-%Y',  # MM-DD-YYYY
                ]
                
                # Build date range queries for different formats
                date_queries = []
                for fmt in date_formats:
                    start_str = start_date.strftime(fmt)
                    end_str = end_date.strftime(fmt)
                    date_queries.append(
                        Q(orderlineitem__dos__gte=start_str) & Q(orderlineitem__dos__lte=end_str)
                    )
                
                # Combine all date format queries with OR
                if date_queries:
                    combined_date_query = date_queries[0]
                    for query in date_queries[1:]:
                        combined_date_query |= query
                    order_query &= combined_date_query
            
        except ValueError:
            # Invalid date format
            pass
    
    return order_query


def landing_page(request):
    """Landing page with login form"""
    if request.user.is_authenticated:
        return redirect('billing:dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('billing:dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'billing/landing.html')


@login_required
def dashboard(request):
    """High-level dashboard showing bill status distributions"""
    
    # Get unpaid bills (bill_paid != "Y")
    unpaid_bills = ProviderBill.objects.exclude(bill_paid='Y')
    
    # Status distribution for unpaid bills
    unpaid_status_dist = list(unpaid_bills.values('status').annotate(count=Count('id')).order_by('-count'))
    
    # Status distribution for paid bills
    paid_bills = ProviderBill.objects.filter(bill_paid='Y')
    paid_status_dist = list(paid_bills.values('status').annotate(count=Count('id')).order_by('-count'))
    
    # Queue counts for the 5 core views
    validation_count = ProviderBill.objects.filter(status='INVALID').count()
    mapping_count = ProviderBill.objects.filter(status__in=['UNMAPPED', 'VALID']).count()
    correction_count = ProviderBill.objects.filter(status__in=['REVIEW_FLAG', 'FLAGGED']).count()
    rate_correction_count = ProviderBill.objects.filter(action__in=['review_rate', 'review_rates']).count()
    ready_to_pay_count = ProviderBill.objects.filter(
        status='REVIEWED',
        action='apply_rate'
    ).exclude(
        bill_paid='Y'
    ).count()
    
    context = {
        'unpaid_bills_count': unpaid_bills.count(),
        'paid_bills_count': paid_bills.count(),
        'unpaid_status_dist': unpaid_status_dist,
        'paid_status_dist': paid_status_dist,
        'validation_count': validation_count,
        'mapping_count': mapping_count,
        'correction_count': correction_count,
        'rate_correction_count': rate_correction_count,
        'ready_to_pay_count': ready_to_pay_count,
    }
    
    return render(request, 'billing/dashboard.html', context)


@login_required
def validation_queue(request):
    """Validation queue - status = 'INVALID'"""
    bills = ProviderBill.objects.filter(status='INVALID').order_by('-created_at')
    
    # Add validation errors to each bill
    bills_with_errors = []
    for bill in bills:
        validation_errors = bill.get_validation_errors()
        bills_with_errors.append({
            'bill': bill,
            'validation_errors': validation_errors
        })
    
    context = {
        'bills': bills,
        'bills_with_errors': bills_with_errors,
        'queue_type': 'Validation',
        'status_filter': 'INVALID',
    }
    
    return render(request, 'billing/queue.html', context)


@login_required
def mapping_queue(request):
    """Mapping queue - status = 'UNMAPPED' with search functionality"""
    from datetime import datetime, timedelta
    from django.db.models import Q
    
    # Get search parameters
    first_name = request.GET.get('first_name', '').strip()
    last_name = request.GET.get('last_name', '').strip()
    dos_date = request.GET.get('dos_date', '').strip()
    
    # Start with unmapped and valid bills
    bills = ProviderBill.objects.filter(status__in=['UNMAPPED', 'VALID']).order_by('-created_at')
    
    # Search results for mapping
    search_results = []
    
    if first_name or last_name or dos_date:
        # Build query for orders table
        order_query = Q()
        
        if first_name:
            # Search in patient first name with LIKE pattern
            order_query &= Q(patient_first_name__icontains=first_name)
        
        if last_name:
            # Search in patient last name with LIKE pattern
            order_query &= Q(patient_last_name__icontains=last_name)
        
        order_query = add_date_search_to_query(order_query, dos_date)
        
        # Get matching orders with their line items
        if order_query:
            orders = Order.objects.filter(order_query).distinct()
            search_results = []
            
            for order in orders:
                # Get line items for this order
                line_items = OrderLineItem.objects.filter(order=order)
                
                if line_items.exists():
                    # Group line items by order and consolidate
                    patient_name = f"{order.patient_first_name or ''} {order.patient_last_name or ''}".strip()
                    
                    # Collect all CPT codes and descriptions
                    cpt_codes = []
                    descriptions = []
                    dos_dates = []
                    
                    for line_item in line_items:
                        if line_item.cpt:
                            cpt_codes.append(line_item.cpt)
                        if line_item.description:
                            descriptions.append(line_item.description)
                        if line_item.dos:
                            formatted_date = format_dos_date(line_item.dos)
                            if formatted_date and formatted_date not in dos_dates:
                                dos_dates.append(formatted_date)
                    
                    # Get provider billing name
                    provider_billing_name = 'N/A'
                    if order.provider_id:
                        try:
                            provider = Provider.objects.get(primary_key=order.provider_id)
                            provider_billing_name = provider.name or 'N/A'
                        except Provider.DoesNotExist:
                            pass
                    
                    # Create consolidated result
                    search_results.append({
                        'order': order,
                        'patient_name': patient_name,
                            'patient_first_name': order.patient_last_name,
                            'patient_last_name': order.patient_first_name,
                        'cpt_codes': ', '.join(cpt_codes) if cpt_codes else 'N/A',
                        'cpt_list': cpt_codes,  # For individual display if needed
                        'descriptions': ', '.join(descriptions) if descriptions else 'N/A',
                        'dos': ', '.join(dos_dates) if dos_dates else '-',  # Already unique and formatted
                        'order_id': order.order_id,
                        'line_item_count': line_items.count(),
                        'provider_billing_name': provider_billing_name,
                    })
    
    # Paginate search results
    paginator = Paginator(search_results, 20)  # Show 20 results per page
    page_number = request.GET.get('page')
    search_results_page = paginator.get_page(page_number)
    
    # Add validation errors to each bill (same as validation queue)
    bills_with_errors = []
    for bill in bills:
        validation_errors = bill.get_validation_errors()
        bills_with_errors.append({
            'bill': bill,
            'validation_errors': validation_errors
        })
    
    context = {
        'bills': bills,
        'bills_with_errors': bills_with_errors,
        'search_results': search_results_page,
        'queue_type': 'Mapping',
        'status_filter': 'UNMAPPED',
        'first_name': first_name,
        'last_name': last_name,
        'dos_date': dos_date,
    }
    
    return render(request, 'billing/mapping_queue.html', context)


@login_required
def correction_queue(request):
    """Correction queue - status in ('REVIEW_FLAG', 'FLAGGED')"""
    bills = ProviderBill.objects.filter(status__in=['REVIEW_FLAG', 'FLAGGED']).order_by('-created_at')
    
    # Add validation errors to each bill (same as validation queue)
    bills_with_errors = []
    for bill in bills:
        validation_errors = bill.get_validation_errors()
        bills_with_errors.append({
            'bill': bill,
            'validation_errors': validation_errors
        })
    
    context = {
        'bills': bills,
        'bills_with_errors': bills_with_errors,
        'queue_type': 'Correction',
        'status_filter': 'REVIEW_FLAG,FLAGGED',
    }
    
    return render(request, 'billing/queue.html', context)


@login_required
def rate_correction_queue(request):
    """Rate Correction queue - action in ('review_rate', 'review_rates')"""
    bills = ProviderBill.objects.filter(action__in=['review_rate', 'review_rates']).order_by('-created_at')
    
    # Add validation errors to each bill (same as validation queue)
    bills_with_errors = []
    for bill in bills:
        validation_errors = bill.get_validation_errors()
        bills_with_errors.append({
            'bill': bill,
            'validation_errors': validation_errors
        })
    
    context = {
        'bills': bills,
        'bills_with_errors': bills_with_errors,
        'queue_type': 'Rate Correction',
        'status_filter': 'review_rate,review_rates',
    }
    
    return render(request, 'billing/queue.html', context)


@login_required
def ready_to_pay_queue(request):
    """Ready to Pay queue - status = 'REVIEWED', action = 'apply_rate', bill_paid != 'Y'"""
    bills = ProviderBill.objects.filter(
        status='REVIEWED',
        action='apply_rate'
    ).exclude(
        bill_paid='Y'
    ).order_by('-created_at')
    
    # Add validation errors to each bill (same as other queues)
    bills_with_errors = []
    for bill in bills:
        validation_errors = bill.get_validation_errors()
        bills_with_errors.append({
            'bill': bill,
            'validation_errors': validation_errors
        })
    
    context = {
        'bills': bills,
        'bills_with_errors': bills_with_errors,
        'queue_type': 'Ready to Pay',
        'status_filter': 'REVIEWED',
        'action_filter': 'apply_rate',
        'payment_status': 'unpaid',
    }
    
    return render(request, 'billing/queue.html', context)


@login_required
def bill_detail(request, bill_id):
    """Detailed view of a specific bill with mapping functionality"""
    from datetime import datetime, timedelta
    from django.db.models import Q
    
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        line_items = BillLineItem.objects.filter(provider_bill=bill)
        
        # Get related order if claim_id exists
        order = None
        order_line_items = []
        if bill.claim_id:
            try:
                order = Order.objects.get(order_id=bill.claim_id)
                order_line_items = OrderLineItem.objects.filter(order=order)
            except Order.DoesNotExist:
                pass
        
        # Handle mapping search for UNMAPPED and VALID bills
        search_results = []
        first_name = request.GET.get('first_name', '').strip()
        last_name = request.GET.get('last_name', '').strip()
        dos_date = request.GET.get('dos_date', '').strip()
        
        if bill.status in ['UNMAPPED', 'VALID'] and (first_name or last_name or dos_date):
            # Build query for orders table
            order_query = Q()
            
            if first_name:
                # Search in patient first name with LIKE pattern
                order_query &= Q(patient_first_name__icontains=first_name)
            
            if last_name:
                # Search in patient last name with LIKE pattern
                order_query &= Q(patient_last_name__icontains=last_name)
            
            if dos_date:
                try:
                    # Parse the date
                    target_date = datetime.strptime(dos_date, '%Y-%m-%d').date()
                    
                    # Calculate date range (60 days before and after)
                    start_date = target_date - timedelta(days=60)
                    end_date = target_date + timedelta(days=60)
                    
                    # Try different date formats that might be in the DOS field
                    date_formats = [
                        '%m/%d/%y',  # MM/DD/YY
                        '%m/%d/%Y',  # MM/DD/YYYY
                        '%Y-%m-%d',  # YYYY-MM-DD
                        '%m-%d-%y',  # MM-DD-YY
                        '%m-%d-%Y',  # MM-DD-YYYY
                    ]
                    
                    # Build date range queries for different formats
                    date_queries = []
                    for fmt in date_formats:
                        start_str = start_date.strftime(fmt)
                        end_str = end_date.strftime(fmt)
                        date_queries.append(
                            Q(orderlineitem__dos__gte=start_str) & Q(orderlineitem__dos__lte=end_str)
                        )
                    
                    # Combine all date format queries with OR
                    if date_queries:
                        combined_date_query = date_queries[0]
                        for query in date_queries[1:]:
                            combined_date_query |= query
                        order_query &= combined_date_query
                    
                except ValueError:
                    # Invalid date format
                    pass
            
            # Get matching orders with their line items
            if order_query:
                orders = Order.objects.filter(order_query).distinct()
                search_results = []
                
                for order in orders:
                    # Get line items for this order
                    order_line_items_search = OrderLineItem.objects.filter(order=order)
                    
                    if order_line_items_search.exists():
                        # Group line items by order and consolidate
                        patient_name = f"{order.patient_first_name or ''} {order.patient_last_name or ''}".strip()
                        
                        # Collect all CPT codes and descriptions
                        cpt_codes = []
                        descriptions = []
                        dos_dates = []
                        
                        for line_item in order_line_items_search:
                            if line_item.cpt:
                                cpt_codes.append(line_item.cpt)
                            if line_item.description:
                                descriptions.append(line_item.description)
                            if line_item.dos:
                                formatted_date = format_dos_date(line_item.dos)
                                if formatted_date and formatted_date not in dos_dates:
                                    dos_dates.append(formatted_date)
                        
                        # Get provider billing name
                        provider_billing_name = '-'
                        if order.provider_id:
                            try:
                                provider = Provider.objects.get(primary_key=order.provider_id)
                                provider_billing_name = provider.name or '-'
                            except Provider.DoesNotExist:
                                pass
                        
                        # Create consolidated result
                        search_results.append({
                            'order': order,
                            'patient_name': patient_name,
                            'patient_first_name': order.patient_last_name,
                            'patient_last_name': order.patient_first_name,
                            'cpt_codes': ', '.join(cpt_codes) if cpt_codes else '-',
                            'cpt_list': cpt_codes,  # For individual display if needed
                            'descriptions': ', '.join(descriptions) if descriptions else '-',
                            'dos': ', '.join(dos_dates) if dos_dates else '-',  # Already unique and formatted
                            'order_id': order.order_id,
                            'line_item_count': order_line_items_search.count(),
                            'provider_billing_name': provider_billing_name,
                        })
            
            # Paginate search results
            paginator = Paginator(search_results, 20)  # Show 20 results per page
            page_number = request.GET.get('page')
            search_results = paginator.get_page(page_number)
        
        # Rate lookup logic for Apply Rate panel
        line_items_with_rates = []
        total_rates = 0
        
        for line_item in line_items:
            line_item_data = {
                'line_item': line_item,
                'rate': None,
                'rate_source': 'None',
                'provider_tin': None,
                'cpt_code': line_item.cpt_code,
                'modifier': line_item.modifier
            }
            
            # Check if line item already has a manual rate (allowed_amount)
            if line_item.allowed_amount:
                line_item_data['rate'] = str(line_item.allowed_amount)
                line_item_data['rate_source'] = 'MANUAL'
            else:
                # Get associated order to find provider
                provider_tin = None
                if bill.claim_id:
                    try:
                        order = Order.objects.get(order_id=bill.claim_id)
                        if order.provider_id:
                            try:
                                provider = Provider.objects.get(primary_key=order.provider_id)
                                provider_tin = provider.tin
                                line_item_data['provider_tin'] = provider_tin
                            except Provider.DoesNotExist:
                                pass
                    except Order.DoesNotExist:
                        pass
                
                # Clean TIN (remove spaces and dashes)
                if provider_tin:
                    import re
                    clean_tin = re.sub(r'[\s\-]', '', provider_tin)
                    
                    # Determine modifier for lookup
                    lookup_modifier = None
                    if line_item.modifier and ('TC' in line_item.modifier or '26' in line_item.modifier):
                        lookup_modifier = line_item.modifier
                    
                    # Try PPO lookup first
                    ppo_query = Q(tin=clean_tin) & Q(proc_cd=line_item.cpt_code)
                    if lookup_modifier:
                        ppo_query &= Q(modifier=lookup_modifier)
                    else:
                        ppo_query &= (Q(modifier__isnull=True) | Q(modifier='') | Q(modifier='None'))
                    
                    ppo_rate = PPO.objects.filter(ppo_query).first()
                    
                    if ppo_rate and ppo_rate.rate:
                        line_item_data['rate'] = ppo_rate.rate
                        line_item_data['rate_source'] = 'PPO'
                    else:
                        # Try OTA lookup if PPO not found
                        if bill.claim_id:
                            ota_query = Q(id_order_primary_key=bill.claim_id) & Q(cpt=line_item.cpt_code)
                            if lookup_modifier:
                                ota_query &= Q(modifier=lookup_modifier)
                            else:
                                ota_query &= (Q(modifier__isnull=True) | Q(modifier='') | Q(modifier='None'))
                            
                            ota_rate = OTA.objects.filter(ota_query).first()
                            
                            if ota_rate and ota_rate.rate:
                                line_item_data['rate'] = ota_rate.rate
                                line_item_data['rate_source'] = 'OTA'
            
            # Calculate total rates
            if line_item_data['rate']:
                try:
                    rate_value = float(line_item_data['rate'])
                    total_rates += rate_value
                except (ValueError, TypeError):
                    pass
            
            line_items_with_rates.append(line_item_data)
        
        # Get provider information from providers table if order exists
        order_provider = None
        if order and order.provider_id:
            try:
                order_provider = Provider.objects.get(primary_key=order.provider_id)
            except Provider.DoesNotExist:
                pass
        
        # Get validation errors for this bill
        validation_errors = bill.get_validation_errors()
        
        context = {
            'bill': bill,
            'line_items': line_items,
            'order': order,
            'order_line_items': order_line_items,
            'search_results': search_results,
            'first_name': first_name,
            'last_name': last_name,
            'dos_date': dos_date,
            'line_items_with_rates': line_items_with_rates,
            'total_rates': total_rates,
            'order_provider': order_provider,
            'validation_errors': validation_errors,
        }
        
        return render(request, 'billing/bill_detail.html', context)
        
    except ProviderBill.DoesNotExist:
        messages.error(request, 'Bill not found.')
        return redirect('billing:dashboard')


@login_required
def logout_view(request):
    """Logout user"""
    logout(request)
    return redirect('billing:landing')


@login_required
def map_bill(request):
    """Map a bill to an order by updating claim_id"""
    if request.method == 'POST':
        bill_id = request.POST.get('bill_id')
        order_id = request.POST.get('order_id')
        
        try:
            # Get the bill
            bill = ProviderBill.objects.get(id=bill_id)
            
            # Only allow mapping of UNMAPPED or VALID bills
            if bill.status not in ['UNMAPPED', 'VALID']:
                messages.error(request, f'Bill {bill_id} is not in UNMAPPED or VALID status and cannot be mapped.')
                return redirect('billing:bill_detail', bill_id=bill_id)
            
            # Update the claim_id with the order_id
            bill.claim_id = order_id
            bill.status = 'MAPPED'  # Update status to mapped
            bill.action = 'to_review'  # Update action
            bill.updated_at = datetime.now()
            bill.save()
            
            messages.success(request, f'Bill {bill_id} successfully mapped to Order {order_id}')
            
        except ProviderBill.DoesNotExist:
            messages.error(request, 'Bill not found.')
        except Exception as e:
            messages.error(request, f'Error mapping bill: {str(e)}')
    
    # Redirect back to the bill detail page
    return redirect('billing:bill_detail', bill_id=bill_id)


@login_required
def bill_pdf(request, bill_id):
    """Serve PDF file from S3 for a specific bill"""
    try:
        # Get the bill to ensure it exists
        bill = ProviderBill.objects.get(id=bill_id)
        
        # Find PDF in S3 and get pre-signed URL
        found, s3_key, pre_signed_url = s3_pdf_service.find_pdf(bill_id)
        
        if found and pre_signed_url:
            # Redirect to pre-signed URL with proper parameters
            return HttpResponseRedirect(pre_signed_url)
        else:
            messages.error(request, f'PDF not found for bill {bill_id}')
            return redirect('billing:bill_detail', bill_id=bill_id)
            
    except ProviderBill.DoesNotExist:
        messages.error(request, 'Bill not found.')
        return redirect('billing:dashboard')
    except Exception as e:
        messages.error(request, f'Error retrieving PDF: {str(e)}')
        return redirect('billing:bill_detail', bill_id=bill_id)


def get_status_chart_data(request):
    """API endpoint for status distribution charts"""
    unpaid_bills = ProviderBill.objects.exclude(bill_paid='Y')
    paid_bills = ProviderBill.objects.filter(bill_paid='Y')
    
    unpaid_data = list(unpaid_bills.values('status').annotate(count=Count('id')))
    paid_data = list(paid_bills.values('status').annotate(count=Count('id')))
    
    return JsonResponse({
        'unpaid': unpaid_data,
        'paid': paid_data,
    })


@login_required
def edit_bill(request, bill_id):
    """Edit bill information"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        
        if request.method == 'POST':
            # Update bill fields
            bill.claim_id = request.POST.get('claim_id', bill.claim_id)
            bill.uploaded_by = request.POST.get('uploaded_by', bill.uploaded_by)
            bill.source_file = request.POST.get('source_file', bill.source_file)
            bill.status = request.POST.get('status', bill.status)
            bill.action = request.POST.get('action', bill.action)
            bill.bill_paid = request.POST.get('bill_paid', bill.bill_paid)
            bill.total_charge = request.POST.get('total_charge') or None
            bill.patient_account_no = request.POST.get('patient_account_no', bill.patient_account_no)
            bill.last_error = request.POST.get('last_error', bill.last_error)
            
            # Handle datetime fields
            created_at_str = request.POST.get('created_at')
            if created_at_str:
                try:
                    bill.created_at = datetime.strptime(created_at_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    pass
            
            updated_at_str = request.POST.get('updated_at')
            if updated_at_str:
                try:
                    bill.updated_at = datetime.strptime(updated_at_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    pass
            
            bill.updated_at = datetime.now()
            bill.save()
            
            messages.success(request, 'Bill information updated successfully.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        context = {
            'bill': bill,
            'status_choices': ProviderBill.STATUS_CHOICES,
            'action_choices': ProviderBill.ACTION_CHOICES,
        }
        return render(request, 'billing/edit_bill.html', context)
        
    except ProviderBill.DoesNotExist:
        messages.error(request, 'Bill not found.')
        return redirect('billing:dashboard')


@login_required
def edit_patient_info(request, bill_id):
    """Edit patient information"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        
        if request.method == 'POST':
            # Update patient and provider fields
            bill.patient_name = request.POST.get('patient_name', bill.patient_name)
            bill.patient_dob = request.POST.get('patient_dob', bill.patient_dob)
            bill.patient_zip = request.POST.get('patient_zip', bill.patient_zip)
            bill.patient_account_no = request.POST.get('patient_account_no', bill.patient_account_no)
            bill.billing_provider_name = request.POST.get('billing_provider_name', bill.billing_provider_name)
            bill.billing_provider_tin = request.POST.get('billing_provider_tin', bill.billing_provider_tin)
            bill.billing_provider_npi = request.POST.get('billing_provider_npi', bill.billing_provider_npi)
            bill.billing_provider_address = request.POST.get('billing_provider_address', bill.billing_provider_address)
            bill.updated_at = datetime.now()
            bill.save()
            
            messages.success(request, 'Patient information updated successfully.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        context = {
            'bill': bill,
        }
        return render(request, 'billing/edit_patient_info.html', context)
        
    except ProviderBill.DoesNotExist:
        messages.error(request, 'Bill not found.')
        return redirect('billing:dashboard')


@login_required
def edit_provider_info(request, bill_id):
    """Edit provider information"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        
        if request.method == 'POST':
            # Update provider fields
            bill.billing_provider_name = request.POST.get('billing_provider_name', bill.billing_provider_name)
            bill.billing_provider_tin = request.POST.get('billing_provider_tin', bill.billing_provider_tin)
            bill.billing_provider_npi = request.POST.get('billing_provider_npi', bill.billing_provider_npi)
            bill.billing_provider_address = request.POST.get('billing_provider_address', bill.billing_provider_address)
            bill.updated_at = datetime.now()
            bill.save()
            
            messages.success(request, 'Provider information updated successfully.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        context = {
            'bill': bill,
        }
        return render(request, 'billing/edit_provider_info.html', context)
        
    except ProviderBill.DoesNotExist:
        messages.error(request, 'Bill not found.')
        return redirect('billing:dashboard')


@login_required
def edit_order_provider(request, bill_id):
    """Edit order provider information"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        
        # Get the order and provider
        order = None
        order_provider = None
        
        if bill.claim_id:
            try:
                order = Order.objects.get(order_id=bill.claim_id)
                if order.provider_id:
                    try:
                        order_provider = Provider.objects.get(primary_key=order.provider_id)
                    except Provider.DoesNotExist:
                        pass
            except Order.DoesNotExist:
                pass
        
        if not order_provider:
            messages.error(request, 'No order provider found for this bill.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        if request.method == 'POST':
            # Update provider fields
            order_provider.name = request.POST.get('name', order_provider.name)
            order_provider.npi = request.POST.get('npi', order_provider.npi)
            order_provider.tin = request.POST.get('tin', order_provider.tin)
            order_provider.address_line_1 = request.POST.get('address_line_1', order_provider.address_line_1)
            order_provider.address_line_2 = request.POST.get('address_line_2', order_provider.address_line_2)
            order_provider.city = request.POST.get('city', order_provider.city)
            order_provider.state = request.POST.get('state', order_provider.state)
            order_provider.postal_code = request.POST.get('postal_code', order_provider.postal_code)
            order_provider.phone = request.POST.get('phone', order_provider.phone)
            order_provider.email = request.POST.get('email', order_provider.email)
            order_provider.website = request.POST.get('website', order_provider.website)
            order_provider.provider_type = request.POST.get('provider_type', order_provider.provider_type)
            order_provider.provider_status = request.POST.get('provider_status', order_provider.provider_status)
            order_provider.provider_network = request.POST.get('provider_network', order_provider.provider_network)
            order_provider.latitude = request.POST.get('latitude', order_provider.latitude)
            order_provider.longitude = request.POST.get('longitude', order_provider.longitude)
            
            # Billing address fields
            order_provider.billing_name = request.POST.get('billing_name', order_provider.billing_name)
            order_provider.billing_address_1 = request.POST.get('billing_address_1', order_provider.billing_address_1)
            order_provider.billing_address_2 = request.POST.get('billing_address_2', order_provider.billing_address_2)
            order_provider.billing_address_city = request.POST.get('billing_address_city', order_provider.billing_address_city)
            order_provider.billing_address_state = request.POST.get('billing_address_state', order_provider.billing_address_state)
            order_provider.billing_address_postal_code = request.POST.get('billing_address_postal_code', order_provider.billing_address_postal_code)
            
            # Service capabilities
            order_provider.ct = request.POST.get('ct', order_provider.ct)
            order_provider.mri_1_5t = request.POST.get('mri_1_5t', order_provider.mri_1_5t)
            order_provider.mri_3_0t = request.POST.get('mri_3_0t', order_provider.mri_3_0t)
            order_provider.mri_open = request.POST.get('mri_open', order_provider.mri_open)
            order_provider.xray = request.POST.get('xray', order_provider.xray)
            order_provider.mammo = request.POST.get('mammo', order_provider.mammo)
            order_provider.echo = request.POST.get('echo', order_provider.echo)
            order_provider.ekg = request.POST.get('ekg', order_provider.ekg)
            order_provider.bone_density = request.POST.get('bone_density', order_provider.bone_density)
            
            order_provider.save()
            
            messages.success(request, 'Order provider information updated successfully.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        context = {
            'bill': bill,
            'order': order,
            'order_provider': order_provider,
        }
        return render(request, 'billing/edit_order_provider.html', context)
        
    except ProviderBill.DoesNotExist:
        messages.error(request, 'Bill not found.')
        return redirect('billing:dashboard')


@login_required
def edit_bill_line_item(request, bill_id, line_item_id):
    """Edit a specific bill line item"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        line_item = BillLineItem.objects.get(id=line_item_id, provider_bill=bill)
        
        if request.method == 'POST':
            # Update line item fields
            line_item.cpt_code = request.POST.get('cpt_code', line_item.cpt_code)
            line_item.modifier = request.POST.get('modifier', line_item.modifier)
            line_item.units = request.POST.get('units') or None
            line_item.charge_amount = request.POST.get('charge_amount') or None
            line_item.allowed_amount = request.POST.get('allowed_amount') or None
            line_item.decision = request.POST.get('decision', line_item.decision)
            line_item.reason_code = request.POST.get('reason_code', line_item.reason_code)
            line_item.date_of_service = request.POST.get('date_of_service', line_item.date_of_service)
            line_item.place_of_service = request.POST.get('place_of_service', line_item.place_of_service)
            line_item.diagnosis_pointer = request.POST.get('diagnosis_pointer', line_item.diagnosis_pointer)
            line_item.save()
            
            messages.success(request, 'Bill line item updated successfully.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        context = {
            'bill': bill,
            'line_item': line_item,
            'decision_choices': BillLineItem.DECISION_CHOICES,
        }
        return render(request, 'billing/edit_bill_line_item.html', context)
        
    except (ProviderBill.DoesNotExist, BillLineItem.DoesNotExist):
        messages.error(request, 'Bill or line item not found.')
        return redirect('billing:dashboard')


@login_required
def edit_order_info(request, bill_id):
    """Edit order information"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        
        if not bill.claim_id:
            messages.error(request, 'No order mapped to this bill.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        order = Order.objects.get(order_id=bill.claim_id)
        
        if request.method == 'POST':
            # Update order fields
            order.filemaker_record_number = request.POST.get('filemaker_record_number', order.filemaker_record_number)
            order.patient_address = request.POST.get('patient_address', order.patient_address)
            order.patient_city = request.POST.get('patient_city', order.patient_city)
            order.patient_state = request.POST.get('patient_state', order.patient_state)
            order.patient_zip = request.POST.get('patient_zip', order.patient_zip)
            order.patient_injury_date = request.POST.get('patient_injury_date', order.patient_injury_date)
            order.patient_injury_description = request.POST.get('patient_injury_description', order.patient_injury_description)
            order.patient_dob = request.POST.get('patient_dob', order.patient_dob)
            order.patient_last_name = request.POST.get('patient_last_name', order.patient_last_name)
            order.patient_first_name = request.POST.get('patient_first_name', order.patient_first_name)
            order.patient_name = request.POST.get('patient_name', order.patient_name)
            order.patient_phone = request.POST.get('patient_phone', order.patient_phone)
            order.referring_physician = request.POST.get('referring_physician', order.referring_physician)
            order.referring_physician_npi = request.POST.get('referring_physician_npi', order.referring_physician_npi)
            order.assigning_company = request.POST.get('assigning_company', order.assigning_company)
            order.assigning_adjuster = request.POST.get('assigning_adjuster', order.assigning_adjuster)
            order.claim_number = request.POST.get('claim_number', order.claim_number)
            order.order_type = request.POST.get('order_type', order.order_type)
            order.jurisdiction_state = request.POST.get('jurisdiction_state', order.jurisdiction_state)
            order.bundle_type = request.POST.get('bundle_type', order.bundle_type)
            order.provider_id = request.POST.get('provider_id', order.provider_id)
            order.fully_paid = request.POST.get('fully_paid', order.fully_paid)
            order.updated_at = datetime.now()
            order.save()
            
            messages.success(request, 'Order information updated successfully.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        context = {
            'bill': bill,
            'order': order,
        }
        return render(request, 'billing/edit_order_info.html', context)
        
    except (ProviderBill.DoesNotExist, Order.DoesNotExist):
        messages.error(request, 'Bill or order not found.')
        return redirect('billing:dashboard')


@login_required
def edit_order_line_item(request, bill_id, line_item_id):
    """Edit a specific order line item"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        
        if not bill.claim_id:
            messages.error(request, 'No order mapped to this bill.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        order = Order.objects.get(order_id=bill.claim_id)
        line_item = OrderLineItem.objects.get(id=line_item_id, order=order)
        
        if request.method == 'POST':
            # Update line item fields
            line_item.cpt = request.POST.get('cpt', line_item.cpt)
            line_item.modifier = request.POST.get('modifier', line_item.modifier)
            line_item.units = request.POST.get('units', line_item.units)
            line_item.description = request.POST.get('description', line_item.description)
            line_item.charge = request.POST.get('charge', line_item.charge)
            line_item.dos = request.POST.get('dos', line_item.dos)
            line_item.line_number = request.POST.get('line_number', line_item.line_number)
            line_item.is_active = request.POST.get('is_active', line_item.is_active)
            line_item.br_paid = request.POST.get('br_paid', line_item.br_paid)
            line_item.br_rate = request.POST.get('br_rate', line_item.br_rate)
            line_item.eobr_doc_no = request.POST.get('eobr_doc_no', line_item.eobr_doc_no)
            line_item.hcfa_doc_no = request.POST.get('hcfa_doc_no', line_item.hcfa_doc_no)
            line_item.br_date_processed = request.POST.get('br_date_processed', line_item.br_date_processed)
            line_item.bills_paid = request.POST.get('bills_paid') or None
            line_item.bill_reviewed = request.POST.get('bill_reviewed', line_item.bill_reviewed)
            
            # Handle datetime fields
            created_at_str = request.POST.get('created_at')
            if created_at_str:
                try:
                    line_item.created_at = datetime.strptime(created_at_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    pass
            
            updated_at_str = request.POST.get('updated_at')
            if updated_at_str:
                try:
                    line_item.updated_at = datetime.strptime(updated_at_str, '%Y-m-%dT%H:%M')
                except ValueError:
                    pass
            
            line_item.updated_at = datetime.now()
            line_item.save()
            
            messages.success(request, 'Order line item updated successfully.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        context = {
            'bill': bill,
            'order': order,
            'line_item': line_item,
        }
        return render(request, 'billing/edit_order_line_item.html', context)
        
    except (ProviderBill.DoesNotExist, Order.DoesNotExist, OrderLineItem.DoesNotExist):
        messages.error(request, 'Bill, order, or line item not found.')
        return redirect('billing:dashboard')


@login_required
def validate_bill(request, bill_id):
    """Validate a bill and change status to VALID with action to_map"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        
        # Only allow validation of INVALID bills
        if bill.status != 'INVALID':
            messages.error(request, f'Bill {bill_id} is not in INVALID status and cannot be validated.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        # Update bill status and action
        bill.status = 'VALID'
        bill.action = 'to_map'
        bill.last_error = None  # Clear the last error message
        bill.updated_at = datetime.now()
        bill.save()
        
        messages.success(request, f'Bill {bill_id} has been validated successfully. Status changed to VALID.')
        return redirect('billing:bill_detail', bill_id=bill_id)
        
    except ProviderBill.DoesNotExist:
        messages.error(request, 'Bill not found.')
        return redirect('billing:dashboard')
    except Exception as e:
        messages.error(request, f'Error validating bill: {str(e)}')
        return redirect('billing:bill_detail', bill_id=bill_id)


@login_required
def review_rate(request, bill_id):
    """Review rate for a bill and update action"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        
        # Only allow rate review of bills with review_rate or review_rates action
        if bill.action not in ['review_rate', 'review_rates']:
            messages.error(request, f'Bill {bill_id} is not in rate review status and cannot be processed.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        # Update bill action to indicate rate has been reviewed
        bill.action = 'to_review'  # Move to next step in workflow
        bill.updated_at = datetime.now()
        bill.save()
        
        messages.success(request, f'Bill {bill_id} rate has been reviewed successfully. Action updated to to_review.')
        return redirect('billing:bill_detail', bill_id=bill_id)
        
    except ProviderBill.DoesNotExist:
        messages.error(request, 'Bill not found.')
        return redirect('billing:dashboard')
    except Exception as e:
        messages.error(request, f'Error reviewing rate: {str(e)}')
        return redirect('billing:bill_detail', bill_id=bill_id)


@login_required
def apply_rates(request, bill_id):
    """Apply rates to a bill and update status"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        
        # Update bill status and action (works for any bill)
        bill.status = 'REVIEWED'  # Move to reviewed status
        bill.action = 'to_review'  # Move to next step in workflow
        bill.updated_at = datetime.now()
        bill.save()
        
        messages.success(request, f'Bill {bill_id} rates have been applied successfully. Status updated to REVIEWED.')
        return redirect('billing:bill_detail', bill_id=bill_id)
        
    except ProviderBill.DoesNotExist:
        messages.error(request, 'Bill not found.')
        return redirect('billing:dashboard')
    except Exception as e:
        messages.error(request, f'Error applying rates: {str(e)}')
        return redirect('billing:bill_detail', bill_id=bill_id)


@login_required
def add_manual_rate(request, bill_id):
    """Add a manual rate to a specific line item"""
    if request.method == 'POST':
        try:
            bill = ProviderBill.objects.get(id=bill_id)
            line_item_id = request.POST.get('line_item_id')
            rate = request.POST.get('rate')
            
            if not line_item_id or not rate:
                messages.error(request, 'Line item ID and rate are required.')
                return redirect('billing:bill_detail', bill_id=bill_id)
            
            # Get the line item
            line_item = BillLineItem.objects.get(id=line_item_id, provider_bill=bill)
            
            # Convert rate to decimal
            try:
                rate_decimal = float(rate)
                if rate_decimal < 0:
                    messages.error(request, 'Rate cannot be negative.')
                    return redirect('billing:bill_detail', bill_id=bill_id)
            except ValueError:
                messages.error(request, 'Invalid rate format.')
                return redirect('billing:bill_detail', bill_id=bill_id)
            
            # Update the line item's allowed_amount with the manual rate
            line_item.allowed_amount = rate_decimal
            line_item.save()
            
            # Update bill timestamp
            bill.updated_at = datetime.now()
            bill.save()
            
            messages.success(request, f'Manual rate of ${rate_decimal:.2f} added to line item {line_item.cpt_code}.')
            return redirect('billing:bill_detail', bill_id=bill_id)
            
        except ProviderBill.DoesNotExist:
            messages.error(request, 'Bill not found.')
            return redirect('billing:dashboard')
        except BillLineItem.DoesNotExist:
            messages.error(request, 'Line item not found.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        except Exception as e:
            messages.error(request, f'Error adding manual rate: {str(e)}')
            return redirect('billing:bill_detail', bill_id=bill_id)
    
    return redirect('billing:bill_detail', bill_id=bill_id)


@login_required
def mark_bill_paid(request, bill_id):
    """Mark a bill as paid"""
    if request.method == 'POST':
        try:
            bill = ProviderBill.objects.get(id=bill_id)
            
            # Update bill_paid to 'Y'
            bill.bill_paid = 'Y'
            bill.updated_at = datetime.now()
            bill.save()
            
            messages.success(request, f'Bill {bill_id} has been marked as paid.')
            return redirect('billing:ready_to_pay_queue')
            
        except ProviderBill.DoesNotExist:
            messages.error(request, 'Bill not found.')
            return redirect('billing:dashboard')
        except Exception as e:
            messages.error(request, f'Error marking bill as paid: {str(e)}')
            return redirect('billing:ready_to_pay_queue')
    
    return redirect('billing:ready_to_pay_queue')


@login_required
def add_bill_line_item(request, bill_id):
    """Add a new bill line item"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        
        if request.method == 'POST':
            # Create new line item
            line_item = BillLineItem.objects.create(
                provider_bill=bill,
                cpt_code=request.POST.get('cpt_code', ''),
                modifier=request.POST.get('modifier', ''),
                units=request.POST.get('units') or None,
                charge_amount=request.POST.get('charge_amount') or None,
                allowed_amount=request.POST.get('allowed_amount') or None,
                decision=request.POST.get('decision', 'pending'),
                reason_code=request.POST.get('reason_code', ''),
                date_of_service=request.POST.get('date_of_service', ''),
                place_of_service=request.POST.get('place_of_service', ''),
                diagnosis_pointer=request.POST.get('diagnosis_pointer', ''),
            )
            
            messages.success(request, 'Bill line item added successfully.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        context = {
            'bill': bill,
            'decision_choices': BillLineItem.DECISION_CHOICES,
        }
        return render(request, 'billing/add_bill_line_item.html', context)
        
    except ProviderBill.DoesNotExist:
        messages.error(request, 'Bill not found.')
        return redirect('billing:dashboard')


@login_required
def delete_bill_line_item(request, bill_id, line_item_id):
    """Delete a bill line item"""
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        line_item = BillLineItem.objects.get(id=line_item_id, provider_bill=bill)
        
        if request.method == 'POST':
            line_item.delete()
            messages.success(request, 'Bill line item deleted successfully.')
            return redirect('billing:bill_detail', bill_id=bill_id)
        
        context = {
            'bill': bill,
            'line_item': line_item,
        }
        return render(request, 'billing/delete_bill_line_item.html', context)
        
    except (ProviderBill.DoesNotExist, BillLineItem.DoesNotExist):
        messages.error(request, 'Bill or line item not found.')
        return redirect('billing:dashboard')


@login_required
def order_search(request):
    """Search for orders by patient information and date of service"""
    from datetime import datetime, timedelta
    from django.db.models import Q
    
    # Get search parameters
    first_name = request.GET.get('first_name', '').strip()
    last_name = request.GET.get('last_name', '').strip()
    dos_date = request.GET.get('dos_date', '').strip()
    
    # Start with all orders
    orders = Order.objects.all().order_by('-created_at')
    
    # Search results
    search_results = []
    
    if first_name or last_name or dos_date:
        # Build query for orders table
        order_query = Q()
        
        if first_name:
            # Search in patient first name with LIKE pattern
            order_query &= Q(patient_first_name__icontains=first_name)
        
        if last_name:
            # Search in patient last name with LIKE pattern
            order_query &= Q(patient_last_name__icontains=last_name)
        
        order_query = add_date_search_to_query(order_query, dos_date)
        
        # Get matching orders
        if order_query:
            matching_orders = orders.filter(order_query).distinct()
            search_results = []
            
            for order in matching_orders:
                # Get line items for this order
                line_items = OrderLineItem.objects.filter(order=order)
                
                # Collect all DOS dates from line items
                dos_dates = get_unique_dos_dates(line_items)
                
                # Check if there's an associated bill
                associated_bill = ProviderBill.objects.filter(claim_id=order.order_id).first()
                
                # Check for duplicate orders with same ID
                duplicate_orders_count = Order.objects.filter(order_id=order.order_id).count()
                
                # Create result
                search_results.append({
                    'order': order,
                    'patient_name': f"{order.patient_first_name or ''} {order.patient_last_name or ''}".strip() or 'N/A',
                    'patient_first_name': order.patient_last_name or '',
                    'patient_last_name': order.patient_first_name or '',
                    'dos': ', '.join(dos_dates) if dos_dates else '-',  # Already unique and formatted
                    'order_id': order.order_id,
                    'line_item_count': line_items.count(),
                    'associated_bill': associated_bill,
                    'bill_id': associated_bill.id if associated_bill else None,
                    'bill_status': associated_bill.status if associated_bill else 'No Bill',
                    'bill_paid': associated_bill.bill_paid if associated_bill else None,
                    'total_charge': associated_bill.total_charge if associated_bill else None,
                    'created_at': order.created_at,
                    'duplicate_count': duplicate_orders_count,
                })
    
    # Paginate search results
    paginator = Paginator(search_results, 20)  # Show 20 results per page
    page_number = request.GET.get('page')
    search_results_page = paginator.get_page(page_number)
    
    context = {
        'orders': orders,
        'search_results': search_results_page,
        'first_name': first_name,
        'last_name': last_name,
        'dos_date': dos_date,
    }
    
    return render(request, 'billing/order_search.html', context)


@login_required
def order_detail(request, order_id):
    """Detailed view of a specific order with associated bill information"""
    try:
        # Use filter().first() to handle cases where there might be multiple orders with same ID
        order = Order.objects.filter(order_id=order_id).first()
        
        if not order:
            messages.error(request, 'Order not found.')
            return redirect('billing:order_search')
        
        order_line_items = OrderLineItem.objects.filter(order=order)
        
        # Find associated bill
        associated_bill = ProviderBill.objects.filter(claim_id=order_id).first()
        
        # If there's an associated bill, get its line items
        bill_line_items = []
        if associated_bill:
            bill_line_items = BillLineItem.objects.filter(provider_bill=associated_bill)
        
        # Check for duplicate orders with same ID
        duplicate_count = Order.objects.filter(order_id=order_id).count()
        
        context = {
            'order': order,
            'order_line_items': order_line_items,
            'associated_bill': associated_bill,
            'bill_line_items': bill_line_items,
            'duplicate_count': duplicate_count,
        }
        
        return render(request, 'billing/order_detail.html', context)
        
    except Exception as e:
        messages.error(request, f'Error loading order: {str(e)}')
        return redirect('billing:order_search')