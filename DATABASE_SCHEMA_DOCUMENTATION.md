# Database Schema Documentation for BR Portal CRM

## Overview
This document provides comprehensive schema information for the `monolith.db` database that will serve as the foundation for the Django-based CRM system.

**Database Inspection Date:** 2025-09-05T19:49:00.724508  
**Total Tables Found:** 6 out of 8 core tables  
**Total Rows:** 89,917  
**Total Columns:** 158  

## Core Tables Analysis

### ✅ Found Tables (6/8)
- `orders` - 24,370 rows, 29 columns
- `order_line_items` - 42,978 rows, 19 columns  
- `dim_proc` - 263 rows, 6 columns
- `ppo` - 19,571 rows, 9 columns
- `providers` - 2,562 rows, 91 columns
- `ota` - 173 rows, 4 columns

### ❌ Missing Tables (2/8)
- `providerbill` - Not found in database
- `billlineitems` - Not found in database

## Detailed Table Schemas

### 1. ORDERS Table
**Purpose:** Main orders/claims table containing patient and order information  
**Rows:** 24,370  
**Columns:** 29  

#### Key Columns:
- `Order_ID` (TEXT) - Primary identifier for orders
- `FileMaker_Record_Number` (TEXT) - Legacy FileMaker reference
- `Patient_First_Name` (TEXT) - Patient first name
- `Patient_Last_Name` (TEXT) - Patient last name
- `Patient_DOB` (TEXT) - Patient date of birth
- `Patient_Address` (TEXT) - Patient address
- `Patient_City` (TEXT) - Patient city
- `Patient_State` (TEXT) - Patient state
- `Patient_Zip` (TEXT) - Patient ZIP code
- `Patient_Injury_Date` (TEXT) - Date of injury
- `Patient_Injury_Description` (TEXT) - Description of injury
- `Referring_Physician` (TEXT) - Referring physician name
- `Referring_Physician_NPI` (TEXT) - Physician NPI number
- `Assigning_Company` (TEXT) - Insurance company
- `Assigning_Adjuster` (TEXT) - Insurance adjuster
- `Claim_Number` (TEXT) - Insurance claim number
- `Order_Type` (TEXT) - Type of medical order
- `Jurisdiction_State` (TEXT) - Legal jurisdiction
- `created_at` (TIMESTAMP) - Record creation timestamp
- `FULLY_PAID` (TEXT) - Payment status
- `BILLS_REC` (INTEGER) - Bills received count

#### Indexes:
- `idx_orders_order_id` - Index on Order_ID

#### Business Logic Insights:
- Large dataset with 24K+ orders
- Contains comprehensive patient demographic information
- Tracks insurance and legal jurisdiction details
- Has payment tracking fields

### 2. ORDER_LINE_ITEMS Table
**Purpose:** Individual line items for each order (procedures, charges)  
**Rows:** 42,978  
**Columns:** 19  

#### Key Columns:
- `id` (TEXT) - Primary key for line items
- `Order_ID` (TEXT) - Foreign key to orders table
- `DOS` (TEXT) - Date of service
- `CPT` (TEXT) - Current Procedural Terminology code
- `Modifier` (TEXT) - CPT modifier
- `Units` (TEXT) - Number of units
- `Description` (TEXT) - Procedure description
- `Charge` (TEXT) - Charge amount
- `line_number` (TEXT) - Line item sequence
- `created_at` (TIMESTAMP) - Record creation timestamp
- `updated_at` (TIMESTAMP) - Record update timestamp
- `is_active` (TEXT) - Active status
- `BR_paid` (TEXT) - Bill review paid amount
- `BR_rate` (TEXT) - Bill review rate
- `EOBR_doc_no` (TEXT) - EOBR document number
- `HCFA_doc_no` (TEXT) - HCFA document number
- `BR_date_processed` (TEXT) - Bill review processing date
- `BILLS_PAID` (INTEGER) - Bills paid count
- `BILL_REVIEWED` (TEXT) - Bill review status

#### Business Logic Insights:
- Largest table with 43K+ line items
- One-to-many relationship with orders
- Contains detailed billing and procedure information
- Tracks bill review process and payments

### 3. DIM_PROC Table (Procedure Dimension)
**Purpose:** Master data table for medical procedures  
**Rows:** 263  
**Columns:** 6  

#### Key Columns:
- `id` (INTEGER, PRIMARY KEY) - Unique procedure identifier
- `proc_cd` (TEXT) - Procedure code (CPT)
- `modifier` (TEXT) - Procedure modifier
- `proc_desc` (TEXT) - Procedure description
- `category` (TEXT) - Procedure category (e.g., "MRI w/o")
- `subcategory` (TEXT) - Procedure subcategory (e.g., "Abdomen/Pelvis")

#### Business Logic Insights:
- Reference table for procedure codes
- Categorizes procedures by type and body part
- Small but critical for data integrity

### 4. PPO Table (Preferred Provider Organization)
**Purpose:** PPO rates and provider procedure pricing  
**Rows:** 19,571  
**Columns:** 9  

#### Key Columns:
- `id` (TEXT) - Primary key
- `RenderingState` (TEXT) - State where service is rendered
- `TIN` (TEXT) - Tax Identification Number
- `provider_name` (TEXT) - Provider name
- `proc_cd` (TEXT) - Procedure code
- `modifier` (TEXT) - Procedure modifier
- `proc_desc` (TEXT) - Procedure description
- `proc_category` (TEXT) - Procedure category
- `rate` (TEXT) - PPO rate for procedure

#### Business Logic Insights:
- Large dataset with 19K+ rate records
- Links providers to procedure rates
- Critical for pricing and billing calculations

### 5. PROVIDERS Table
**Purpose:** Comprehensive provider information and capabilities  
**Rows:** 2,562  
**Columns:** 91 (Most complex table)

#### Key Columns (Selected Important Ones):
- `Name` (TEXT) - Provider name
- `NPI` (TEXT) - National Provider Identifier
- `TIN` (TEXT) - Tax Identification Number
- `Address Line 1` (TEXT) - Primary address
- `Address Line 2` (TEXT) - Secondary address
- `City` (TEXT) - City
- `State` (TEXT) - State
- `Postal Code` (TEXT) - ZIP code
- `Phone` (TEXT) - Phone number
- `Email` (TEXT) - Email address
- `Website` (TEXT) - Website URL
- `Provider Type` (TEXT) - Type of provider
- `Provider Status` (TEXT) - Current status
- `ServicesProvided` (TEXT) - Available services

#### Service Capability Columns:
- `CT` (TEXT) - CT scan capability
- `MRI 1.5T` (TEXT) - 1.5T MRI capability
- `MRI 3.0T` (TEXT) - 3.0T MRI capability
- `MRI Open` (TEXT) - Open MRI capability
- `Xray` (TEXT) - X-ray capability
- `Mammo` (TEXT) - Mammography capability
- `Echo` (TEXT) - Echocardiography capability
- `EKG` (TEXT) - EKG capability
- `Bone Density` (TEXT) - Bone density testing
- `Angiography` (TEXT) - Angiography capability
- `Arthrogram` (TEXT) - Arthrogram capability
- `Breast MRI` (TEXT) - Breast MRI capability
- `CT W` (TEXT) - CT with contrast
- `CT WO` (TEXT) - CT without contrast
- `MRI W` (TEXT) - MRI with contrast
- `MRI WO` (TEXT) - MRI without contrast

#### Geographic Columns:
- `Latitude` (TEXT) - Geographic latitude
- `Longitude` (TEXT) - Geographic longitude
- `lat` (TEXT) - Alternative latitude field
- `lon` (TEXT) - Alternative longitude field
- `g_lat` (TEXT) - Google latitude
- `g_lon` (TEXT) - Google longitude

#### Business Logic Insights:
- Most complex table with 91 columns
- Contains comprehensive provider information
- Tracks service capabilities and equipment
- Includes geographic data for location-based services
- Has billing and contract information

### 6. OTA Table (Order Treatment Authorization)
**Purpose:** Treatment authorization rates for specific orders  
**Rows:** 173  
**Columns:** 4  

#### Key Columns:
- `ID_Order_PrimaryKey` (TEXT) - Foreign key to orders
- `CPT` (TEXT) - Procedure code
- `modifier` (TEXT) - Procedure modifier
- `rate` (TEXT) - Authorized rate for procedure

#### Business Logic Insights:
- Small but important table
- Links specific orders to authorized rates
- Used for treatment authorization process

## Data Relationships

### Primary Relationships:
1. **Orders → Order_Line_Items**: One-to-many (Order_ID)
2. **Orders → OTA**: One-to-many (ID_Order_PrimaryKey)
3. **Order_Line_Items → DIM_PROC**: Many-to-one (CPT code)
4. **PPO → Providers**: Many-to-one (TIN)
5. **PPO → DIM_PROC**: Many-to-one (proc_cd)

### Key Business Flows:
1. **Order Creation**: Orders contain patient and claim information
2. **Line Item Processing**: Each order can have multiple line items (procedures)
3. **Provider Matching**: Orders are matched to providers based on location and capabilities
4. **Rate Determination**: PPO rates and OTA rates determine pricing
5. **Bill Review**: Line items go through bill review process

## Data Quality Insights

### Strengths:
- Large, comprehensive datasets
- Good geographic coverage (providers table)
- Detailed procedure and billing information
- Timestamp tracking for audit trails

### Areas of Concern:
- Missing `providerbill` and `billlineitems` tables
- Many TEXT fields that could be better typed
- Some fields contain "None" values indicating potential data quality issues
- Date fields stored as TEXT instead of proper date types

## Recommendations for Django CRM

### 1. Model Design:
- Create separate models for each table
- Use proper Django field types (DateField, DecimalField, etc.)
- Implement proper foreign key relationships
- Add validation for data integrity

### 2. Key Features to Build:
- **Order Management**: Complete order lifecycle management
- **Provider Directory**: Searchable provider database with capabilities
- **Billing System**: Line item processing and rate calculations
- **Patient Management**: Patient information and history
- **Reporting**: Analytics on orders, providers, and billing

### 3. Data Migration Considerations:
- Convert TEXT date fields to proper DateField/DateTimeField
- Handle "None" values appropriately
- Implement data validation rules
- Consider data cleaning for existing records

### 4. Performance Considerations:
- Index frequently queried fields
- Consider pagination for large tables (orders, order_line_items)
- Implement caching for reference data (dim_proc, providers)
- Use database views for complex queries

## Next Steps

1. **Django Project Setup**: Create Django project with proper structure
2. **Model Creation**: Build Django models based on this schema
3. **Data Migration**: Create migration scripts to import existing data
4. **Admin Interface**: Build Django admin for data management
5. **API Development**: Create REST APIs for frontend integration
6. **Frontend Development**: Build user interface for CRM functionality

This schema provides a solid foundation for building a comprehensive medical billing and provider management CRM system.
