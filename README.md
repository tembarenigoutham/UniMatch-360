# UniMatch-360
## Unified Customer 360 & Golden Record Master Data Management (MDM)

UniMatch-360 is a Master Data Management platform that consolidates customer information from Core Banking, Credit Card, and Loan systems into a unified, trusted Golden Record.

### Key Features

- **Customer Matching:** Exact email matching, exact phone matching, and fuzzy name-and-address matching.
- **Data Normalization:** Standardizes customer names, emails, phone numbers, and addresses.
- **Golden Record Creation:** Creates a unified customer profile using configurable field-level survivorship rules.
- **Customer 360 Dashboard:** Displays Golden Records, source records, match explanations, and transaction history.
- **Transaction Linking:** Connects transactions to their corresponding Golden Records.
- **Data Stewardship:** Supports manual corrections with provenance tracking.
- **Audit Trail:** Records changes, previous values, new values, reasons, and timestamps.
- **Bulk CSV Import:** Supports ingestion of multiple customer records.
- **REST APIs:** Provides FastAPI endpoints and interactive Swagger documentation.

### Technology Stack

**Backend:** Python, FastAPI, Pydantic  
**Database:** Supabase, PostgreSQL  
**Data Processing:** Pandas, NumPy, RapidFuzz  
**Frontend:** HTML, CSS, JavaScript  
**Testing:** Pytest  
**Version Control:** Git and GitHub

### Project Structure

```text
UniMatch-360/
├── config/
├── data/
├── frontend/
├── services/
├── src/
├── tests/
├── api.py
├── cleaning.py
├── database.py
├── import_data.py
├── matching.py
├── requirements.txt
└── README.md
```

### Prerequisites

- Python 3.11
- Git
- A Supabase project with the required database schema and credentials

### Setup and Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/tembarenigoutham/UniMatch-360.git
   cd UniMatch-360
   ```

2. Create and activate a virtual environment in the project root:

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Configure the Supabase credentials in a local `.env` file using the variable names expected by `database.py`.

5. Start the application:

   ```bash
   uvicorn api:app --reload
   ```

6. Open the application and API documentation:

   - Application: http://127.0.0.1:8000/
   - Swagger documentation: http://127.0.0.1:8000/docs
   - Health check: http://127.0.0.1:8000/api/health

**Important:** Run the application from the directory containing `api.py`. If Python is not installed or recognized on your system, install Python 3.11 and ensure it is added to PATH.

Never commit `.env` files or secret keys to GitHub.

### Project Goal

UniMatch-360 provides a single, traceable view of each customer by combining data from multiple systems, explaining matching decisions, and preserving the provenance of mastered customer information.

**Team:** BNP-BLR-Team-29
