from pathlib import Path

import pandas as pd

from database import supabase
from services.normalization import (
    clean_name,
    clean_email,
    clean_phone,
    clean_address,
)


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"

BATCH_SIZE = 500


# ============================================================
# REFERENCE DATA
# ============================================================

def load_reference_map():

    path = RAW / "reference_data.csv"

    if not path.exists():
        raise FileNotFoundError(
            f"Reference file not found: {path}"
        )

    df = pd.read_csv(
        path,
        dtype=str
    ).fillna("")

    reference_map = {}

    for _, row in df.iterrows():

        short_form = str(
            row.get("Short_Form", "")
        ).strip().lower()

        long_form = str(
            row.get("Long_Form", "")
        ).strip().lower()

        if short_form:
            reference_map[short_form] = long_form

    return reference_map


def import_reference_data():

    path = RAW / "reference_data.csv"

    df = pd.read_csv(
        path,
        dtype=str
    ).fillna("")

    rows = []

    for _, row in df.iterrows():

        short_form = str(
            row["Short_Form"]
        ).strip()

        long_form = str(
            row["Long_Form"]
        ).strip()

        if short_form and long_form:

            rows.append({
                "short_form": short_form,
                "long_form": long_form
            })

    if rows:

        supabase.table(
            "reference_data"
        ).upsert(
            rows,
            on_conflict="short_form"
        ).execute()

    print(
        f"Reference data imported: {len(rows)} rows"
    )


# ============================================================
# SOURCE IDS
# ============================================================

def get_source_ids():

    result = (
        supabase
        .table("sources")
        .select("id, source_name")
        .execute()
    )

    return {
        row["source_name"]: row["id"]
        for row in result.data
    }


# ============================================================
# CUSTOMER DATA
# ============================================================

def prepare_customer_rows():

    reference_map = load_reference_map()

    source_ids = get_source_ids()

    files = [
        {
            "source": "SourceA",
            "file": "core_banking.csv",
            "id": "Customer_ID",
            "name": "Name",
            "email": "Email",
            "phone": "Phone",
            "dob": "DOB",
            "address": "Address",
        },
        {
            "source": "SourceB",
            "file": "credit_card.csv",
            "id": "Cust_Ref",
            "name": "Name",
            "email": "Email",
            "phone": "Phone",
            "dob": None,
            "address": "Address",
        },
        {
            "source": "SourceC",
            "file": "loan_system.csv",
            "id": "Loan_Cust_ID",
            "name": "Name",
            "email": None,
            "phone": "Phone",
            "dob": None,
            "address": "Address",
        },
    ]

    rows = []

    for spec in files:

        source = spec["source"]

        path = RAW / spec["file"]

        print(
            f"Reading {spec['file']}..."
        )

        df = pd.read_csv(
            path,
            dtype=str
        ).fillna("")

        for _, record in df.iterrows():

            source_customer_id = str(
                record[spec["id"]]
            ).strip()

            name = (
                record[spec["name"]]
                if spec["name"]
                else ""
            )

            email = (
                record[spec["email"]]
                if spec["email"]
                else ""
            )

            phone = (
                record[spec["phone"]]
                if spec["phone"]
                else ""
            )

            address = (
                record[spec["address"]]
                if spec["address"]
                else ""
            )

            dob = (
                record[spec["dob"]]
                if spec["dob"]
                else ""
            )

            # Convert DOB to PostgreSQL DATE
            dob_value = None

            if str(dob).strip():

                parsed = pd.to_datetime(
                    dob,
                    errors="coerce"
                )

                if pd.notna(parsed):
                    dob_value = parsed.strftime(
                        "%Y-%m-%d"
                    )

            rows.append({
                "source_id": source_ids[source],

                "source_customer_id":
                    source_customer_id,

                # Original values
                "name": name or None,
                "email": email or None,
                "phone": phone or None,
                "dob": dob_value,
                "address": address or None,

                # Normalized values
                "normalized_name":
                    clean_name(name) or None,

                "normalized_email":
                    clean_email(email) or None,

                "normalized_phone":
                    clean_phone(phone) or None,

                "normalized_address":
                    clean_address(
                        address,
                        reference_map
                    ) or None,
            })

    return rows


# ============================================================
# INSERT CUSTOMERS
# ============================================================

def import_customers():

    rows = prepare_customer_rows()

    print(
        f"Prepared {len(rows)} customer records"
    )

    for start in range(
        0,
        len(rows),
        BATCH_SIZE
    ):

        batch = rows[
            start:start + BATCH_SIZE
        ]

        (
            supabase
            .table("source_customers")
            .upsert(
                batch,
                on_conflict=(
                    "source_id,source_customer_id"
                )
            )
            .execute()
        )

        print(
            f"Customers: "
            f"{min(start + BATCH_SIZE, len(rows))}"
            f"/{len(rows)}"
        )


# ============================================================
# TRANSACTIONS
# ============================================================

def import_transactions():

    path = RAW / "transaction_data.csv"

    df = pd.read_csv(
        path,
        dtype=str
    ).fillna("")

    rows = []

    for _, record in df.iterrows():

        amount = pd.to_numeric(
            record.get("Amount"),
            errors="coerce"
        )

        date = pd.to_datetime(
            record.get("Date"),
            errors="coerce"
        )

        rows.append({
            "txn_id":
                str(record.get("Txn_ID", "")).strip(),

            "account_id":
                str(record.get("Account_ID", "")).strip(),

            "amount":
                float(amount)
                if pd.notna(amount)
                else None,

            "transaction_date":
                date.strftime("%Y-%m-%d")
                if pd.notna(date)
                else None,

            "transaction_type":
                str(record.get("Type", "")).strip()
                or None,
        })

    print(
        f"Prepared {len(rows)} transactions"
    )

    for start in range(
        0,
        len(rows),
        BATCH_SIZE
    ):

        batch = rows[
            start:start + BATCH_SIZE
        ]

        (
            supabase
            .table("transactions")
            .upsert(
                batch,
                on_conflict="txn_id"
            )
            .execute()
        )

        print(
            f"Transactions: "
            f"{min(start + BATCH_SIZE, len(rows))}"
            f"/{len(rows)}"
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("MDM CUSTOMER 360 - SUPABASE IMPORT")
    print("=" * 60)

    print("\n1. Importing reference data...")
    import_reference_data()

    print("\n2. Importing source customers...")
    import_customers()

    print("\n3. Importing transactions...")
    import_transactions()

    print("\n" + "=" * 60)
    print("SUPABASE IMPORT COMPLETED")
    print("=" * 60)