"""
URL configuration for billing app
"""

from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('validation/', views.validation_queue, name='validation_queue'),
    path('mapping/', views.mapping_queue, name='mapping_queue'),
    path('correction/', views.correction_queue, name='correction_queue'),
    path('rate-correction/', views.rate_correction_queue, name='rate_correction_queue'),
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
    
    # Bill line item management
    path('bill/<str:bill_id>/add-line-item/', views.add_bill_line_item, name='add_bill_line_item'),
    path('bill/<str:bill_id>/delete-line-item/<int:line_item_id>/', views.delete_bill_line_item, name='delete_bill_line_item'),
    
    # Order search
    path('search/', views.order_search, name='order_search'),
    path('order/<str:order_id>/', views.order_detail, name='order_detail'),
]
