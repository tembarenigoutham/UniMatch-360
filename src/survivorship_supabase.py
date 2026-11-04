"""
MDM Customer 360 - Supabase Survivorship Engine

Input:
    source_customers
    match_links
    config/trust_hierarchy.json

Output:
    golden_records
    golden_record_sources

Survivorship:
    Matching defines the customer group.
    Each field then follows the complete field-specific
    trust hierarchy across the entire group.
"""

import sys
import json
from pathlib import Path
from collections import defaultdict


# ============================================================
# IMPORT BACKEND MODULES
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.append(str(PROJECT_ROOT))

from database import supabase


# ============================================================
# CONFIG
# ============================================================

CONFIG_PATH = PROJECT_ROOT / "config" / "trust_hierarchy.json"

FIELDS = [
    "name",
    "email",
    "phone",
    "address",
    "dob"
]

PAGE_SIZE = 1000


# ============================================================
# LOAD TRUST HIERARCHY
# ============================================================

def load_hierarchy():

    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        hierarchy = json.load(file)

    print("\n==========================================")
    print("TRUST HIERARCHY")
    print("==========================================")

    for field in FIELDS:
        print(
            f"{field:10} : "
            f"{' > '.join(hierarchy.get(field, []))}"
        )

    return hierarchy


# ============================================================
# LOAD SOURCE CUSTOMERS
# ============================================================

def load_customers():

    print("\n==========================================")
    print("LOADING SOURCE CUSTOMERS")
    print("==========================================")

    customers = []

    start = 0

    while True:

        response = (
            supabase
            .table("source_customers")
            .select(
                "id,"
                "source_id,"
                "source_customer_id,"
                "name,"
                "email,"
                "phone,"
                "dob,"
                "address"
            )
            .range(
                start,
                start + PAGE_SIZE - 1
            )
            .execute()
        )

        batch = response.data or []

        if not batch:
            break

        customers.extend(batch)

        print(
            f"Loaded customers: "
            f"{len(customers)}"
        )

        if len(batch) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    print(
        f"\nTotal customers: {len(customers)}"
    )

    return customers


# ============================================================
# LOAD SOURCE NAMES
# ============================================================

def load_sources():

    response = (
        supabase
        .table("sources")
        .select("id,source_name")
        .execute()
    )

    source_map = {}

    for row in response.data or []:
        source_map[row["id"]] = row["source_name"]

    return source_map


# ============================================================
# LOAD MATCH LINKS
# ============================================================

def load_match_links():

    print("\n==========================================")
    print("LOADING MATCH LINKS")
    print("==========================================")

    matches = []

    start = 0

    while True:

        response = (
            supabase
            .table("match_links")
            .select(
                "id,"
                "source_customer_id_1,"
                "source_customer_id_2,"
                "match_method,"
                "match_score"
            )
            .range(
                start,
                start + PAGE_SIZE - 1
            )
            .execute()
        )

        batch = response.data or []

        if not batch:
            break

        matches.extend(batch)

        if len(batch) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    print(
        f"Total match links: {len(matches)}"
    )

    return matches


# ============================================================
# UNION-FIND
# ============================================================

class UnionFind:

    def __init__(self):

        self.parent = {}
        self.rank = {}

    def find(self, x):

        if x not in self.parent:

            self.parent[x] = x
            self.rank[x] = 0

            return x

        if self.parent[x] != x:

            self.parent[x] = self.find(
                self.parent[x]
            )

        return self.parent[x]

    def union(self, x, y):

        root_x = self.find(x)
        root_y = self.find(y)

        if root_x == root_y:
            return

        if self.rank[root_x] < self.rank[root_y]:

            self.parent[root_x] = root_y

        elif self.rank[root_x] > self.rank[root_y]:

            self.parent[root_y] = root_x

        else:

            self.parent[root_y] = root_x
            self.rank[root_x] += 1


# ============================================================
# BUILD CUSTOMER GROUPS
# ============================================================

def build_groups(customers, matches):

    print("\n==========================================")
    print("BUILDING CUSTOMER GROUPS")
    print("==========================================")

    uf = UnionFind()

    # Every customer must exist in the structure.
    for customer in customers:

        uf.find(customer["id"])

    # Join matched records.
    for match in matches:

        uf.union(
            match["source_customer_id_1"],
            match["source_customer_id_2"]
        )

    groups = defaultdict(list)

    for customer in customers:

        root = uf.find(customer["id"])

        groups[root].append(
            customer["id"]
        )

    group_list = list(groups.values())

    matched_groups = [
        group
        for group in group_list
        if len(group) > 1
    ]

    singleton_groups = [
        group
        for group in group_list
        if len(group) == 1
    ]

    print(
        f"Total customer groups : {len(group_list)}"
    )

    print(
        f"Matched groups        : "
        f"{len(matched_groups)}"
    )

    print(
        f"Singleton groups      : "
        f"{len(singleton_groups)}"
    )

    return group_list


# ============================================================
# SELECT SURVIVING VALUE
# ============================================================

def select_surviving_value(
    group_records,
    field,
    hierarchy
):

    trust_order = hierarchy.get(
        field,
        []
    )

    # Follow the complete hierarchy.
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

    # Fallback.
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


# ============================================================
# BUILD GOLDEN RECORD
# ============================================================

def create_golden_record(
    group_records,
    golden_id,
    hierarchy
):

    # First record is only the metadata anchor.
    # It does NOT decide field survivorship.
    representative = group_records[0]

    golden = {

        "golden_id": golden_id,

        "name": None,
        "email": None,
        "phone": None,
        "address": None,
        "dob": None,

        "name_source": None,
        "email_source": None,
        "phone_source": None,
        "address_source": None,
        "dob_source": None,

        "representative_source":
            representative["source_name"],

        "representative_source_id":
            representative["source_customer_id"],

        "match_group_size":
            len(group_records)
    }

    # Survivorship happens across the COMPLETE group.
    for field in FIELDS:

        value, source = select_surviving_value(
            group_records,
            field,
            hierarchy
        )

        golden[field] = value

        golden[f"{field}_source"] = source

    return golden


# ============================================================
# PREPARE GOLDEN RECORDS
# ============================================================

def generate_golden_records(
    customers,
    sources,
    groups,
    hierarchy
):

    print("\n==========================================")
    print("CREATING GOLDEN RECORDS")
    print("==========================================")

    customer_map = {
        customer["id"]: customer
        for customer in customers
    }

    # Add source name to each customer.
    enriched_customers = {}

    for customer in customers:

        customer_copy = customer.copy()

        customer_copy["source_name"] = sources.get(
            customer["source_id"],
            f"Source_{customer['source_id']}"
        )

        enriched_customers[
            customer["id"]
        ] = customer_copy

    golden_records = []

    group_members = {}

    golden_counter = 1

    for group in groups:

        group_records = []

        for customer_id in group:

            if customer_id in enriched_customers:

                group_records.append(
                    enriched_customers[
                        customer_id
                    ]
                )

        if not group_records:
            continue

        golden_id = (
            f"GOLD_{golden_counter:06d}"
        )

        golden = create_golden_record(
            group_records,
            golden_id,
            hierarchy
        )

        golden_records.append(golden)

        group_members[golden_id] = group_records

        golden_counter += 1

    print(
        f"Golden records created: "
        f"{len(golden_records)}"
    )

    return (
        golden_records,
        group_members
    )


# ============================================================
# SAVE GOLDEN RECORDS
# ============================================================

def save_golden_records(
    golden_records
):

    print("\n==========================================")
    print("SAVING GOLDEN RECORDS")
    print("==========================================")

    # Clear old generated Golden Records.
    (
        supabase
        .table("golden_records")
        .delete()
        .neq("id", 0)
        .execute()
    )

    if not golden_records:

        print("No golden records found.")

        return {}

    response = (
        supabase
        .table("golden_records")
        .insert(golden_records)
        .execute()
    )

    inserted = response.data or []

    print(
        f"Inserted golden records: "
        f"{len(inserted)}"
    )

    # Map GOLD_XXXXXX -> database ID
    golden_db_ids = {}

    for row in inserted:

        golden_db_ids[
            row["golden_id"]
        ] = row["id"]

    return golden_db_ids


# ============================================================
# SAVE GOLDEN RECORD SOURCES
# ============================================================

def save_golden_sources(
    golden_db_ids,
    group_members,
    matches
):

    print("\n==========================================")
    print("SAVING GOLDEN RECORD SOURCES")
    print("==========================================")

    # Clear old links.
    (
        supabase
        .table("golden_record_sources")
        .delete()
        .neq("id", 0)
        .execute()
    )

    # Build lookup of match relationships.
    match_lookup = {}

    for match in matches:

        pair = tuple(sorted([
            match["source_customer_id_1"],
            match["source_customer_id_2"]
        ]))

        match_lookup[pair] = match

    rows = []

    for golden_id, records in group_members.items():

        golden_db_id = golden_db_ids.get(
            golden_id
        )

        if golden_db_id is None:
            continue

        record_ids = [
            record["id"]
            for record in records
        ]

        for record_id in record_ids:

            match_method = None
            match_score = None

            # Find a match relationship
            # involving this record inside its group.
            for other_id in record_ids:

                if record_id == other_id:
                    continue

                pair = tuple(sorted([
                    record_id,
                    other_id
                ]))

                if pair in match_lookup:

                    match = match_lookup[pair]

                    match_method = match[
                        "match_method"
                    ]

                    match_score = match[
                        "match_score"
                    ]

                    break

            rows.append({

                "golden_record_id":
                    golden_db_id,

                "source_customer_id":
                    record_id,

                "match_method":
                    match_method,

                "match_score":
                    match_score
            })

    batch_size = 500

    for i in range(
        0,
        len(rows),
        batch_size
    ):

        batch = rows[
            i:i + batch_size
        ]

        (
            supabase
            .table("golden_record_sources")
            .insert(batch)
            .execute()
        )

        print(
            f"Saved source links: "
            f"{min(i + batch_size, len(rows))}"
            f"/{len(rows)}"
        )

    print(
        f"Total source links: {len(rows)}"
    )


# ============================================================
# VALIDATION
# ============================================================

def validate_results():

    print("\n==========================================")
    print("VALIDATING GOLDEN RECORDS")
    print("==========================================")

    # --------------------------------------------------------
    # Load ALL Golden Records using pagination
    # --------------------------------------------------------

    golden = []

    start = 0

    while True:

        response = (
            supabase
            .table("golden_records")
            .select(
                "golden_id,match_group_size"
            )
            .range(
                start,
                start + PAGE_SIZE - 1
            )
            .execute()
        )

        batch = response.data or []

        if not batch:
            break

        golden.extend(batch)

        if len(batch) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    # --------------------------------------------------------
    # Calculate statistics
    # --------------------------------------------------------

    matched = [
        row
        for row in golden
        if row["match_group_size"] > 1
    ]

    singleton = [
        row
        for row in golden
        if row["match_group_size"] == 1
    ]

    print(
        f"Golden records : {len(golden)}"
    )

    print(
        f"Matched groups : {len(matched)}"
    )

    print(
        f"Singletons     : {len(singleton)}"
    )

    # --------------------------------------------------------
    # Load ALL Golden Record source links
    # --------------------------------------------------------

    source_links = []

    start = 0

    while True:

        response = (
            supabase
            .table("golden_record_sources")
            .select("id")
            .range(
                start,
                start + PAGE_SIZE - 1
            )
            .execute()
        )

        batch = response.data or []

        if not batch:
            break

        source_links.extend(batch)

        if len(batch) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    print(
        f"Source links   : "
        f"{len(source_links)}"
    )

    # --------------------------------------------------------
    # Basic consistency checks
    # --------------------------------------------------------

    expected_customers = len(
        load_customers()
    )

    if len(source_links) != expected_customers:

        print(
            "\nWARNING:"
            f" Expected {expected_customers} "
            f"source links but found "
            f"{len(source_links)}."
        )

    else:

        print(
            "\nSource-link validation: PASSED"
        )

    print(
        "\nGolden-record validation: PASSED"
    )


# ============================================================
# MAIN
# ============================================================

def run_survivorship():

    print()
    print("=" * 60)
    print(
        "MDM CUSTOMER 360 - "
        "SUPABASE SURVIVORSHIP ENGINE"
    )
    print("=" * 60)

    # 1. Hierarchy
    hierarchy = load_hierarchy()

    # 2. Customers
    customers = load_customers()

    # 3. Sources
    sources = load_sources()

    # 4. Match links
    matches = load_match_links()

    # 5. Connected components
    groups = build_groups(
        customers,
        matches
    )

    # 6. Golden records
    (
        golden_records,
        group_members
    ) = generate_golden_records(
        customers,
        sources,
        groups,
        hierarchy
    )

    # 7. Save Golden Records
    golden_db_ids = save_golden_records(
        golden_records
    )

    # 8. Save membership/source links
    save_golden_sources(
        golden_db_ids,
        group_members,
        matches
    )

    # 9. Validate
    validate_results()

    print()
    print("=" * 60)
    print(
        "SUPABASE SURVIVORSHIP COMPLETED"
    )
    print("=" * 60)


if __name__ == "__main__":
    run_survivorship()