"""
MDM Customer 360 - Supabase Matching Engine

Migrated from the existing CSV matching engine.

Matching logic preserved:
1. Exact Email
2. Exact Phone
3. Fuzzy Name + Address
   - Name >= 0.85
   - Address >= 0.85

Output:
- match_links table in Supabase
"""

from rapidfuzz import fuzz

from database import supabase
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))


FUZZY_THRESHOLD = 0.85
PAGE_SIZE = 1000


# ============================================================
# 1. LOAD CUSTOMERS FROM SUPABASE
# ============================================================

def load_customers():
    """Load normalized customer records from source_customers."""

    print()
    print("==========================================")
    print("LOADING CUSTOMERS FROM SUPABASE")
    print("==========================================")

    customers = []
    start = 0

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
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )

        batch = response.data or []

        if not batch:
            break

        customers.extend(batch)

        print(f"Loaded customers: {len(customers)}")

        if len(batch) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    print(f"\nTotal customers loaded: {len(customers)}")

    return customers


# ============================================================
# 2. EXACT EMAIL MATCHING
# ============================================================

def exact_email_matching(customers):

    print()
    print("==========================================")
    print("EXACT EMAIL MATCHING")
    print("==========================================")

    email_groups = {}

    for customer in customers:

        email = customer.get("normalized_email")

        if not email:
            continue

        email_groups.setdefault(email, []).append(customer)

    matches = []

    for email, records in email_groups.items():

        if len(records) < 2:
            continue

        for i in range(len(records)):

            for j in range(i + 1, len(records)):

                record_a = records[i]
                record_b = records[j]

                # Do not match records from same source system
                if record_a["source_id"] == record_b["source_id"]:
                    continue

                matches.append({
                    "source_customer_id_1": record_a["id"],
                    "source_customer_id_2": record_b["id"],
                    "match_method": "EXACT_EMAIL",
                    "match_score": 1.0
                })

    print("Exact email matches:", len(matches))

    return matches


# ============================================================
# 3. EXACT PHONE MATCHING
# ============================================================

def exact_phone_matching(customers):

    print()
    print("==========================================")
    print("EXACT PHONE MATCHING")
    print("==========================================")

    phone_groups = {}

    for customer in customers:

        phone = customer.get("normalized_phone")

        if not phone:
            continue

        phone_groups.setdefault(phone, []).append(customer)

    matches = []

    for phone, records in phone_groups.items():

        if len(records) < 2:
            continue

        for i in range(len(records)):

            for j in range(i + 1, len(records)):

                record_a = records[i]
                record_b = records[j]

                # Do not match records from same source system
                if record_a["source_id"] == record_b["source_id"]:
                    continue

                matches.append({
                    "source_customer_id_1": record_a["id"],
                    "source_customer_id_2": record_b["id"],
                    "match_method": "EXACT_PHONE",
                    "match_score": 1.0
                })

    print("Exact phone matches:", len(matches))

    return matches


# ============================================================
# 4. BUILD EXACT MATCH PAIR SET
# ============================================================

def build_exact_pairs(email_matches, phone_matches):

    exact_pairs = set()

    for match in email_matches + phone_matches:

        pair = tuple(sorted([
            match["source_customer_id_1"],
            match["source_customer_id_2"]
        ]))

        exact_pairs.add(pair)

    return exact_pairs


# ============================================================
# 5. FUZZY NAME + ADDRESS MATCHING
# ============================================================

def fuzzy_matching(customers, exact_pairs):

    print()
    print("==========================================")
    print("FUZZY NAME + ADDRESS MATCHING")
    print("==========================================")

    fuzzy_matches = []

    total_comparisons = 0

    records = customers

    for i in range(len(records)):

        record_a = records[i]

        for j in range(i + 1, len(records)):

            record_b = records[j]

            # Same source system
            if record_a["source_id"] == record_b["source_id"]:
                continue

            # Check whether exact match already exists
            pair = tuple(sorted([
                record_a["id"],
                record_b["id"]
            ]))

            if pair in exact_pairs:
                continue

            name_a = record_a.get("normalized_name") or ""
            name_b = record_b.get("normalized_name") or ""

            address_a = record_a.get("normalized_address") or ""
            address_b = record_b.get("normalized_address") or ""

            # Name required
            if not name_a or not name_b:
                continue

            # Address required
            if not address_a or not address_b:
                continue

            total_comparisons += 1

            # Name similarity
            name_score = (
                fuzz.ratio(
                    name_a.lower(),
                    name_b.lower()
                ) / 100
            )

            # Address similarity
            address_score = (
                fuzz.ratio(
                    address_a.lower(),
                    address_b.lower()
                ) / 100
            )

            # Both must satisfy threshold
            if (
                name_score >= FUZZY_THRESHOLD
                and
                address_score >= FUZZY_THRESHOLD
            ):

                final_score = (
                    name_score + address_score
                ) / 2

                fuzzy_matches.append({
                    "source_customer_id_1": record_a["id"],
                    "source_customer_id_2": record_b["id"],
                    "match_method": "FUZZY_NAME_ADDRESS",
                    "match_score": round(final_score, 5)
                })

    print(
        "Fuzzy comparisons performed:",
        total_comparisons
    )

    print(
        "Fuzzy matches found:",
        len(fuzzy_matches)
    )

    return fuzzy_matches


# ============================================================
# 6. DEDUPLICATE MATCHES
# ============================================================

def deduplicate_matches(matches):

    unique_matches = {}

    for match in matches:

        pair = tuple(sorted([
            match["source_customer_id_1"],
            match["source_customer_id_2"]
        ]))

        if pair not in unique_matches:

            unique_matches[pair] = match

        else:

            existing = unique_matches[pair]

            # Prefer exact matching over fuzzy
            if (
                existing["match_method"]
                == "FUZZY_NAME_ADDRESS"
                and
                match["match_method"]
                != "FUZZY_NAME_ADDRESS"
            ):
                unique_matches[pair] = match

    return list(unique_matches.values())


# ============================================================
# 7. SAVE MATCHES TO SUPABASE
# ============================================================

def save_matches(matches):

    print()
    print("==========================================")
    print("SAVING MATCH LINKS")
    print("==========================================")

    # Remove previous generated matches
    supabase \
        .table("match_links") \
        .delete() \
        .neq("id", 0) \
        .execute()

    if not matches:

        print("No matches found.")

        return

    batch_size = 500

    for i in range(0, len(matches), batch_size):

        batch = matches[i:i + batch_size]

        (
            supabase
            .table("match_links")
            .insert(batch)
            .execute()
        )

        print(
            f"Saved matches: "
            f"{min(i + batch_size, len(matches))}"
            f"/{len(matches)}"
        )

    print("Match links saved successfully.")


# ============================================================
# 8. MAIN ENGINE
# ============================================================

def run_matching():

    print()
    print("=" * 60)
    print("MDM CUSTOMER 360 - SUPABASE MATCHING ENGINE")
    print("=" * 60)

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    customers = load_customers()

    # --------------------------------------------------------
    # Exact Email
    # --------------------------------------------------------

    email_matches = exact_email_matching(
        customers
    )

    # --------------------------------------------------------
    # Exact Phone
    # --------------------------------------------------------

    phone_matches = exact_phone_matching(
        customers
    )

    # --------------------------------------------------------
    # Exact pairs
    # --------------------------------------------------------

    exact_pairs = build_exact_pairs(
        email_matches,
        phone_matches
    )

    # --------------------------------------------------------
    # Fuzzy
    # --------------------------------------------------------

    fuzzy_matches = fuzzy_matching(
        customers,
        exact_pairs
    )

    # --------------------------------------------------------
    # Combine
    # --------------------------------------------------------

    all_matches = (
        email_matches
        + phone_matches
        + fuzzy_matches
    )

    # --------------------------------------------------------
    # Deduplicate
    # --------------------------------------------------------

    all_matches = deduplicate_matches(
        all_matches
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("==========================================")
    print("MATCHING ENGINE SUMMARY")
    print("==========================================")

    print(
        "Exact Email matches :",
        len(email_matches)
    )

    print(
        "Exact Phone matches :",
        len(phone_matches)
    )

    print(
        "Fuzzy matches       :",
        len(fuzzy_matches)
    )

    print("------------------------------------------")

    print(
        "Total unique pairs  :",
        len(all_matches)
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_matches(all_matches)

    print()
    print("=" * 60)
    print("SUPABASE MATCHING COMPLETED")
    print("=" * 60)

    return all_matches


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    run_matching()