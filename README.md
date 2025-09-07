# Monolith.db - Medical Billing CRM Database

## Overview
The `monolith.db` database serves as the foundation for a comprehensive medical billing and provider management CRM system. This database manages the complete lifecycle of medical claims from initial provider billing through order processing and payment tracking.

## Database Statistics
- **Total Tables**: 8 core tables
- **Total Records**: 95,549 rows
- **Total Columns**: 189 fields
- **Database Type**: SQLite

## Core Tables & Relationships

### Primary Data Flow
The database follows a hierarchical structure where data flows from provider billing through order processing:

```
ProviderBill → BillLineItem (1:many)
     ↓
ProviderBill.claim_id → orders.Order_ID (1:1)
     ↓
orders.Order_ID → order_line_items.Order_ID (1:many)
     ↓
providers.PrimaryKey → orders.provider_id (1:many)
```

## Table Descriptions

### 1. ProviderBill (2,100 records)
**Purpose**: Central billing table that tracks provider bills and their processing status

**Key Fields**:
- `id` (TEXT, Primary Key) - Unique bill identifier
- `claim_id` (TEXT) - Links to orders.Order_ID
- `status` (TEXT) - Current processing status (ESCALATE, MAPPED, REVIEWED)
- `action` (TEXT) - Next action required (resolve_escalation, to_review, apply_rate)
- `last_error` (TEXT) - Last error encountered during processing
- `patient_name` (TEXT) - Patient name
- `patient_dob` (TEXT) - Patient date of birth
- `billing_provider_name` (TEXT) - Provider name
- `billing_provider_tin` (TEXT) - Provider Tax ID
- `total_charge` (REAL) - Total bill amount
- `bill_paid` (TEXT) - Payment status (Y/N)

**Status Workflow**:
- `ESCALATE` → `MAPPED` → `REVIEWED`
- Each status has corresponding actions and error tracking

### 2. BillLineItem (3,532 records)
**Purpose**: Individual line items for each provider bill

**Key Fields**:
- `id` (INTEGER, Primary Key) - Line item identifier
- `provider_bill_id` (TEXT) - Foreign key to ProviderBill.id
- `cpt_code` (TEXT) - Current Procedural Terminology code
- `modifier` (TEXT) - CPT modifier
- `units` (INTEGER) - Number of units
- `charge_amount` (REAL) - Line item charge
- `allowed_amount` (REAL) - Allowed amount after review
- `decision` (TEXT) - Review decision (pending, APPROVED)
- `reason_code` (TEXT) - Decision reason code
- `date_of_service` (TEXT) - Service date
- `place_of_service` (TEXT) - Service location code

**Relationship**: `provider_bill_id` → `ProviderBill.id` (Many-to-One)

### 3. orders (24,370 records)
**Purpose**: Main orders/claims table containing patient and order information

**Key Fields**:
- `Order_ID` (TEXT) - Primary order identifier
- `FileMaker_Record_Number` (TEXT) - Legacy FileMaker reference
- `Patient_First_Name` (TEXT) - Patient first name
- `Patient_Last_Name` (TEXT) - Patient last name
- `Patient_DOB` (TEXT) - Patient date of birth
- `Patient_Address` (TEXT) - Patient address
- `Patient_City` (TEXT) - Patient city
- `Patient_State` (TEXT) - Patient state
- `Patient_Zip` (TEXT) - Patient ZIP code
- `Referring_Physician` (TEXT) - Referring physician name
- `Referring_Physician_NPI` (TEXT) - Physician NPI number
- `Assigning_Company` (TEXT) - Insurance company
- `Assigning_Adjuster` (TEXT) - Insurance adjuster
- `Claim_Number` (TEXT) - Insurance claim number
- `Order_Type` (TEXT) - Type of medical order
- `Jurisdiction_State` (TEXT) - Legal jurisdiction
- `provider_id` (TEXT) - Foreign key to providers.PrimaryKey
- `created_at` (TIMESTAMP) - Record creation timestamp
- `FULLY_PAID` (TEXT) - Payment status
- `BILLS_REC` (INTEGER) - Bills received count

**Relationships**:
- `Order_ID` ← `ProviderBill.claim_id` (One-to-One)
- `Order_ID` → `order_line_items.Order_ID` (One-to-Many)
- `provider_id` ← `providers.PrimaryKey` (Many-to-One)

### 4. order_line_items (42,978 records)
**Purpose**: Individual line items for each order (procedures, charges)

**Key Fields**:
- `id` (TEXT) - Line item identifier
- `Order_ID` (TEXT) - Foreign key to orders.Order_ID
- `DOS` (TEXT) - Date of service
- `CPT` (TEXT) - Current Procedural Terminology code
- `Modifier` (TEXT) - CPT modifier
- `Units` (TEXT) - Number of units
- `Description` (TEXT) - Procedure description
- `Charge` (TEXT) - Charge amount
- `line_number` (TEXT) - Line item sequence
- `BR_paid` (TEXT) - Bill review paid amount
- `BR_rate` (TEXT) - Bill review rate
- `BR_date_processed` (TEXT) - Bill review processing date
- `BILLS_PAID` (INTEGER) - Bills paid count
- `BILL_REVIEWED` (TEXT) - Bill review status

**Relationship**: `Order_ID` ← `orders.Order_ID` (Many-to-One)

### 5. providers (2,562 records)
**Purpose**: Comprehensive provider information and capabilities

**Key Fields**:
- `PrimaryKey` (TEXT) - Primary provider identifier
- `Name` (TEXT) - Provider name
- `NPI` (TEXT) - National Provider Identifier
- `TIN` (TEXT) - Tax Identification Number
- `Address Line 1` (TEXT) - Primary address
- `City` (TEXT) - City
- `State` (TEXT) - State
- `Postal Code` (TEXT) - ZIP code
- `Phone` (TEXT) - Phone number
- `Email` (TEXT) - Email address
- `Provider Type` (TEXT) - Type of provider
- `Provider Status` (TEXT) - Current status
- `Latitude` (TEXT) - Geographic latitude
- `Longitude` (TEXT) - Geographic longitude

**Service Capabilities** (91 total fields):
- `CT`, `MRI 1.5T`, `MRI 3.0T`, `MRI Open`, `Xray`, `Mammo`
- `Echo`, `EKG`, `Bone Density`, `Angiography`, `Arthrogram`
- `Breast MRI`, `CT W`, `CT WO`, `MRI W`, `MRI WO`

**Relationship**: `PrimaryKey` → `orders.provider_id` (One-to-Many)

### 6. dim_proc (263 records)
**Purpose**: Master data table for medical procedures

**Key Fields**:
- `id` (INTEGER, Primary Key) - Procedure identifier
- `proc_cd` (TEXT) - Procedure code (CPT)
- `modifier` (TEXT) - Procedure modifier
- `proc_desc` (TEXT) - Procedure description
- `category` (TEXT) - Procedure category (e.g., "MRI w/o")
- `subcategory` (TEXT) - Procedure subcategory (e.g., "Abdomen/Pelvis")

**Usage**: Reference table for procedure codes and categorization

### 7. ppo (19,571 records)
**Purpose**: PPO rates and provider procedure pricing

**Key Fields**:
- `id` (TEXT) - Rate identifier
- `RenderingState` (TEXT) - State where service is rendered
- `TIN` (TEXT) - Tax Identification Number
- `provider_name` (TEXT) - Provider name
- `proc_cd` (TEXT) - Procedure code
- `modifier` (TEXT) - Procedure modifier
- `proc_desc` (TEXT) - Procedure description
- `proc_category` (TEXT) - Procedure category
- `rate` (TEXT) - PPO rate for procedure

**Usage**: Pricing reference for provider procedures

### 8. ota (173 records)
**Purpose**: Order Treatment Authorization rates

**Key Fields**:
- `ID_Order_PrimaryKey` (TEXT) - Foreign key to orders.Order_ID
- `CPT` (TEXT) - Procedure code
- `modifier` (TEXT) - Procedure modifier
- `rate` (TEXT) - Authorized rate for procedure

**Relationship**: `ID_Order_PrimaryKey` ← `orders.Order_ID` (Many-to-One)

## Data Flow & Business Process

### 1. Provider Billing Entry
- Provider submits bill → `ProviderBill` record created
- Status: `ESCALATE` (initial state)
- Action: `resolve_escalation` (if errors exist)

### 2. Bill Processing
- System maps provider information → Status: `MAPPED`
- Action: `to_review` (ready for review)
- Line items created in `BillLineItem` table

### 3. Order Creation
- `claim_id` links to `orders.Order_ID`
- Patient and claim information populated
- Provider assigned via `provider_id`

### 4. Line Item Processing
- Order line items created in `order_line_items`
- CPT codes and charges recorded
- Bill review process initiated

### 5. Rate Application
- PPO rates applied from `ppo` table
- OTA rates applied from `ota` table
- Final pricing determined

### 6. Payment Processing
- Status: `REVIEWED`
- Action: `apply_rate`
- Payment tracking via `bill_paid` fields

## Key Relationships Summary

| From Table | From Field | To Table | To Field | Relationship |
|------------|------------|----------|----------|--------------|
| ProviderBill | claim_id | orders | Order_ID | 1:1 |
| ProviderBill | id | BillLineItem | provider_bill_id | 1:many |
| orders | Order_ID | order_line_items | Order_ID | 1:many |
| orders | provider_id | providers | PrimaryKey | many:1 |
| orders | Order_ID | ota | ID_Order_PrimaryKey | 1:many |
| order_line_items | CPT | dim_proc | proc_cd | many:1 |
| ppo | TIN | providers | TIN | many:1 |

## Status Workflow

```
ProviderBill Status Flow:
ESCALATE → MAPPED → REVIEWED

Actions by Status:
- ESCALATE: resolve_escalation
- MAPPED: to_review  
- REVIEWED: apply_rate
```

## Usage Notes

- All date fields are stored as TEXT and may need conversion
- Many fields contain "None" values indicating potential data quality issues
- Geographic data available for location-based provider searches
- Comprehensive service capability tracking for provider matching
- Multiple pricing systems (PPO, OTA) for rate determination

## Database Maintenance

- Regular cleanup of error logs in `last_error` fields
- Status monitoring for stuck records
- Provider capability updates as equipment changes
- Rate updates in PPO and OTA tables
