"""
URL configuration for billing app
"""

from django.urls import path
from . import views
from . import views_job_monitoring

app_name = 'billing'

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('intake/', views.intake_queue, name='intake_queue'),
    path('intake/upload/', views.upload_pdf_batch, name='upload_pdf_batch'),
    path('intake/process-scans/', views.process_scans, name='process_scans'),
    path('intake/process-validation/', views.process_validation, name='process_validation'),
    path('intake/process-mapping/', views.process_mapping, name='process_mapping'),
    path('validation/process-second-pass/', views.process_second_pass, name='process_second_pass'),
    path('test-import/', views.test_import, name='test_import'),
    path('validation/', views.validation_queue, name='validation_queue'),
    path('mapping/', views.mapping_queue, name='mapping_queue'),
    path('filemaker-mapping/', views.filemaker_mapping_queue, name='filemaker_mapping_queue'),
    path('worker-assignment/', views.worker_assignment, name='worker_assignment'),
    path('worker/<str:worker_name>/', views.worker_queue, name='worker_queue'),
    path('correction/', views.correction_queue, name='correction_queue'),
    path('rate-correction/', views.rate_correction_queue, name='rate_correction_queue'),
    path('ready-to-pay/', views.ready_to_pay_queue, name='ready_to_pay_queue'),
    path('bill/<str:bill_id>/', views.bill_detail, name='bill_detail'),
    path('bill/<str:bill_id>/pdf/', views.bill_pdf, name='bill_pdf'),
    path('map-bill/', views.map_bill, name='map_bill'),
    path('logout/', views.logout_view, name='logout'),
    path('api/status-chart/', views.get_status_chart_data, name='status_chart_api'),
    
    # Edit views
    path('bill/<str:bill_id>/edit/', views.edit_bill, name='edit_bill'),
    path('bill/<str:bill_id>/edit/patient/', views.edit_patient_info, name='edit_patient_info'),
    path('bill/<str:bill_id>/edit/provider/', views.edit_provider_info, name='edit_provider_info'),
    path('bill/<str:bill_id>/edit/order-provider/', views.edit_order_provider, name='edit_order_provider'),
    path('bill/<str:bill_id>/edit/line-item/<int:line_item_id>/', views.edit_bill_line_item, name='edit_bill_line_item'),
    path('bill/<str:bill_id>/edit/order/', views.edit_order_info, name='edit_order_info'),
    path('bill/<str:bill_id>/edit/order-line-item/<str:line_item_id>/', views.edit_order_line_item, name='edit_order_line_item'),
    
    # Action views
    path('bill/<str:bill_id>/validate/', views.validate_bill, name='validate_bill'),
    path('bill/<str:bill_id>/review-rate/', views.review_rate, name='review_rate'),
    path('bill/<str:bill_id>/apply-rates/', views.apply_rates, name='apply_rates'),
    path('bill/<str:bill_id>/add-manual-rate/', views.add_manual_rate, name='add_manual_rate'),
    path('bill/<str:bill_id>/mark-paid/', views.mark_bill_paid, name='mark_bill_paid'),
    path('bill/<str:bill_id>/approve-for-rate/', views.approve_for_rate, name='approve_for_rate'),
    path('bill/<str:bill_id>/approve-for-payment/', views.approve_for_payment, name='approve_for_payment'),
    path('bill/<str:bill_id>/approve-for-bill-review/', views.approve_for_bill_review, name='approve_for_bill_review'),
    
    # Bill line item management
    path('bill/<str:bill_id>/add-line-item/', views.add_bill_line_item, name='add_bill_line_item'),
    path('bill/<str:bill_id>/delete-line-item/<int:line_item_id>/', views.delete_bill_line_item, name='delete_bill_line_item'),
    
    # Order search
    path('search/', views.order_search, name='order_search'),
    path('order/<str:order_id>/', views.order_detail, name='order_detail'),
    
    # Job monitoring API endpoints
    path('api/jobs/progress/<str:job_id>/', views_job_monitoring.get_job_progress, name='job_progress'),
    path('api/jobs/logs/<str:job_id>/', views_job_monitoring.get_job_logs, name='job_logs'),
    path('api/jobs/active/', views_job_monitoring.list_active_jobs, name='active_jobs'),
    path('api/jobs/summary/', views_job_monitoring.get_job_status_summary, name='job_summary'),
    path('api/jobs/cancel/<str:job_id>/', views_job_monitoring.cancel_job, name='cancel_job'),
]
