import json
import re
from rapidfuzz import fuzz
from services.normalization import (
    clean_name,
    clean_email,
    clean_phone,
    clean_address
)
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import csv
import io
from datetime import datetime
from database import supabase
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="MDM Customer 360 API",
    description=(
        "Unified Customer 360 API powered by "
        "Supabase and MDM Golden Records"
    ),
    version="1.0.0"
)

# ============================================================
# FRONTEND
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

app.mount(
    "/static",
    StaticFiles(
        directory=FRONTEND_DIR / "static"
    ),
    name="static"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# REQUEST MODELS
# ============================================================

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    dob: Optional[str] = None
    changed_by: str = "data_steward"
    reason: str = "Manual data stewardship update"


class BulkCustomerUpdate(BaseModel):
    golden_ids: list[str]
    field: str
    value: str
    changed_by: str = "data_steward"
    reason: str = "Bulk data stewardship update"


# ============================================================
# DATA STEWARDSHIP
# ============================================================

DATA_STEWARD_SOURCE = "DATA_STEWARD"

FIELD_SOURCE_MAP = {
    "name": "name_source",
    "email": "email_source",
    "phone": "phone_source",
    "address": "address_source",
    "dob": "dob_source"
}

# ============================================================
# DASHBOARD STATISTICS
# ============================================================

@app.get("/api/dashboard/stats")
def get_dashboard_stats():

    # --------------------------------------------------------
    # Exact count helper
    # Supabase normally limits select() results to 1000 rows.
    # Using count="exact", head=True gives the real count.
    # --------------------------------------------------------

    def exact_count(table_name: str) -> int:
        response = (
            supabase
            .table(table_name)
            .select("id", count="exact", head=True)
            .execute()
        )

        return response.count or 0

    # --------------------------------------------------------
    # Golden Records
    # --------------------------------------------------------

    golden_records_count = exact_count("golden_records")

    # --------------------------------------------------------
    # Source Customers
    # --------------------------------------------------------

    source_customers_count = exact_count("source_customers")

    # --------------------------------------------------------
    # Match Links
    # --------------------------------------------------------

    match_links_count = exact_count("match_links")

    # --------------------------------------------------------
    # Matched Groups
    # match_group_size > 1
    # --------------------------------------------------------

    matched_groups_response = (
        supabase
        .table("golden_records")
        .select("id", count="exact", head=True)
        .gt("match_group_size", 1)
        .execute()
    )

    matched_groups_count = matched_groups_response.count or 0

    # --------------------------------------------------------
    # Singleton Groups
    # match_group_size = 1
    # --------------------------------------------------------

    singleton_groups_response = (
        supabase
        .table("golden_records")
        .select("id", count="exact", head=True)
        .eq("match_group_size", 1)
        .execute()
    )

    singleton_groups_count = singleton_groups_response.count or 0

    # --------------------------------------------------------
    # Transactions
    # --------------------------------------------------------

    transactions_count = exact_count("transactions")

    # --------------------------------------------------------
    # Unlinked Transactions
    # --------------------------------------------------------

    unlinked_response = (
        supabase
        .table("transactions")
        .select("id", count="exact", head=True)
        .is_("golden_id", "null")
        .execute()
    )

    unlinked_transactions_count = unlinked_response.count or 0

    # --------------------------------------------------------
    # Linked Transactions
    # --------------------------------------------------------

    linked_transactions_count = (
        transactions_count - unlinked_transactions_count
    )

    # --------------------------------------------------------
    # Linkage Rate
    # --------------------------------------------------------

    if transactions_count > 0:
        linkage_rate = (
            linked_transactions_count / transactions_count
        ) * 100
    else:
        linkage_rate = 0

    # --------------------------------------------------------
    # Final Response
    # --------------------------------------------------------

    return {
        "golden_records": golden_records_count,

        "source_customers": source_customers_count,

        "matched_groups": matched_groups_count,

        "singleton_groups": singleton_groups_count,

        "match_links": match_links_count,

        "transactions": transactions_count,

        "linked_transactions": linked_transactions_count,

        "unlinked_transactions": unlinked_transactions_count,

        "linkage_rate": round(linkage_rate, 2)
    }
# ============================================================
# HEALTH
# ============================================================
@app.get("/", include_in_schema=False)
def root():

    return FileResponse(
        FRONTEND_DIR / "index.html"
    )


@app.get("/api/health")
def health():

    try:

        response = (
            supabase
            .table("golden_records")
            .select("id")
            .limit(1)
            .execute()
        )

        return {
            "status": "healthy",
            "database": "connected"
        }

    except Exception as e:

        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }


# ============================================================
# CUSTOMER SEARCH
# ============================================================

@app.get("/api/customers/search")
def search_customers(
    q: str = Query(
        ...,
        min_length=1,
        description="Search by name, email, phone or Golden ID"
    )
):

    search_term = q.strip()

    # --------------------------------------------------------
    # Search Golden ID
    # --------------------------------------------------------

    golden_response = (
        supabase
        .table("golden_records")
        .select(
            "golden_id,name,email,phone,address,dob,"
            "name_source,email_source,phone_source,"
            "address_source,dob_source,"
            "representative_source,"
            "match_group_size"
        )
        .ilike(
            "golden_id",
            f"%{search_term}%"
        )
        .limit(20)
        .execute()
    )

    results = golden_response.data or []

    # --------------------------------------------------------
    # Search Name
    # --------------------------------------------------------

    if len(results) < 20:

        response = (
            supabase
            .table("golden_records")
            .select(
                "golden_id,name,email,phone,address,dob,"
                "name_source,email_source,phone_source,"
                "address_source,dob_source,"
                "representative_source,"
                "match_group_size"
            )
            .ilike(
                "name",
                f"%{search_term}%"
            )
            .limit(20)
            .execute()
        )

        existing_ids = {
            row["golden_id"]
            for row in results
        }

        for row in response.data or []:

            if row["golden_id"] not in existing_ids:

                results.append(row)

    # --------------------------------------------------------
    # Search Email
    # --------------------------------------------------------

    if len(results) < 20:

        response = (
            supabase
            .table("golden_records")
            .select(
                "golden_id,name,email,phone,address,dob,"
                "name_source,email_source,phone_source,"
                "address_source,dob_source,"
                "representative_source,"
                "match_group_size"
            )
            .ilike(
                "email",
                f"%{search_term}%"
            )
            .limit(20)
            .execute()
        )

        existing_ids = {
            row["golden_id"]
            for row in results
        }

        for row in response.data or []:

            if row["golden_id"] not in existing_ids:

                results.append(row)

    # --------------------------------------------------------
    # Search Phone
    # --------------------------------------------------------

    if len(results) < 20:

        response = (
            supabase
            .table("golden_records")
            .select(
                "golden_id,name,email,phone,address,dob,"
                "name_source,email_source,phone_source,"
                "address_source,dob_source,"
                "representative_source,"
                "match_group_size"
            )
            .ilike(
                "phone",
                f"%{search_term}%"
            )
            .limit(20)
            .execute()
        )

        existing_ids = {
            row["golden_id"]
            for row in results
        }

        for row in response.data or []:

            if row["golden_id"] not in existing_ids:

                results.append(row)

    return {
        "query": search_term,
        "count": len(results),
        "customers": results[:20]
    }


# ============================================================
# CUSTOMER LIST
# ============================================================

@app.get("/api/customers")
def get_customers(
    limit: int = Query(
        20,
        ge=1,
        le=100
    ),
    offset: int = Query(
        0,
        ge=0
    )
):

    response = (
        supabase
        .table("golden_records")
        .select(
            "golden_id,name,email,phone,"
            "address,dob,match_group_size"
        )
        .range(
            offset,
            offset + limit - 1
        )
        .execute()
    )

    return {
        "count": len(response.data or []),
        "offset": offset,
        "limit": limit,
        "customers": response.data or []
    }


# ============================================================
# CUSTOMER 360
# ============================================================

@app.get("/api/customers/{golden_id}")
def get_customer_360(
    golden_id: str
):

    # --------------------------------------------------------
    # Golden Record
    # --------------------------------------------------------

    golden_response = (
        supabase
        .table("golden_records")
        .select("*")
        .eq(
            "golden_id",
            golden_id
        )
        .limit(1)
        .execute()
    )

    golden_records = (
        golden_response.data or []
    )

    if not golden_records:

        raise HTTPException(
            status_code=404,
            detail="Golden customer not found"
        )

    golden = golden_records[0]

    golden_db_id = golden["id"]

    # --------------------------------------------------------
    # Source Records
    # --------------------------------------------------------

    source_links_response = (
        supabase
        .table("golden_record_sources")
        .select(
            "source_customer_id,"
            "match_method,"
            "match_score"
        )
        .eq(
            "golden_record_id",
            golden_db_id
        )
        .execute()
    )

    source_links = (
        source_links_response.data or []
    )

    source_customer_ids = [
        row["source_customer_id"]
        for row in source_links
    ]

    source_records = []

    if source_customer_ids:

        customers_response = (
            supabase
            .table("source_customers")
            .select("*")
            .in_(
                "id",
                source_customer_ids
            )
            .execute()
        )

        customer_map = {
            row["id"]: row
            for row in (
                customers_response.data or []
            )
        }

        for link in source_links:

            customer = customer_map.get(
                link["source_customer_id"]
            )

            if customer:

                source_records.append({
                    **customer,
                    "match_method":
                        link["match_method"],
                    "match_score":
                        link["match_score"]
                })


    # --------------------------------------------------------
    # Transactions
    # --------------------------------------------------------

    transaction_response = (
        supabase
        .table("transactions")
        .select(
            "txn_id,account_id,amount,"
            "transaction_date,"
            "transaction_type"
        )
        .eq(
            "golden_id",
            golden_id
        )
        .order(
            "transaction_date",
            desc=True
        )
        .execute()
    )

    transactions = (
        transaction_response.data or []
    )

    # --------------------------------------------------------
    # Transaction Summary
    # --------------------------------------------------------

    total_transaction_amount = sum(
        float(txn["amount"] or 0)
        for txn in transactions
    )

    transaction_count = len(
        transactions
    )

    # --------------------------------------------------------
    # Product / Source Summary
    # --------------------------------------------------------

    source_summary = {}

    for record in source_records:

        source_name = record.get(
            "source_id"
        )

        source_summary[str(
            source_name
        )] = source_summary.get(
            str(source_name),
            0
        ) + 1

    # --------------------------------------------------------
    # Customer 360 Response
    # --------------------------------------------------------

    return {

        "golden_record": golden,

        "source_records": {
            "count": len(source_records),
            "records": source_records
        },

        "transactions": {
            "count": transaction_count,
            "total_amount":
                round(
                    total_transaction_amount,
                    2
                ),
            "records": transactions
        },

        "summary": {
            "golden_id": golden_id,
            "source_record_count":
                len(source_records),
            "transaction_count":
                transaction_count,
            "total_transaction_amount":
                round(
                    total_transaction_amount,
                    2
                ),
            "match_group_size":
                golden.get(
                    "match_group_size"
                )
        }
    }



# ============================================================
# UPDATE SINGLE GOLDEN RECORD
# ============================================================

@app.patch("/api/customers/{golden_id}")
def update_customer(
    golden_id: str,
    update: CustomerUpdate
):

    # --------------------------------------------------------
    # Find Golden Record
    # --------------------------------------------------------

    response = (
        supabase
        .table("golden_records")
        .select("*")
        .eq(
            "golden_id",
            golden_id
        )
        .limit(1)
        .execute()
    )

    records = response.data or []

    if not records:
        raise HTTPException(
            status_code=404,
            detail="Golden customer not found"
        )

    old_record = records[0]

    # --------------------------------------------------------
    # Build update
    # Any field manually changed by a steward becomes
    # DATA_STEWARD-authoritative for that field.
    # --------------------------------------------------------

    allowed_fields = [
        "name",
        "email",
        "phone",
        "address",
        "dob"
    ]

    update_data = {}
    updated_value_fields = []
    stewardship_changes = []

    for field in allowed_fields:

        value = getattr(
            update,
            field
        )

        if value is not None:

            update_data[field] = value
            update_data[FIELD_SOURCE_MAP[field]] = DATA_STEWARD_SOURCE
            updated_value_fields.append(field)

            stewardship_changes.append({
                "field": field,
                "old_value": old_record.get(field),
                "new_value": value,
                "old_source": old_record.get(
                    FIELD_SOURCE_MAP[field]
                ),
                "new_source": DATA_STEWARD_SOURCE
            })

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No fields supplied for update"
        )

    # --------------------------------------------------------
    # Update Golden Record
    # --------------------------------------------------------

    updated_response = (
        supabase
        .table("golden_records")
        .update(update_data)
        .eq(
            "golden_id",
            golden_id
        )
        .execute()
    )

    updated_record = (
        updated_response.data or []
    )

    # --------------------------------------------------------
    # Audit every stewardship change
    # --------------------------------------------------------

    audit_rows = []

    for change in stewardship_changes:

        value_changed = (
            str(change["old_value"])
            != str(change["new_value"])
        )

        source_changed = (
            str(change["old_source"])
            != DATA_STEWARD_SOURCE
        )

        if value_changed or source_changed:

            audit_rows.append({
                "entity_type": "golden_record",
                "entity_id": golden_id,
                "action": "DATA_STEWARD_OVERRIDE",
                "old_value": {
                    change["field"]:
                        change["old_value"],
                    FIELD_SOURCE_MAP[change["field"]]:
                        change["old_source"]
                },
                "new_value": {
                    change["field"]:
                        change["new_value"],
                    FIELD_SOURCE_MAP[change["field"]]:
                        DATA_STEWARD_SOURCE
                },
                "changed_by": update.changed_by
            })

    if audit_rows:
        (
            supabase
            .table("audit_logs")
            .insert(audit_rows)
            .execute()
        )

    return {
        "message": "Customer updated successfully",
        "golden_id": golden_id,
        "updated_fields": updated_value_fields,
        "steward_overrides": [
            {
                "field": change["field"],
                "source": DATA_STEWARD_SOURCE
            }
            for change in stewardship_changes
        ],
        "reason": update.reason,
        "customer": (
            updated_record[0]
            if updated_record
            else None
        )
    }


# ============================================================
# BULK CUSTOMER UPDATE
# ============================================================

@app.patch("/api/customers/bulk-update")
def bulk_update_customers(
    update: BulkCustomerUpdate
):

    allowed_fields = [
        "name",
        "email",
        "phone",
        "address",
        "dob"
    ]

    if update.field not in allowed_fields:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid field. Allowed fields: "
                f"{', '.join(allowed_fields)}"
            )
        )

    if not update.golden_ids:
        raise HTTPException(
            status_code=400,
            detail="No Golden IDs supplied"
        )

    updated = []
    failed = []
    audit_rows = []

    source_field = FIELD_SOURCE_MAP[update.field]

    for golden_id in update.golden_ids:

        try:

            response = (
                supabase
                .table("golden_records")
                .select("*")
                .eq(
                    "golden_id",
                    golden_id
                )
                .limit(1)
                .execute()
            )

            records = response.data or []

            if not records:
                failed.append({
                    "golden_id": golden_id,
                    "reason": "Customer not found"
                })
                continue

            old_record = records[0]
            old_value = old_record.get(update.field)
            old_source = old_record.get(source_field)

            # ------------------------------------------------
            # Manual bulk stewardship update
            # ------------------------------------------------

            (
                supabase
                .table("golden_records")
                .update({
                    update.field: update.value,
                    source_field: DATA_STEWARD_SOURCE
                })
                .eq(
                    "golden_id",
                    golden_id
                )
                .execute()
            )

            updated.append(golden_id)

            if (
                str(old_value) != str(update.value)
                or str(old_source) != DATA_STEWARD_SOURCE
            ):

                audit_rows.append({
                    "entity_type": "golden_record",
                    "entity_id": golden_id,
                    "action": "DATA_STEWARD_BULK_OVERRIDE",
                    "old_value": {
                        update.field: old_value,
                        source_field: old_source
                    },
                    "new_value": {
                        update.field: update.value,
                        source_field: DATA_STEWARD_SOURCE
                    },
                    "changed_by": update.changed_by
                })

        except Exception as e:

            failed.append({
                "golden_id": golden_id,
                "reason": str(e)
            })

    # --------------------------------------------------------
    # Save audits
    # --------------------------------------------------------

    if audit_rows:
        (
            supabase
            .table("audit_logs")
            .insert(audit_rows)
            .execute()
        )

    return {
        "message": "Bulk update completed",
        "field": update.field,
        "updated_count": len(updated),
        "failed_count": len(failed),
        "updated": updated,
        "failed": failed,
        "source": DATA_STEWARD_SOURCE,
        "reason": update.reason
    }


# ============================================================
# AUDIT TRAIL
# ============================================================

@app.get("/api/audit")
def get_audit_logs(
    golden_id: Optional[str] = None,
    limit: int = Query(
        100,
        ge=1,
        le=500
    )
):

    query = (
        supabase
        .table("audit_logs")
        .select("*")
        .order(
            "created_at",
            desc=True
        )
        .limit(limit)
    )

    if golden_id:

        query = query.eq(
            "entity_id",
            golden_id
        )

    response = query.execute()

    return {
        "count": len(
            response.data or []
        ),
        "logs": response.data or []
    }

# ============================================================
# INCREMENTAL MDM PROCESSING
# ============================================================

FUZZY_THRESHOLD = 0.85


def load_trust_hierarchy():
    config_path = (
        Path(__file__).resolve().parent
        / "config"
        / "trust_hierarchy.json"
    )

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_all_source_customers():
    customers = []
    start = 0
    page_size = 1000

    while True:
        response = (
            supabase
            .table("source_customers")
            .select(
                "id,source_id,source_customer_id,"
                "name,email,phone,dob,address,"
                "normalized_name,normalized_email,"
                "normalized_phone,normalized_address"
            )
            .range(start, start + page_size - 1)
            .execute()
        )

        batch = response.data or []

        if not batch:
            break

        customers.extend(batch)

        if len(batch) < page_size:
            break

        start += page_size

    return customers


def get_source_names():
    response = (
        supabase
        .table("sources")
        .select("id,source_name")
        .execute()
    )

    return {
        row["id"]: row["source_name"]
        for row in response.data or []
    }


def find_incremental_matches(new_customer):
    """
    Find existing customers that match the newly uploaded customer.

    Rules:
    1. Exact email
    2. Exact phone
    3. Fuzzy name + address, both >= 0.85

    Records from the same source system are never matched.
    """

    all_customers = get_all_source_customers()
    source_names = get_source_names()

    # Load reference-data abbreviations for address normalization.
    reference_map = {}
    try:
        reference_response = (
            supabase
            .table("reference_data")
            .select("short_form,long_form")
            .execute()
        )
        reference_map = {
            row["short_form"]: row["long_form"]
            for row in (reference_response.data or [])
        }
    except Exception:
        # Matching should still work if reference_data is unavailable.
        reference_map = {}

    new_email = clean_email(new_customer.get("email"))
    new_phone = clean_phone(new_customer.get("phone"))
    new_name = clean_name(new_customer.get("name"))
    new_address = clean_address(
        new_customer.get("address"),
        reference_map
    )

    matches = []

    for existing in all_customers:

        # Do not compare the record with itself.
        if existing["id"] == new_customer["id"]:
            continue

        # Preserve the source-engine rule:
        # records from the same source system are not matched.
        if existing["source_id"] == new_customer["source_id"]:
            continue

        existing_email = clean_email(existing.get("email"))
        existing_phone = clean_phone(existing.get("phone"))
        existing_name = clean_name(existing.get("name"))
        existing_address = clean_address(
            existing.get("address"),
            reference_map
        )

        match_method = None
        match_score = None

        # ----------------------------------------------------
        # EXACT EMAIL
        # ----------------------------------------------------
        if (
            new_email
            and existing_email
            and new_email == existing_email
        ):
            match_method = "EXACT_EMAIL"
            match_score = 1.0

        # ----------------------------------------------------
        # EXACT PHONE
        # ----------------------------------------------------
        elif (
            new_phone
            and existing_phone
            and new_phone == existing_phone
        ):
            match_method = "EXACT_PHONE"
            match_score = 1.0

        # ----------------------------------------------------
        # FUZZY NAME + ADDRESS
        # ----------------------------------------------------
        elif (
            new_name
            and existing_name
            and new_address
            and existing_address
        ):
            name_score = (
                fuzz.ratio(new_name, existing_name) / 100
            )
            address_score = (
                fuzz.ratio(new_address, existing_address) / 100
            )

            if (
                name_score >= FUZZY_THRESHOLD
                and address_score >= FUZZY_THRESHOLD
            ):
                match_method = "FUZZY_NAME_ADDRESS"
                match_score = round(
                    (name_score + address_score) / 2,
                    5
                )

        if match_method:
            matches.append({
                "customer_id": existing["id"],
                "match_method": match_method,
                "match_score": match_score,
                "source_name": source_names.get(
                    existing["source_id"],
                    f"Source_{existing['source_id']}"
                )
            })

    # Prefer strongest evidence first.
    matches.sort(
        key=lambda x: (
            x["match_score"],
            x["match_method"] == "EXACT_EMAIL",
            x["match_method"] == "EXACT_PHONE"
        ),
        reverse=True
    )

    return matches

def get_golden_for_source_customer(source_customer_id):
    """
    Find which Golden Record currently owns
    this source customer.
    """

    response = (
        supabase
        .table("golden_record_sources")
        .select(
            "golden_record_id,"
            "match_method,"
            "match_score"
        )
        .eq(
            "source_customer_id",
            source_customer_id
        )
        .limit(1)
        .execute()
    )

    links = response.data or []

    if not links:
        return None

    golden_db_id = links[0]["golden_record_id"]

    response = (
        supabase
        .table("golden_records")
        .select("*")
        .eq("id", golden_db_id)
        .limit(1)
        .execute()
    )

    records = response.data or []

    return records[0] if records else None


def get_group_records(golden_db_id):
    """
    Get every source customer belonging to
    one Golden Record.
    """

    links_response = (
        supabase
        .table("golden_record_sources")
        .select(
            "source_customer_id,"
            "match_method,"
            "match_score"
        )
        .eq(
            "golden_record_id",
            golden_db_id
        )
        .execute()
    )

    links = links_response.data or []

    if not links:
        return []

    ids = [
        row["source_customer_id"]
        for row in links
    ]

    customers_response = (
        supabase
        .table("source_customers")
        .select("*")
        .in_("id", ids)
        .execute()
    )

    customers = customers_response.data or []

    source_names = get_source_names()

    enriched = []

    for customer in customers:

        customer_copy = customer.copy()

        customer_copy["source_name"] = source_names.get(
            customer["source_id"],
            f"Source_{customer['source_id']}"
        )

        enriched.append(customer_copy)

    return enriched


def select_surviving_value_incremental(
    group_records,
    field,
    hierarchy
):

    trust_order = hierarchy.get(field, [])

    for source in trust_order:

        for record in group_records:

            if record["source_name"] != source:
                continue

            value = record.get(field)

            if value is None:
                continue

            if str(value).strip() == "":
                continue

            return value, source

    # Fallback
    for record in group_records:

        value = record.get(field)

        if value is None:
            continue

        if str(value).strip() == "":
            continue

        return (
            value,
            record["source_name"]
        )

    return None, None


def recalculate_golden_record(golden_db_id):
    """
    Recalculate ONLY one Golden Record using the existing trust hierarchy.

    DATA_STEWARD overrides are authoritative. If a Golden Record field has
    *_source = DATA_STEWARD, that value is preserved and is not replaced by
    SourceA/SourceB/SourceC during incremental MDM processing.
    """

    hierarchy = load_trust_hierarchy()

    group_records = get_group_records(
        golden_db_id
    )

    if not group_records:
        return None

    # Load current Golden Record so we can preserve steward overrides.
    current_response = (
        supabase
        .table("golden_records")
        .select("*")
        .eq("id", golden_db_id)
        .limit(1)
        .execute()
    )

    current_records = current_response.data or []

    if not current_records:
        return None

    current_golden = current_records[0]

    # First record is only metadata anchor.
    representative = group_records[0]

    fields = [
        "name",
        "email",
        "phone",
        "address",
        "dob"
    ]

    update_data = {
        "representative_source":
            representative["source_name"],

        "representative_source_id":
            representative["source_customer_id"],

        "match_group_size":
            len(group_records)
    }

    for field in fields:

        source_field = FIELD_SOURCE_MAP[field]

        # ----------------------------------------------------
        # DATA STEWARD OVERRIDE
        # ----------------------------------------------------
        if (
            current_golden.get(source_field)
            == DATA_STEWARD_SOURCE
        ):

            update_data[field] = current_golden.get(
                field
            )

            update_data[source_field] = (
                DATA_STEWARD_SOURCE
            )

            continue

        # ----------------------------------------------------
        # NORMAL SOURCE-BASED SURVIVORSHIP
        # ----------------------------------------------------

        value, source = (
            select_surviving_value_incremental(
                group_records,
                field,
                hierarchy
            )
        )

        update_data[field] = value
        update_data[source_field] = source

    response = (
        supabase
        .table("golden_records")
        .update(update_data)
        .eq("id", golden_db_id)
        .execute()
    )

    return (
        response.data[0]
        if response.data
        else None
    )


def create_incremental_golden_record(
    customer,
    source_name
):

    # Generate next Golden ID
    response = (
        supabase
        .table("golden_records")
        .select("golden_id")
        .order(
            "id",
            desc=True
        )
        .limit(1)
        .execute()
    )

    existing = response.data or []

    if existing:
        last_id = existing[0]["golden_id"]

        try:
            number = int(
                last_id.replace(
                    "GOLD_",
                    ""
                )
            ) + 1
        except ValueError:
            number = 1
    else:
        number = 1

    golden_id = f"GOLD_{number:06d}"

    # Create Golden Record
    golden_data = {
        "golden_id": golden_id,

        "name": customer.get("name"),
        "email": customer.get("email"),
        "phone": customer.get("phone"),
        "address": customer.get("address"),
        "dob": customer.get("dob"),

        "name_source": source_name,
        "email_source": source_name,
        "phone_source": source_name,
        "address_source": source_name,
        "dob_source": source_name,

        "representative_source": source_name,

        "representative_source_id":
            customer["source_customer_id"],

        "match_group_size": 1
    }

    golden_response = (
        supabase
        .table("golden_records")
        .insert(golden_data)
        .execute()
    )

    golden_records = golden_response.data or []

    if not golden_records:
        raise HTTPException(
            status_code=500,
            detail="Failed to create Golden Record"
        )

    golden = golden_records[0]

    # Connect source customer
    supabase.table(
        "golden_record_sources"
    ).insert({
        "golden_record_id":
            golden["id"],

        "source_customer_id":
            customer["id"],

        "match_method":
            None,

        "match_score":
            None
    }).execute()

    return golden


def process_new_customer(customer_id):
    """
    Process one newly inserted source customer through the MDM flow.

    This is intentionally incremental. It does NOT rebuild all Golden
    Records and therefore does not disturb existing transaction links.
    """

    # --------------------------------------------------------
    # Load uploaded customer
    # --------------------------------------------------------

    response = (
        supabase
        .table("source_customers")
        .select("*")
        .eq("id", customer_id)
        .limit(1)
        .execute()
    )

    customers = response.data or []

    if not customers:
        raise HTTPException(
            status_code=404,
            detail="Uploaded customer not found"
        )

    customer = customers[0]

    source_names = get_source_names()

    source_name = source_names.get(
        customer["source_id"],
        f"Source_{customer['source_id']}"
    )

    # --------------------------------------------------------
    # Find matching source records
    # --------------------------------------------------------

    matches = find_incremental_matches(customer)

    # --------------------------------------------------------
    # Helper: add a match link if it does not already exist
    # --------------------------------------------------------

    def ensure_match_link(existing_id, method, score):

        first_id = min(customer["id"], existing_id)
        second_id = max(customer["id"], existing_id)

        duplicate = (
            supabase
            .table("match_links")
            .select("id")
            .eq("source_customer_id_1", first_id)
            .eq("source_customer_id_2", second_id)
            .limit(1)
            .execute()
        )

        if duplicate.data:
            return

        (
            supabase
            .table("match_links")
            .insert({
                "source_customer_id_1": first_id,
                "source_customer_id_2": second_id,
                "match_method": method,
                "match_score": score
            })
            .execute()
        )

    # --------------------------------------------------------
    # NO MATCH
    # --------------------------------------------------------

    if not matches:

        golden = create_incremental_golden_record(
            customer,
            source_name
        )

        (
            supabase
            .table("audit_logs")
            .insert({
                "entity_type": "golden_record",
                "entity_id": golden["golden_id"],
                "action": "CREATE_FROM_UPLOAD",
                "old_value": None,
                "new_value": {
                    "source_customer_id": customer["id"],
                    "source_name": source_name,
                    "match_method": None,
                    "match_score": None
                },
                "changed_by": "system"
            })
            .execute()
        )

        return {
            "action": "NEW_GOLDEN_RECORD",
            "golden_id": golden["golden_id"],
            "match_method": None,
            "match_score": None,
            "matches_found": 0,
            "golden_record": golden
        }

    # --------------------------------------------------------
    # Find Golden Records belonging to matched source records
    # --------------------------------------------------------

    matched_source_ids = [
        match["customer_id"]
        for match in matches
    ]

    golden_links_response = (
        supabase
        .table("golden_record_sources")
        .select(
            "golden_record_id,"
            "source_customer_id,"
            "match_method,"
            "match_score"
        )
        .in_(
            "source_customer_id",
            matched_source_ids
        )
        .execute()
    )

    golden_links = golden_links_response.data or []

    golden_db_ids = sorted({
        row["golden_record_id"]
        for row in golden_links
    })

    # --------------------------------------------------------
    # No existing Golden Record among matched records
    #
    # This can happen because earlier uploads were inserted
    # using the old endpoint. Repair those orphan records by
    # creating one Golden Record and attaching all matches.
    # --------------------------------------------------------

    if not golden_db_ids:

        golden = create_incremental_golden_record(
            customer,
            source_name
        )

        golden_db_id = golden["id"]
        golden_id = golden["golden_id"]

        for match in matches:

            ensure_match_link(
                match["customer_id"],
                match["match_method"],
                match["match_score"]
            )

            (
                supabase
                .table("golden_record_sources")
                .insert({
                    "golden_record_id": golden_db_id,
                    "source_customer_id": match["customer_id"],
                    "match_method": match["match_method"],
                    "match_score": match["match_score"]
                })
                .execute()
            )

        updated_golden = recalculate_golden_record(
            golden_db_id
        )

        (
            supabase
            .table("audit_logs")
            .insert({
                "entity_type": "golden_record",
                "entity_id": golden_id,
                "action": "CREATE_AND_REPAIR_FROM_UPLOAD",
                "old_value": None,
                "new_value": {
                    "source_customer_id": customer["id"],
                    "source_name": source_name,
                    "matches_found": len(matches)
                },
                "changed_by": "system"
            })
            .execute()
        )

        return {
            "action": "NEW_GOLDEN_RECORD_WITH_MATCHES",
            "golden_id": golden_id,
            "match_method": matches[0]["match_method"],
            "match_score": matches[0]["match_score"],
            "matches_found": len(matches),
            "golden_record": updated_golden
        }

    # --------------------------------------------------------
    # Select primary Golden Record.
    #
    # If the new record bridges multiple existing Golden Records,
    # merge the smaller groups into the primary group.
    # --------------------------------------------------------

    primary_golden_db_id = golden_db_ids[0]

    primary_response = (
        supabase
        .table("golden_records")
        .select("id,golden_id")
        .eq("id", primary_golden_db_id)
        .limit(1)
        .execute()
    )

    primary_rows = primary_response.data or []

    if not primary_rows:
        raise HTTPException(
            status_code=500,
            detail="Primary Golden Record not found"
        )

    primary_golden_id = primary_rows[0]["golden_id"]

    # --------------------------------------------------------
    # Merge bridged Golden Records into primary
    # --------------------------------------------------------

    merged_golden_ids = []

    for old_golden_db_id in golden_db_ids[1:]:

        old_response = (
            supabase
            .table("golden_records")
            .select("id,golden_id")
            .eq("id", old_golden_db_id)
            .limit(1)
            .execute()
        )

        old_rows = old_response.data or []

        if not old_rows:
            continue

        old_golden_id = old_rows[0]["golden_id"]

        # Preserve any DATA_STEWARD field overrides from the old Golden
        # Record before that Golden Record is merged/deleted.
        old_golden_full_response = (
            supabase
            .table("golden_records")
            .select(
                "name,email,phone,address,dob,"
                "name_source,email_source,phone_source,"
                "address_source,dob_source"
            )
            .eq("id", old_golden_db_id)
            .limit(1)
            .execute()
        )

        old_golden_full = (
            old_golden_full_response.data[0]
            if old_golden_full_response.data
            else {}
        )

        primary_full_response = (
            supabase
            .table("golden_records")
            .select(
                "name_source,email_source,phone_source,"
                "address_source,dob_source"
            )
            .eq("id", primary_golden_db_id)
            .limit(1)
            .execute()
        )

        primary_full = (
            primary_full_response.data[0]
            if primary_full_response.data
            else {}
        )

        steward_transfer = {}

        for field in (
            "name",
            "email",
            "phone",
            "address",
            "dob"
        ):
            source_field = FIELD_SOURCE_MAP[field]

            if (
                old_golden_full.get(source_field)
                == DATA_STEWARD_SOURCE
                and primary_full.get(source_field)
                != DATA_STEWARD_SOURCE
            ):
                steward_transfer[field] = old_golden_full.get(field)
                steward_transfer[source_field] = DATA_STEWARD_SOURCE

        if steward_transfer:
            (
                supabase
                .table("golden_records")
                .update(steward_transfer)
                .eq("id", primary_golden_db_id)
                .execute()
            )

            primary_full.update(steward_transfer)

        # Move transaction references BEFORE deleting the old
        # Golden Record because transactions use ON DELETE SET NULL.
        (
            supabase
            .table("transactions")
            .update({
                "golden_id": primary_golden_id
            })
            .eq(
                "golden_id",
                old_golden_id
            )
            .execute()
        )

        old_links_response = (
            supabase
            .table("golden_record_sources")
            .select(
                "source_customer_id,"
                "match_method,"
                "match_score"
            )
            .eq(
                "golden_record_id",
                old_golden_db_id
            )
            .execute()
        )

        old_links = old_links_response.data or []

        for link in old_links:

            existing_primary_link = (
                supabase
                .table("golden_record_sources")
                .select("id")
                .eq(
                    "golden_record_id",
                    primary_golden_db_id
                )
                .eq(
                    "source_customer_id",
                    link["source_customer_id"]
                )
                .limit(1)
                .execute()
            )

            if not existing_primary_link.data:

                (
                    supabase
                    .table("golden_record_sources")
                    .insert({
                        "golden_record_id":
                            primary_golden_db_id,
                        "source_customer_id":
                            link["source_customer_id"],
                        "match_method":
                            link["match_method"],
                        "match_score":
                            link["match_score"]
                    })
                    .execute()
                )

        (
            supabase
            .table("golden_record_sources")
            .delete()
            .eq(
                "golden_record_id",
                old_golden_db_id
            )
            .execute()
        )

        (
            supabase
            .table("golden_records")
            .delete()
            .eq(
                "id",
                old_golden_db_id
            )
            .execute()
        )

        merged_golden_ids.append(old_golden_id)

    # --------------------------------------------------------
    # Add uploaded source customer to primary Golden Record
    # --------------------------------------------------------

    existing_new_link = (
        supabase
        .table("golden_record_sources")
        .select("id")
        .eq(
            "golden_record_id",
            primary_golden_db_id
        )
        .eq(
            "source_customer_id",
            customer["id"]
        )
        .limit(1)
        .execute()
    )

    primary_match = matches[0]

    if not existing_new_link.data:

        (
            supabase
            .table("golden_record_sources")
            .insert({
                "golden_record_id":
                    primary_golden_db_id,
                "source_customer_id":
                    customer["id"],
                "match_method":
                    primary_match["match_method"],
                "match_score":
                    primary_match["match_score"]
            })
            .execute()
        )

    # --------------------------------------------------------
    # Save all match relationships
    # --------------------------------------------------------

    for match in matches:

        ensure_match_link(
            match["customer_id"],
            match["match_method"],
            match["match_score"]
        )

    # --------------------------------------------------------
    # Recalculate survivorship for affected group only
    # --------------------------------------------------------

    updated_golden = recalculate_golden_record(
        primary_golden_db_id
    )

    # --------------------------------------------------------
    # Audit
    # --------------------------------------------------------

    action = (
        "CUSTOMER_MATCHED_FROM_UPLOAD"
        if not merged_golden_ids
        else "CUSTOMER_MATCHED_AND_GOLDEN_GROUPS_MERGED"
    )

    (
        supabase
        .table("audit_logs")
        .insert({
            "entity_type": "golden_record",
            "entity_id": primary_golden_id,
            "action": action,
            "old_value": None,
            "new_value": {
                "source_customer_id": customer["id"],
                "source_name": source_name,
                "match_method": primary_match["match_method"],
                "match_score": primary_match["match_score"],
                "matches_found": len(matches),
                "merged_golden_ids": merged_golden_ids
            },
            "changed_by": "system"
        })
        .execute()
    )

    return {
        "action": (
            "MATCHED_EXISTING_GOLDEN_RECORD"
            if not merged_golden_ids
            else "MATCHED_AND_MERGED_GOLDEN_RECORDS"
        ),
        "golden_id": primary_golden_id,
        "match_method": primary_match["match_method"],
        "match_score": primary_match["match_score"],
        "matches_found": len(matches),
        "merged_golden_ids": merged_golden_ids,
        "golden_record": updated_golden
    }

# ============================================================
# UPLOAD SINGLE SOURCE CUSTOMER
# ============================================================

@app.post("/api/customers/upload")
def upload_customer(
    source_name: str = Form(...),
    source_customer_id: str = Form(...),
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    dob: str = Form(""),
    address: str = Form("")
):

    # --------------------------------------------------------
    # Find source
    # --------------------------------------------------------

    source_response = (
        supabase
        .table("sources")
        .select("id,source_name")
        .eq("source_name", source_name)
        .limit(1)
        .execute()
    )

    sources = source_response.data or []

    if not sources:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source: {source_name}"
        )

    source_id = sources[0]["id"]

    # --------------------------------------------------------
    # Proper normalization
    # --------------------------------------------------------

    customer = {
        "source_id": source_id,
        "source_customer_id": source_customer_id,

        "name": name or None,
        "email": email or None,
        "phone": phone or None,
        "dob": dob or None,
        "address": address or None,

        "normalized_name": clean_name(name),
        "normalized_email": clean_email(email),
        "normalized_phone": clean_phone(phone),
        "normalized_address": clean_address(address)
    }

    # --------------------------------------------------------
    # Insert source customer
    # --------------------------------------------------------

    try:

        response = (
            supabase
            .table("source_customers")
            .insert(customer)
            .execute()
        )

    except Exception as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    inserted = response.data or []

    if not inserted:

        raise HTTPException(
            status_code=500,
            detail="Customer insertion failed"
        )

    new_customer = inserted[0]

    # --------------------------------------------------------
    # Incremental MDM processing
    # --------------------------------------------------------

    try:

        result = process_new_customer(
            new_customer["id"]
        )

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=(
                "Customer was uploaded, but "
                f"MDM processing failed: {str(e)}"
            )
        )

    # --------------------------------------------------------
    # Final response
    # --------------------------------------------------------

    return {
        "message":
            "Customer uploaded and processed successfully",

        "customer":
            new_customer,

        "mdm":
            result
    }


# ============================================================
# BULK CSV IMPORT
# ============================================================

@app.post("/api/import/csv")
async def import_csv(
    source_name: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Bulk CSV import with incremental MDM processing.

    The CSV rows are first upserted into source_customers. Every
    resulting source customer is then sent through the same
    process_new_customer() pipeline used by the single-customer upload.

    This avoids rebuilding the complete MDM dataset while still creating
    or updating Golden Records for newly imported customers.
    """

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are supported"
        )

    # --------------------------------------------------------
    # Validate source
    # --------------------------------------------------------

    source_response = (
        supabase
        .table("sources")
        .select("id,source_name")
        .eq("source_name", source_name)
        .limit(1)
        .execute()
    )

    sources = source_response.data or []

    if not sources:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source: {source_name}"
        )

    source_id = sources[0]["id"]

    # --------------------------------------------------------
    # Read CSV
    # --------------------------------------------------------

    contents = await file.read()

    try:
        text = contents.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid CSV: {str(e)}"
        )

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="CSV contains no data"
        )

    # --------------------------------------------------------
    # Build records
    # --------------------------------------------------------

    records = []
    skipped_rows = 0

    for row in rows:
        source_customer_id = (
            row.get("customer_id")
            or row.get("Customer_ID")
            or row.get("source_customer_id")
            or row.get("Source_Customer_ID")
            or row.get("account_id")
            or row.get("Account_ID")
        )

        if not source_customer_id:
            skipped_rows += 1
            continue

        name = (
            row.get("name")
            or row.get("Name")
            or ""
        ).strip()

        email = (
            row.get("email")
            or row.get("Email")
            or ""
        ).strip()

        phone = (
            row.get("phone")
            or row.get("Phone")
            or ""
        ).strip()

        address = (
            row.get("address")
            or row.get("Address")
            or ""
        ).strip()

        dob = (
            row.get("dob")
            or row.get("DOB")
            or None
        )

        records.append({
            "source_id": source_id,
            "source_customer_id": str(source_customer_id).strip(),
            "name": name or None,
            "email": email or None,
            "phone": phone or None,
            "dob": dob,
            "address": address or None,
            "normalized_name": clean_name(name),
            "normalized_email": clean_email(email),
            "normalized_phone": clean_phone(phone),
            "normalized_address": clean_address(address)
        })

    if not records:
        raise HTTPException(
            status_code=400,
            detail="No valid customer records found in CSV"
        )

    # --------------------------------------------------------
    # Upsert source records first.
    # We collect the returned database rows so their actual IDs can
    # be passed directly into the incremental MDM processor.
    # --------------------------------------------------------

    upserted_customers = []
    batch_size = 500

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        response = (
            supabase
            .table("source_customers")
            .upsert(
                batch,
                on_conflict="source_id,source_customer_id"
            )
            .execute()
        )

        upserted_customers.extend(response.data or [])

    if not upserted_customers:
        raise HTTPException(
            status_code=500,
            detail="CSV rows could not be inserted into source_customers"
        )

    # --------------------------------------------------------
    # Incremental MDM processing
    # --------------------------------------------------------

    new_golden_count = 0
    matched_count = 0
    merged_count = 0
    fuzzy_count = 0
    exact_email_count = 0
    exact_phone_count = 0
    mdm_errors = []
    mdm_results = []

    for customer in upserted_customers:
        try:
            result = process_new_customer(customer["id"])
            mdm_results.append({
                "source_customer_id": customer["source_customer_id"],
                **{
                    key: result.get(key)
                    for key in (
                        "action",
                        "golden_id",
                        "match_method",
                        "match_score",
                        "matches_found"
                    )
                }
            })

            action = result.get("action")

            if action == "NEW_GOLDEN_RECORD":
                new_golden_count += 1
            elif action == "NEW_GOLDEN_RECORD_WITH_MATCHES":
                new_golden_count += 1
                matched_count += 1
            elif action == "MATCHED_EXISTING_GOLDEN_RECORD":
                matched_count += 1
            elif action == "MATCHED_AND_MERGED_GOLDEN_RECORDS":
                matched_count += 1
                merged_count += 1

            method = result.get("match_method")
            if method == "EXACT_EMAIL":
                exact_email_count += 1
            elif method == "EXACT_PHONE":
                exact_phone_count += 1
            elif method == "FUZZY_NAME_ADDRESS":
                fuzzy_count += 1

        except Exception as e:
            mdm_errors.append({
                "source_customer_id": customer.get("source_customer_id"),
                "customer_id": customer.get("id"),
                "error": str(e)
            })

    # --------------------------------------------------------
    # Return both import and MDM results.
    # Keep records_inserted_or_updated for frontend compatibility.
    # --------------------------------------------------------

    return {
        "message": "CSV import and MDM processing completed",
        "source": source_name,
        "filename": file.filename,
        "rows_read": len(rows),
        "records_processed": len(records),
        "records_skipped": skipped_rows,
        "records_inserted_or_updated": len(upserted_customers),
        "mdm": {
            "new_golden_records": new_golden_count,
            "matched_existing_records": matched_count,
            "merged_golden_groups": merged_count,
            "exact_email_matches": exact_email_count,
            "exact_phone_matches": exact_phone_count,
            "fuzzy_matches": fuzzy_count,
            "successful": len(mdm_results),
            "failed": len(mdm_errors),
            "errors": mdm_errors,
            "results": mdm_results
        }
    }

# ============================================================
# CUSTOMER TRANSACTIONS
# ============================================================

@app.get(
    "/api/customers/{golden_id}/transactions"
)
def get_customer_transactions(
    golden_id: str,
    limit: int = Query(
        100,
        ge=1,
        le=500
    ),
    offset: int = Query(
        0,
        ge=0
    )
):

    # Verify customer exists
    customer = (
        supabase
        .table("golden_records")
        .select("golden_id")
        .eq(
            "golden_id",
            golden_id
        )
        .limit(1)
        .execute()
    )

    if not customer.data:

        raise HTTPException(
            status_code=404,
            detail="Golden customer not found"
        )

    response = (
        supabase
        .table("transactions")
        .select(
            "txn_id,account_id,amount,"
            "transaction_date,"
            "transaction_type"
        )
        .eq(
            "golden_id",
            golden_id
        )
        .order(
            "transaction_date",
            desc=True
        )
        .range(
            offset,
            offset + limit - 1
        )
        .execute()
    )

    transactions = response.data or []

    return {
        "golden_id": golden_id,
        "count": len(transactions),
        "offset": offset,
        "limit": limit,
        "transactions": transactions
    }


# ============================================================
# CUSTOMER SOURCE RECORDS
# ============================================================

@app.get(
    "/api/customers/{golden_id}/sources"
)
def get_customer_sources(
    golden_id: str
):

    golden_response = (
        supabase
        .table("golden_records")
        .select("id,golden_id")
        .eq(
            "golden_id",
            golden_id
        )
        .limit(1)
        .execute()
    )

    golden = (
        golden_response.data or []
    )

    if not golden:

        raise HTTPException(
            status_code=404,
            detail="Golden customer not found"
        )

    golden_db_id = golden[0]["id"]

    links = (
        supabase
        .table("golden_record_sources")
        .select(
            "source_customer_id,"
            "match_method,"
            "match_score"
        )
        .eq(
            "golden_record_id",
            golden_db_id
        )
        .execute()
    )

    source_links = links.data or []

    if not source_links:

        return {
            "golden_id": golden_id,
            "count": 0,
            "sources": []
        }

    ids = [
        row["source_customer_id"]
        for row in source_links
    ]

    records = (
        supabase
        .table("source_customers")
        .select("*")
        .in_(
            "id",
            ids
        )
        .execute()
    )

    record_map = {
        row["id"]: row
        for row in (
            records.data or []
        )
    }

    result = []

    for link in source_links:

        record = record_map.get(
            link["source_customer_id"]
        )

        if record:

            result.append({
                "source_record": record,
                "match_method":
                    link["match_method"],
                "match_score":
                    link["match_score"]
            })

    return {
        "golden_id": golden_id,
        "count": len(result),
        "sources": result
    }