"""
MDM Customer 360 - Supabase Transaction Linker

Reads transactions from Supabase and links each transaction
to its Golden Record using:

Transaction Account_ID
        ↓
Source System
        ↓
source_customers.source_customer_id
        ↓
golden_record_sources
        ↓
golden_records.golden_id

Updates:
    transactions.golden_id
"""

import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.append(str(PROJECT_ROOT))

from database import supabase


PAGE_SIZE = 1000


# ============================================================
# LOAD DATA WITH PAGINATION
# ============================================================

def load_all(table, columns):

    rows = []
    start = 0

    while True:

        response = (
            supabase
            .table(table)
            .select(columns)
            .range(
                start,
                start + PAGE_SIZE - 1
            )
            .execute()
        )

        batch = response.data or []

        if not batch:
            break

        rows.extend(batch)

        if len(batch) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    return rows


# ============================================================
# INFER SOURCE
# ============================================================

def infer_source_from_account_id(account_id):
    """
    Preserve the source convention used by the original
    transaction linker.

    SourceA:
        C001, C0252, ...

    SourceB:
        CC001, CC701, ...

    SourceC:
        L001, L521, ...
    """

    account_id_str = str(account_id).strip().upper()

    if account_id_str.startswith(
        (
            "C0",
            "C1",
            "C2",
            "C3",
            "C4",
            "C5",
            "C6",
            "C7",
            "C8",
            "C9",
        )
    ):
        return "SourceA"

    elif account_id_str.startswith(
        ("CC", "CRED")
    ):
        return "SourceB"

    elif account_id_str.startswith(
        ("L", "LOAN")
    ):
        return "SourceC"

    return None


# ============================================================
# LOAD SOURCE MAP
# ============================================================

def build_source_map():

    print("\n==========================================")
    print("LOADING SOURCE SYSTEMS")
    print("==========================================")

    sources = load_all(
        "sources",
        "id,source_name"
    )

    source_map = {
        row["id"]: row["source_name"]
        for row in sources
    }

    for source_id, source_name in source_map.items():

        print(
            f"{source_id} -> {source_name}"
        )

    return source_map


# ============================================================
# BUILD ACCOUNT -> GOLDEN ID MAP
# ============================================================

def build_account_mapping(source_map):

    print("\n==========================================")
    print("BUILDING ACCOUNT → GOLDEN ID MAPPING")
    print("==========================================")

    source_customers = load_all(
        "source_customers",
        "id,source_id,source_customer_id"
    )

    golden_sources = load_all(
        "golden_record_sources",
        "source_customer_id,golden_record_id"
    )

    golden_records = load_all(
        "golden_records",
        "id,golden_id"
    )

    golden_id_by_db_id = {
        row["id"]: row["golden_id"]
        for row in golden_records
    }

    golden_by_customer_id = {}

    for row in golden_sources:

        golden_id = golden_id_by_db_id.get(
            row["golden_record_id"]
        )

        if golden_id:

            golden_by_customer_id[
                row["source_customer_id"]
            ] = golden_id

    account_mapping = {}

    source_counts = defaultdict(int)

    for customer in source_customers:

        source_name = source_map.get(
            customer["source_id"]
        )

        if not source_name:
            continue

        account_id = str(
            customer["source_customer_id"]
        ).strip()

        golden_id = golden_by_customer_id.get(
            customer["id"]
        )

        if golden_id:

            key = (
                source_name,
                account_id
            )

            account_mapping[key] = golden_id

            source_counts[source_name] += 1

    print(
        f"Source customers: "
        f"{len(source_customers)}"
    )

    print(
        f"Golden mappings: "
        f"{len(account_mapping)}"
    )

    print("\nMappings by source:")

    for source in sorted(source_counts):

        print(
            f"  {source}: "
            f"{source_counts[source]}"
        )

    return account_mapping


# ============================================================
# LOAD TRANSACTIONS
# ============================================================

def load_transactions():

    print("\n==========================================")
    print("LOADING TRANSACTIONS")
    print("==========================================")

    transactions = load_all(
        "transactions",
        "id,txn_id,account_id,amount,"
        "transaction_date,transaction_type,golden_id"
    )

    print(
        f"Total transactions: "
        f"{len(transactions)}"
    )

    return transactions


# ============================================================
# LINK TRANSACTIONS
# ============================================================

def link_transactions(
    transactions,
    account_mapping
):

    print("\n==========================================")
    print("LINKING TRANSACTIONS")
    print("==========================================")

    linked = []
    unlinked = []

    for txn in transactions:

        account_id = txn.get(
            "account_id"
        )

        if not account_id:

            unlinked.append({
                "txn_id": txn["txn_id"],
                "account_id": account_id,
                "reason": "NULL_ACCOUNT_ID"
            })

            continue

        account_id = str(
            account_id
        ).strip()

        source = infer_source_from_account_id(
            account_id
        )

        if not source:

            unlinked.append({
                "txn_id": txn["txn_id"],
                "account_id": account_id,
                "reason": "UNKNOWN_SOURCE"
            })

            continue

        golden_id = account_mapping.get(
            (
                source,
                account_id
            )
        )

        if not golden_id:

            unlinked.append({
                "txn_id": txn["txn_id"],
                "account_id": account_id,
                "reason": "NO_GOLDEN_RECORD"
            })

            continue

        linked.append({
            "id": txn["id"],
            "txn_id": txn["txn_id"],
            "golden_id": golden_id,
            "source_system": source
        })

    print(
        f"Linked transactions  : "
        f"{len(linked)}"
    )

    print(
        f"Unlinked transactions: "
        f"{len(unlinked)}"
    )

    return linked, unlinked


# ============================================================
# UPDATE SUPABASE
# ============================================================

def update_transactions(linked):

    print("\n==========================================")
    print("UPDATING TRANSACTIONS")
    print("==========================================")

    if not linked:
        print("No transactions to update.")
        return

    updated_count = 0

    for row in linked:

        (
            supabase
            .table("transactions")
            .update({
                "golden_id": row["golden_id"]
            })
            .eq(
                "id",
                row["id"]
            )
            .execute()
        )

        updated_count += 1

        if (
            updated_count % 500 == 0
            or updated_count == len(linked)
        ):
            print(
                f"Updated transactions: "
                f"{updated_count}/{len(linked)}"
            )

    print(
        f"\nSuccessfully updated: "
        f"{updated_count} transactions"
    )


# ============================================================
# VALIDATION
# ============================================================

def validate():

    print("\n==========================================")
    print("VALIDATING TRANSACTION LINKS")
    print("==========================================")

    transactions = load_all(
        "transactions",
        "id,txn_id,golden_id"
    )

    total = len(transactions)

    linked = [
        txn
        for txn in transactions
        if txn.get("golden_id")
    ]

    unlinked = [
        txn
        for txn in transactions
        if not txn.get("golden_id")
    ]

    unique_golden_ids = {
        txn["golden_id"]
        for txn in linked
    }

    linkage_rate = (
        len(linked) / total * 100
        if total
        else 0
    )

    print(
        f"Total transactions       : {total}"
    )

    print(
        f"Linked transactions      : "
        f"{len(linked)}"
    )

    print(
        f"Unlinked transactions    : "
        f"{len(unlinked)}"
    )

    print(
        f"Unique Golden Customers  : "
        f"{len(unique_golden_ids)}"
    )

    print(
        f"Linkage rate             : "
        f"{linkage_rate:.2f}%"
    )

    if unlinked:

        print(
            "\nFirst 10 unlinked transactions:"
        )

        for txn in unlinked[:10]:

            print(
                f"  {txn['txn_id']}"
            )

    else:

        print(
            "\nTransaction linking validation: PASSED"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print(
        "MDM CUSTOMER 360 - "
        "SUPABASE TRANSACTION LINKER"
    )
    print("=" * 60)

    # 1. Sources
    source_map = build_source_map()

    # 2. Build source customer → Golden ID mapping
    account_mapping = build_account_mapping(
        source_map
    )

    # 3. Load transactions
    transactions = load_transactions()

    # 4. Link
    linked, unlinked = link_transactions(
        transactions,
        account_mapping
    )

    # 5. Update Supabase
    update_transactions(linked)

    # 6. Validate
    validate()

    print()
    print("=" * 60)
    print(
        "SUPABASE TRANSACTION LINKING COMPLETED"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()