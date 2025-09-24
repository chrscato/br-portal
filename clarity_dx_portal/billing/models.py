"""
Django models for the Clarity Dx Bill Review Portal
Based on the monolith.db schema
"""

from django.db import models
from django.core.validators import MinValueValidator


class ProviderBill(models.Model):
    """Provider billing records - central table for bill processing"""
    
    STATUS_CHOICES = [
        ('ESCALATE', 'Escalate'),
        ('MAPPED', 'Mapped'),
        ('REVIEWED', 'Reviewed'),
        ('INVALID', 'Invalid'),
        ('VALID', 'Valid'),
        ('UNMAPPED', 'Unmapped'),
        ('REVIEW_FLAG', 'Review Flag'),
        ('FLAGGED', 'Flagged'),
        ('SCANNED', 'Scanned'),
        ('SCRAPED', 'Scraped'),
    ]
    
    ACTION_CHOICES = [
        ('resolve_escalation', 'Resolve Escalation'),
        ('to_review', 'To Review'),
        ('apply_rate', 'Apply Rate'),
        ('validate', 'Validate'),
        ('to_validate', 'To Validate'),
        ('add_line_items', 'Add Line Items'),
        ('to_map', 'To Map'),
        ('map_provider', 'Map Provider'),
        ('correct_data', 'Correct Data'),
        ('review_rate', 'Review Rate'),
        ('review_rates', 'Review Rates'),
    ]
    
    id = models.CharField(max_length=50, primary_key=True)
    claim_id = models.CharField(max_length=50, blank=True, null=True)
    uploaded_by = models.CharField(max_length=100, blank=True, null=True)
    source_file = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ESCALATE')
    last_error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    patient_name = models.CharField(max_length=255, blank=True, null=True)
    patient_dob = models.CharField(max_length=20, blank=True, null=True)
    patient_zip = models.CharField(max_length=10, blank=True, null=True)
    billing_provider_name = models.CharField(max_length=255, blank=True, null=True)
    billing_provider_address = models.TextField(blank=True, null=True)
    billing_provider_tin = models.CharField(max_length=20, blank=True, null=True)
    billing_provider_npi = models.CharField(max_length=20, blank=True, null=True)
    total_charge = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    patient_account_no = models.CharField(max_length=50, blank=True, null=True)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, default='resolve_escalation')
    bill_paid = models.CharField(max_length=1, blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'ProviderBill'
        managed = False  # Use existing table
        
    def __str__(self):
        return f"Bill {self.id} - {self.patient_name} ({self.status})"
    
    @property
    def is_paid(self):
        return self.bill_paid == 'Y'
    
    @property
    def is_unpaid(self):
        return self.bill_paid != 'Y'
    
    def get_validation_errors(self):
        """Get validation errors for this bill"""
        errors = []
        
        # Get line items sum
        line_items = BillLineItem.objects.filter(provider_bill=self)
        line_items_sum = sum(
            float(item.charge_amount) for item in line_items 
            if item.charge_amount is not None
        )
        
        # Check if total charge is null or zero
        if self.total_charge is None:
            if line_items_sum > 0:
                errors.append({
                    'type': 'total_charge_missing',
                    'message': f'Total charge is missing but line items sum to ${line_items_sum:.2f}',
                    'total_charge': None,
                    'line_items_sum': line_items_sum,
                    'difference': line_items_sum
                })
        elif float(self.total_charge) == 0:
            if line_items_sum > 0:
                errors.append({
                    'type': 'total_charge_zero',
                    'message': f'Total charge is $0.00 but line items sum to ${line_items_sum:.2f}',
                    'total_charge': 0.0,
                    'line_items_sum': line_items_sum,
                    'difference': line_items_sum
                })
        else:
            # Check total charge vs sum of line items (existing logic)
            # Allow for small rounding differences (within $0.01)
            if abs(float(self.total_charge) - line_items_sum) > 0.01:
                errors.append({
                    'type': 'total_charge_mismatch',
                    'message': f'Total charge (${self.total_charge:.2f}) does not match sum of line items (${line_items_sum:.2f})',
                    'total_charge': float(self.total_charge),
                    'line_items_sum': line_items_sum,
                    'difference': abs(float(self.total_charge) - line_items_sum)
                })
        
        return errors
    
    def get_line_items_sum(self):
        """Get the sum of all line item charges for this bill"""
        line_items = BillLineItem.objects.filter(provider_bill=self)
        return sum(
            float(item.charge_amount) for item in line_items 
            if item.charge_amount is not None
        )


class BillLineItem(models.Model):
    """Individual line items for each provider bill"""
    
    DECISION_CHOICES = [
        ('pending', 'Pending'),
        ('APPROVED', 'Approved'),
        ('DENIED', 'Denied'),
        ('PENDING', 'Pending'),
    ]
    
    id = models.AutoField(primary_key=True)
    provider_bill = models.ForeignKey(ProviderBill, on_delete=models.CASCADE, db_column='provider_bill_id')
    cpt_code = models.CharField(max_length=10, blank=True, null=True)
    modifier = models.CharField(max_length=10, blank=True, null=True)
    units = models.IntegerField(blank=True, null=True, validators=[MinValueValidator(0)])
    charge_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    allowed_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, default='pending')
    reason_code = models.CharField(max_length=10, blank=True, null=True)
    date_of_service = models.CharField(max_length=20, blank=True, null=True)
    place_of_service = models.CharField(max_length=10, blank=True, null=True)
    diagnosis_pointer = models.CharField(max_length=10, blank=True, null=True)
    
    class Meta:
        db_table = 'BillLineItem'
        managed = False  # Use existing table
        
    def __str__(self):
        return f"Line {self.id} - {self.cpt_code} (${self.charge_amount})"


class Order(models.Model):
    """Main orders/claims table containing patient and order information"""
    
    order_id = models.CharField(max_length=50, primary_key=True, db_column='Order_ID')
    filemaker_record_number = models.CharField(max_length=20, blank=True, null=True, db_column='FileMaker_Record_Number')
    patient_address = models.CharField(max_length=255, blank=True, null=True, db_column='Patient_Address')
    patient_city = models.CharField(max_length=100, blank=True, null=True, db_column='Patient_City')
    patient_state = models.CharField(max_length=10, blank=True, null=True, db_column='Patient_State')
    patient_zip = models.CharField(max_length=10, blank=True, null=True, db_column='Patient_Zip')
    patient_injury_date = models.CharField(max_length=20, blank=True, null=True, db_column='Patient_Injury_Date')
    patient_injury_description = models.TextField(blank=True, null=True, db_column='Patient_Injury_Description')
    patient_dob = models.CharField(max_length=20, blank=True, null=True, db_column='Patient_DOB')
    patient_last_name = models.CharField(max_length=100, blank=True, null=True, db_column='Patient_Last_Name')
    patient_first_name = models.CharField(max_length=100, blank=True, null=True, db_column='Patient_First_Name')
    patient_name = models.CharField(max_length=200, blank=True, null=True, db_column='PatientName')
    patient_phone = models.CharField(max_length=20, blank=True, null=True, db_column='PatientPhone')
    referring_physician = models.CharField(max_length=255, blank=True, null=True, db_column='Referring_Physician')
    referring_physician_npi = models.CharField(max_length=20, blank=True, null=True, db_column='Referring_Physician_NPI')
    assigning_company = models.CharField(max_length=255, blank=True, null=True, db_column='Assigning_Company')
    assigning_adjuster = models.CharField(max_length=255, blank=True, null=True, db_column='Assigning_Adjuster')
    claim_number = models.CharField(max_length=50, blank=True, null=True, db_column='Claim_Number')
    order_type = models.CharField(max_length=50, blank=True, null=True, db_column='Order_Type')
    jurisdiction_state = models.CharField(max_length=10, blank=True, null=True, db_column='Jurisdiction_State')
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    is_active = models.FloatField(blank=True, null=True)
    bundle_type = models.CharField(max_length=50, blank=True, null=True)
    provider_id = models.CharField(max_length=50, blank=True, null=True)
    provider_name = models.FloatField(blank=True, null=True)
    bills_paid = models.IntegerField(blank=True, null=True, db_column='BILLS_PAID')
    fully_paid = models.CharField(max_length=10, blank=True, null=True, db_column='FULLY_PAID')
    bills_rec = models.IntegerField(blank=True, null=True, db_column='BILLS_REC')
    
    class Meta:
        db_table = 'orders'
        managed = False  # Use existing table
        
    def __str__(self):
        return f"Order {self.order_id} - {self.patient_name}"


class OrderLineItem(models.Model):
    """Individual line items for each order (procedures, charges)"""
    
    id = models.CharField(max_length=50, primary_key=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, db_column='Order_ID')
    dos = models.CharField(max_length=20, blank=True, null=True, db_column='DOS')
    cpt = models.CharField(max_length=10, blank=True, null=True, db_column='CPT')
    modifier = models.CharField(max_length=10, blank=True, null=True, db_column='Modifier')
    units = models.CharField(max_length=10, blank=True, null=True, db_column='Units')
    description = models.TextField(blank=True, null=True, db_column='Description')
    charge = models.CharField(max_length=20, blank=True, null=True, db_column='Charge')
    line_number = models.CharField(max_length=10, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    is_active = models.CharField(max_length=10, blank=True, null=True)
    br_paid = models.CharField(max_length=20, blank=True, null=True, db_column='BR_paid')
    br_rate = models.CharField(max_length=20, blank=True, null=True, db_column='BR_rate')
    eobr_doc_no = models.CharField(max_length=50, blank=True, null=True, db_column='EOBR_doc_no')
    hcfa_doc_no = models.CharField(max_length=50, blank=True, null=True, db_column='HCFA_doc_no')
    br_date_processed = models.CharField(max_length=20, blank=True, null=True, db_column='BR_date_processed')
    bills_paid = models.IntegerField(blank=True, null=True, db_column='BILLS_PAID')
    bill_reviewed = models.CharField(max_length=10, blank=True, null=True, db_column='BILL_REVIEWED')
    
    class Meta:
        db_table = 'order_line_items'
        managed = False  # Use existing table
        
    def __str__(self):
        return f"Line {self.id} - {self.cpt} (${self.charge})"


class Provider(models.Model):
    """Comprehensive provider information and capabilities"""
    
    primary_key = models.CharField(max_length=50, primary_key=True, db_column='PrimaryKey')
    name = models.CharField(max_length=255, blank=True, null=True, db_column='Name')
    npi = models.CharField(max_length=20, blank=True, null=True, db_column='NPI')
    tin = models.CharField(max_length=20, blank=True, null=True, db_column='TIN')
    address_line_1 = models.CharField(max_length=255, blank=True, null=True, db_column='Address Line 1')
    address_line_2 = models.CharField(max_length=255, blank=True, null=True, db_column='Address Line 2')
    city = models.CharField(max_length=100, blank=True, null=True, db_column='City')
    state = models.CharField(max_length=10, blank=True, null=True, db_column='State')
    postal_code = models.CharField(max_length=10, blank=True, null=True, db_column='Postal Code')
    phone = models.CharField(max_length=20, blank=True, null=True, db_column='Phone')
    email = models.CharField(max_length=255, blank=True, null=True, db_column='Email')
    website = models.CharField(max_length=255, blank=True, null=True, db_column='Website')
    provider_type = models.CharField(max_length=50, blank=True, null=True, db_column='Provider Type')
    provider_status = models.CharField(max_length=50, blank=True, null=True, db_column='Provider Status')
    provider_network = models.CharField(max_length=255, blank=True, null=True, db_column='Provider Network')
    latitude = models.CharField(max_length=20, blank=True, null=True, db_column='Latitude')
    longitude = models.CharField(max_length=20, blank=True, null=True, db_column='Longitude')
    
    # Billing address fields
    billing_address_1 = models.CharField(max_length=255, blank=True, null=True, db_column='Billing Address 1')
    billing_address_2 = models.CharField(max_length=255, blank=True, null=True, db_column='Billing Address 2')
    billing_address_city = models.CharField(max_length=100, blank=True, null=True, db_column='Billing Address City')
    billing_address_postal_code = models.CharField(max_length=10, blank=True, null=True, db_column='Billing Address Postal Code')
    billing_address_state = models.CharField(max_length=10, blank=True, null=True, db_column='Billing Address State')
    billing_name = models.CharField(max_length=255, blank=True, null=True, db_column='Billing Name')
    
    # Service capabilities
    ct = models.CharField(max_length=10, blank=True, null=True, db_column='CT')
    mri_1_5t = models.CharField(max_length=10, blank=True, null=True, db_column='MRI 1.5T')
    mri_3_0t = models.CharField(max_length=10, blank=True, null=True, db_column='MRI 3.0T')
    mri_open = models.CharField(max_length=10, blank=True, null=True, db_column='MRI Open')
    xray = models.CharField(max_length=10, blank=True, null=True, db_column='Xray')
    mammo = models.CharField(max_length=10, blank=True, null=True, db_column='Mammo')
    echo = models.CharField(max_length=10, blank=True, null=True, db_column='Echo')
    ekg = models.CharField(max_length=10, blank=True, null=True, db_column='EKG')
    bone_density = models.CharField(max_length=10, blank=True, null=True, db_column='Bone Density')
    
    class Meta:
        db_table = 'providers'
        managed = False  # Use existing table
        
    def __str__(self):
        return f"{self.name} ({self.npi})"


class PPO(models.Model):
    """PPO rates and provider procedure pricing"""
    
    id = models.CharField(max_length=50, primary_key=True)
    rendering_state = models.CharField(max_length=10, blank=True, null=True, db_column='RenderingState')
    tin = models.CharField(max_length=20, blank=True, null=True, db_column='TIN')
    provider_name = models.CharField(max_length=255, blank=True, null=True)
    proc_cd = models.CharField(max_length=10, blank=True, null=True)
    modifier = models.CharField(max_length=10, blank=True, null=True)
    proc_desc = models.CharField(max_length=255, blank=True, null=True)
    proc_category = models.CharField(max_length=100, blank=True, null=True)
    rate = models.CharField(max_length=20, blank=True, null=True)
    
    class Meta:
        db_table = 'ppo'
        managed = False  # Use existing table
        
    def __str__(self):
        return f"PPO {self.id} - {self.proc_cd} (${self.rate})"


class OTA(models.Model):
    """Order Treatment Authorization rates"""
    
    id_order_primary_key = models.CharField(max_length=50, primary_key=True, db_column='ID_Order_PrimaryKey')
    cpt = models.CharField(max_length=10, blank=True, null=True, db_column='CPT')
    modifier = models.CharField(max_length=10, blank=True, null=True)
    rate = models.CharField(max_length=20, blank=True, null=True)
    
    class Meta:
        db_table = 'ota'
        managed = False  # Use existing table
        
    def __str__(self):
        return f"OTA {self.id_order_primary_key} - {self.cpt} (${self.rate})"