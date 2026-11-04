# Unified Customer 360 & Golden Record MDM

## Project Overview

**Unified Customer 360 & Golden Record MDM** is a Master Data Management (MDM) platform that consolidates customer information from multiple source systems into a trusted **Golden Record**.

The system:

- Ingests customer data from Core Banking, Credit Card, and Loan systems
- Normalizes customer attributes before matching
- Performs exact and fuzzy entity resolution
- Groups source records belonging to the same real-world customer
- Creates a field-level Golden Record using survivorship rules
- Maintains source lineage and match explanations
- Links transactions to Golden IDs
- Provides a Customer 360 dashboard
- Supports manual Data Steward overrides
- Preserves Data Steward provenance
- Maintains an audit trail for governed changes
- Supports single-record and bulk CSV ingestion
- Provides FastAPI/Swagger APIs

---

# 1. Main MDM Flow

```text
Source Systems
     |
     v
Data Ingestion
     |
     v
Normalization
     |
     v
Entity Resolution
 ┌───┼──────────────┐
 |   |              |
Email Phone    Fuzzy Name +
Match Match     Address Match
 └───┼──────────────┘
     |
     v
Matched Customer Groups
     |
     v
Field-Level Survivorship
     |
     v
Golden Records
     |
 ┌───┼───────────────┐
 |   |               |
 v   v               v
360 Transactions   Audit
View                Trail
 |
 v
Data Stewardship
```

---

# 2. Key Features

## Customer Matching

The matching engine supports:

1. Exact Email matching
2. Exact Phone matching
3. Fuzzy Name + Address matching

Fuzzy matching uses RapidFuzz with a configured threshold of **85%**.

Each resolved relationship stores:

- Match method
- Match score
- Source record
- Golden Record relationship

Example:

```text
Direct Match — Email
100%
```

or:

```text
Fuzzy Match — Name + Address
87%
```

---

## Data Normalization

Customer values are normalized before matching.

### Name

```text
"  john doe  "
        ↓
"John Doe"
```

### Email

```text
" JOHN@EXAMPLE.COM "
        ↓
"john@example.com"
```

### Phone

Non-numeric characters are removed:

```text
"+91-98765-43210"
        ↓
"919876543210"
```

### Address

Whitespace and configured reference-data abbreviations are standardized.

Reference data can contain mappings such as:

```text
St.  -> Street
Rd.  -> Road
```

---

# 3. Golden Record

A Golden Record represents the mastered identity of a real-world customer.

Example:

```text
GOLD_001777

Name:    Test Customer
Email:   test10001@example.com
Phone:   9003703482
DOB:     2000-01-16
Address: Different address
```

The Golden Record retains the source associated with each surviving field:

```text
name_source
email_source
phone_source
address_source
dob_source
```

Therefore, the system can answer:

> Where did each Golden Record value come from?

---

# 4. Field-Level Survivorship

Survivorship is performed **within the matched customer group**.

Current trust hierarchy:

```json
{
  "phone": ["SourceA", "SourceB", "SourceC"],
  "email": ["SourceB", "SourceA", "SourceC"],
  "name": ["SourceA", "SourceB", "SourceC"],
  "address": ["SourceB", "SourceA", "SourceC"],
  "dob": ["SourceA", "SourceB", "SourceC"]
}
```

This means the highest-trusted source can be different for each attribute.

For example:

```text
Name     -> SourceA
Email    -> SourceB
Phone    -> SourceA
Address  -> SourceB
DOB      -> SourceA
```

The Golden Record is therefore constructed **field by field**, rather than copying one complete source record.

---

# 5. Data Stewardship

Data Stewardship provides a human-in-the-loop governance mechanism.

Automated matching and survivorship handle normal cases, but a Data Steward can manually verify or correct a Golden Record attribute.

Example:

```text
Automated Golden Record

Phone: 9003703482
Source: SourceA
```

A Data Steward verifies the customer's phone and changes it to:

```text
Phone: 9999999999
Source: DATA_STEWARD
```

`DATA_STEWARD` is **not another source system**. It represents a governed human override.

The original source record remains unchanged.

The system also records:

- Golden ID
- Changed field
- Previous value
- New value
- Changed by
- Reason
- Timestamp

This provides traceability and governance.

---

# 6. Customer 360

The Customer 360 interface provides a unified view of a mastered customer.

It includes:

- Golden Record
- Field-level source/provenance
- Source Records
- Match method
- Match score
- Transaction History
- Manual Golden Record editing
- Audit history

Example relationship:

```text
Core Banking
     |
Credit Card -----> GOLD_001777
     |                 |
Loan System           |
                      v
               Customer 360
```

---

# 7. Transaction Linking

Transactions are linked to Golden Records through source customer/account relationships.

```text
Transaction
     |
     v
Source Customer
     |
     v
Golden ID
     |
     v
Customer 360
```

This allows transaction history to be displayed for the mastered customer.

The original processed dataset contained:

```text
Transactions:        6,841
Linked Transactions: 6,841
Linkage Rate:        100%
```

Counts can increase when additional demo/test data is uploaded.

---

# 8. Bulk CSV Import

The application supports bulk customer ingestion.

CSV records are processed through the MDM flow:

```text
CSV Upload
    |
    v
Source Customer
    |
    v
Normalization
    |
    v
Matching
    |
    +---- Existing Golden Record
    |
    +---- New Golden Record
```

A bulk record that matches an existing customer is attached to that Golden Record rather than creating a duplicate customer.

---

# 9. Technology Stack

## Backend

- Python
- FastAPI
- Pydantic
- Supabase
- PostgreSQL
- python-dotenv

## Data Processing

- Pandas
- NumPy
- RapidFuzz

## Frontend

- HTML
- CSS
- JavaScript

## Testing

- Pytest

## Version Control

- Git
- GitHub

---

# 10. Project Structure

```text
team-29/
└── backend/
    ├── .env
    ├── database.py
    ├── import_data.py
    ├── requirements.txt
    ├── api.py
    │
    ├── config/
    │   └── trust_hierarchy.json
    │
    ├── data/
    │   ├── raw/
    │   │   ├── core_banking.csv
    │   │   ├── credit_card.csv
    │   │   ├── loan_system.csv
    │   │   ├── reference_data.csv
    │   │   └── transaction_data.csv
    │   │
    │   └── output/
    │       ├── golden_records.csv
    │       ├── match_results.csv
    │       ├── normalized_customers.csv
    │       └── transactions_with_golden_id.csv
    │
    ├── services/
    │   ├── __init__.py
    │   └── normalization.py
    │
    ├── src/
    │   ├── matching_fixed.py
    │   ├── matching_supabase.py
    │   ├── pipeline.py
    │   ├── survivorship_engine.py
    │   ├── survivorship_supabase.py
    │   └── transaction_linker_supabase.py
    │
    ├── tests/
    │   └── test_pipeline.py
    │
    └── frontend/
        ├── index.html
        └── static/
            ├── css/
            │   └── styles.css
            └── js/
                └── app.js
```

---

# 11. Prerequisites

Install:

- Python 3.11
- Git
- A Supabase project

Recommended:

- Windows 10/11, Linux, or macOS
- 8 GB RAM or more

---

# 12. Clone the Repository

Replace `<repository-url>` with the team's GitHub repository URL.

```bash
git clone <repository-url>
cd team-29
cd backend
```

The important point is:

```text
team-29/
└── backend/
```

There should **not** be another nested `backend/backend` directory.

---

# 13. Create a Python Virtual Environment

From the `backend` directory:

### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use:

```powershell
venv\Scripts\activate
```

### Linux/macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

---

# 14. Install Dependencies

```bash
pip install -r requirements.txt
```

If pip is outdated:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

# 15. Configure Supabase

Create:

```text
backend/.env
```

Add:

```env
SUPABASE_URL=YOUR_SUPABASE_PROJECT_URL
SUPABASE_KEY=YOUR_SUPABASE_KEY
```

Do **not** commit `.env` to GitHub.

The application reads these values through `database.py`.

---

# 16. Database Setup

Create the following tables in the Supabase SQL Editor:

```text
sources
source_customers
match_links
golden_records
golden_record_sources
transactions
audit_logs
reference_data
```

The database relationships are:

```text
sources
   |
   v
source_customers
   |
   +------> match_links
   |
   +------> golden_record_sources
                  |
                  v
            golden_records
                  |
                  v
             transactions

audit_logs
reference_data
```

The application expects the schema described by the tables above.

If the project database is already populated, **do not recreate or clear these tables**.

---

# 17. Initial Data Processing

Use this section only when setting up a **fresh/empty database**.

From:

```text
backend/
```

### Step 1 — Import source data

```powershell
python import_data.py
```

This loads the source CSV data and reference data.

### Step 2 — Run matching

```powershell
python src/matching_supabase.py
```

This creates match relationships using:

- Exact email
- Exact phone
- Fuzzy name + address

### Step 3 — Build Golden Records

```powershell
python src/survivorship_supabase.py
```

This creates the Golden Records using the configured trust hierarchy.

### Step 4 — Link transactions

```powershell
python src/transaction_linker_supabase.py
```

This maps transactions to Golden IDs.

### Important

These commands rebuild/refresh master-data results.

**Do not run them during a normal application restart or during a jury demonstration.**

In particular, the survivorship process can rebuild Golden Records and therefore should not be casually rerun after Data Steward changes.

---

# 18. Start the Application

For normal use, only the FastAPI server needs to be started.

From:

```text
team-29/backend/
```

run:

```powershell
uvicorn api:app --reload
```

You should see something similar to:

```text
Uvicorn running on http://127.0.0.1:8000
```

---

# 19. Open the Application

### Customer 360 UI

```text
http://127.0.0.1:8000/
```

### Swagger API documentation

```text
http://127.0.0.1:8000/docs
```

### Health check

```text
http://127.0.0.1:8000/api/health
```

The health endpoint can be used to confirm that the backend is running.

---

# 20. Normal Restart Procedure

If the database has already been populated and you simply restarted your computer:

```powershell
cd C:\Users\<username>\OneDrive\Desktop\team-29\backend
```

Activate the environment:

```powershell
venv\Scripts\activate
```

Start the server:

```powershell
uvicorn api:app --reload
```

Then open:

```text
http://127.0.0.1:8000/
```

### You normally do NOT need to rerun:

```text
import_data.py
matching_supabase.py
survivorship_supabase.py
transaction_linker_supabase.py
```

The processed data is already stored in Supabase.

---

# 21. API Endpoints

## Health

```http
GET /api/health
```

## Search customers

```http
GET /api/customers/search?q=Test
```

## List customers

```http
GET /api/customers
```

Supports pagination using:

```text
limit
offset
```

## Customer 360

```http
GET /api/customers/{golden_id}
```

## Customer transactions

```http
GET /api/customers/{golden_id}/transactions
```

## Customer source records

```http
GET /api/customers/{golden_id}/sources
```

## Dashboard statistics

```http
GET /api/dashboard/stats
```

## Update Golden Record

```http
PATCH /api/customers/{golden_id}
```

## Bulk Golden Record update

```http
PATCH /api/customers/bulk-update
```

## Audit records

```http
GET /api/audit
```

## Single customer upload

```http
POST /api/customers/upload
```

## CSV import

```http
POST /api/import/csv
```

---

# 22. Example Data Steward Update

A Data Steward can update a Golden Record field.

Example:

```json
{
  "phone": "9999999999",
  "changed_by": "Data Steward",
  "reason": "Verified by Data Steward"
}
```

The Golden Record becomes:

```text
phone = 9999999999
phone_source = DATA_STEWARD
```

The original source record remains unchanged.

The action is recorded in `audit_logs`.

---

# 23. Testing

Run the test suite from `backend/`:

```powershell
pytest
```

For a quick syntax check of the FastAPI application:

```powershell
python -m py_compile api.py
```

---

# 24. Demo Flow

For a jury demonstration, use this order:

### 1. Dashboard

Show:

- Golden Records
- Matched Groups
- Match Links
- Source Customers
- Transactions
- Linkage Rate

### 2. Search Customer

Search for a known Golden Record such as:

```text
Test Customer
```

### 3. Golden Record

Show:

- Name
- Email
- Phone
- DOB
- Address
- Field-level source badges

### 4. Source Records

Show that multiple source records can belong to one Golden ID.

### 5. Match Explanation

Show:

```text
Direct Match — Email
100%
```

or:

```text
Direct Match — Phone
100%
```

or:

```text
Fuzzy Match — Name + Address
```

### 6. Transactions

Show transactions linked to the Golden ID.

### 7. Data Stewardship

Edit a Golden Record field and demonstrate:

```text
DATA_STEWARD
```

provenance.

### 8. Audit

Show:

- Previous value
- New value
- Changed by
- Reason
- Timestamp

### 9. Bulk Upload

Upload a CSV and demonstrate that a record can:

```text
Match an existing Golden Record
```

or:

```text
Create a new Golden Record
```

---

# 25. Example Demo Customer

For testing, the project can use multiple source records representing one customer.

Example:

### SourceA

```text
Source Customer ID: DEMO_A_PRIYA001
Name: Priya Sharma
Email: priya.sharma@gmail.com
Phone: 9876501234
DOB: 1999-08-21
Address: 45 Anna Nagar, Salem
```

### SourceB

```text
Source Customer ID: DEMO_B_PRIYA001
Name: Priya S
Email: priya.sharma@gmail.com
Phone: 9876501234
DOB: 1999-08-21
Address: 45 Anna Nagar Salem
```

### SourceC

```text
Source Customer ID: DEMO_C_PRIYA001
Name: Priya Sharma
Email: PRIYA.SHARMA@GMAIL.COM
Phone: +91 98765 01234
DOB: 1999-08-21
Address: 45 Anna Nagar, Salem
```

These records demonstrate normalization and matching.

---

# 26. Important Operational Notes

### Do not expose credentials

Never commit:

```text
.env
```

or the Supabase secret key.

### Do not rebuild the database for a normal restart

Starting the API does not require re-running the MDM pipeline.

### Do not casually rerun survivorship

The survivorship process rebuilds Golden Records. After Data Steward overrides or demo modifications, rerunning it can change the mastered state.

### Demo data

Additional manual test records can increase the Golden Record/source-customer counts shown on the dashboard.

---

# 27. Troubleshooting

## `ModuleNotFoundError`

Activate the virtual environment and install dependencies:

```powershell
venv\Scripts\activate
pip install -r requirements.txt
```

## Supabase connection error

Check:

```text
backend/.env
```

and verify:

```env
SUPABASE_URL=...
SUPABASE_KEY=...
```

Do not put quotes around the values unless required by your environment.

## Port 8000 already in use

Stop the existing Uvicorn process or use another port:

```powershell
uvicorn api:app --reload --port 8001
```

Then open:

```text
http://127.0.0.1:8001/
```

## UI does not load

First verify:

```text
http://127.0.0.1:8000/api/health
```

Then check the Uvicorn terminal for errors.

## Golden Record missing after upload

Check whether the source record was inserted and whether the upload endpoint completed MDM processing. Do not immediately rerun the complete survivorship pipeline.

---

# 28. Design Principles

## Single Version of Truth

One resolved real-world customer receives one Golden ID.

## Explainability

Matching relationships retain their method and score.

## Field-Level Survivorship

Different customer attributes can come from different trusted sources.

## Source Lineage

Original source records remain traceable to the Golden Record.

## Human-in-the-Loop Governance

Data Stewards can correct mastered data without changing the original source record.

## Auditability

Manual changes are recorded with their context.

## Modular Architecture

The system separates:

```text
Ingestion
Normalization
Matching
Survivorship
Transaction Linking
API
Frontend
Testing
```

---

# 29. Quick Start — Already Configured Project

If another team member receives an already configured copy of the project and the Supabase database is already populated, they only need:

```powershell
cd team-29\backend
venv\Scripts\activate
pip install -r requirements.txt
uvicorn api:app --reload
```

Then open:

```text
http://127.0.0.1:8000/
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

**Do not run the initial data-processing scripts unless the database is empty and you intentionally want to rebuild the MDM data.**

---

# 30. Project Summary

```text
                 UNIFIED CUSTOMER 360
                         |
        ┌────────────────┼────────────────┐
        |                |                |
   Core Banking     Credit Card     Loan System
        |                |                |
        └────────────────┼────────────────┘
                         |
                  Normalization
                         |
                 Entity Resolution
                         |
                 Customer Matching
                         |
                  Survivorship
                         |
                  Golden Record
                         |
        ┌────────────────┼────────────────┐
        |                |                |
    Customer 360     Transactions      Audit
        |                                 |
        └──────── Data Steward ────────────┘
```

**Team:** BNP-BLR-Team-29

**Project:** Unified Customer 360 & Golden Record MDM
