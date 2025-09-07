# Clarity Dx Bill Review Portal

A Django-based CRM system for managing medical billing and provider management workflows.

## Features

### 🏥 **Core Functionality**
- **Provider Bill Management**: Track and process provider bills through various status workflows
- **Order Processing**: Manage medical orders and line items
- **Provider Directory**: Comprehensive provider information with service capabilities
- **Queue Management**: Three specialized processing queues

### 📊 **Dashboard**
- Real-time status distributions (unpaid vs paid bills)
- Queue counts and management cards
- Recent activity monitoring
- Interactive charts and visualizations

### 🔍 **Mapping Queue** (Enhanced)
- **Patient Search**: Last name lookup with SQL LIKE pattern matching
- **Date Range Filter**: DOS-based search with ±60 day range
- **Order Matching**: Find matching orders based on patient and date criteria
- **Bill Mapping**: Link provider bills to orders via Order_ID → claim_id mapping

### 🎯 **Processing Queues**
1. **Validation Queue**: Bills with status = 'INVALID'
2. **Mapping Queue**: Bills with status = 'UNMAPPED' 
3. **Correction Queue**: Bills with status in ('REVIEW_FLAG', 'FLAGGED')

## Database Architecture

### **Dual Database Setup**
- **users.db**: Django authentication and user management
- **monolith.db**: Medical billing data (read-only via Django models)

### **Core Tables**
- `ProviderBill` - Central billing table (2,100 records)
- `BillLineItem` - Individual line items (3,532 records)
- `orders` - Main orders/claims (24,370 records)
- `order_line_items` - Order line items (42,978 records)
- `providers` - Provider directory (2,562 records)
- `dim_proc` - Procedure codes (263 records)
- `ppo` - PPO rates (19,571 records)
- `ota` - Treatment authorization rates (173 records)

## Installation & Setup

### **Prerequisites**
- Python 3.8+
- Django 5.2.3
- SQLite3

### **Quick Start**
```bash
# Navigate to project directory
cd clarity_dx_portal

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

### **Access the Application**
- URL: http://127.0.0.1:8000/
- Default Login: `ccato` / `noisyR@ccoon53`

## Usage Guide

### **Mapping Workflow**
1. Navigate to **Mapping Queue**
2. Use search form to find orders:
   - Enter patient last name (partial matching)
   - Select date of service (±60 day range)
3. Review search results showing:
   - Patient name
   - CPT code
   - Date of service
   - Procedure description
   - Order ID
4. Click "Map to Bill" to link order to provider bill
5. System updates:
   - `claim_id` = Order_ID
   - `status` = 'MAPPED'
   - `action` = 'to_review'

### **Status Workflow**
```
ESCALATE → MAPPED → REVIEWED
    ↓        ↓         ↓
resolve_escalation → to_review → apply_rate
```

## Technical Details

### **Search Functionality**
- **Last Name**: Case-insensitive partial matching using `icontains`
- **Date Range**: Supports multiple date formats (MM/DD/YY, YYYY-MM-DD, etc.)
- **Pagination**: 20 results per page with navigation
- **Performance**: Optimized queries with proper indexing

### **Data Relationships**
- ProviderBill.claim_id → orders.Order_ID (1:1)
- ProviderBill.id → BillLineItem.provider_bill_id (1:many)
- orders.Order_ID → order_line_items.Order_ID (1:many)
- orders.provider_id → providers.PrimaryKey (many:1)

## Development

### **Project Structure**
```
clarity_dx_portal/
├── billing/                 # Main app
│   ├── models.py           # Database models
│   ├── views.py            # View logic
│   ├── urls.py             # URL routing
│   ├── routers.py          # Database routing
│   └── templates/          # HTML templates
├── clarity_dx_portal/      # Project settings
├── manage.py
└── requirements.txt
```

### **Key Files**
- `models.py`: Django models mapped to monolith.db tables
- `views.py`: Business logic and API endpoints
- `routers.py`: Database routing for dual database setup
- `templates/`: Bootstrap-based responsive UI

## Security & Performance

- **CSRF Protection**: All forms protected with CSRF tokens
- **Authentication**: Django's built-in user authentication
- **Database Routing**: Separate databases for user data and billing data
- **Query Optimization**: Efficient database queries with proper relationships
- **Input Validation**: Form validation and sanitization

## Future Enhancements

- **Validation Queue**: Bill validation workflows
- **Correction Queue**: Data correction and flagging
- **Reporting**: Advanced analytics and reporting
- **API Integration**: REST API for external systems
- **Audit Trail**: Complete activity logging
- **Bulk Operations**: Batch processing capabilities

## Support

For technical support or feature requests, contact the development team.
