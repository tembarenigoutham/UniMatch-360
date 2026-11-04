import pandas as pd
import re
from rapidfuzz import fuzz


# ============================================================
# HELPER: Flexible column detection
# ============================================================

def find_column(df, possible_names):
    """Find column case-insensitively"""
    for possible in possible_names:
        for actual in df.columns:
            if actual.lower() == possible.lower():
                return actual
    raise ValueError(f"None of {possible_names} found in columns: {list(df.columns)}")


# ============================================================
# PATH RESOLUTION
# ============================================================

from pathlib import Path
import os

# Find project root (go up from src/ if we're there)
script_path = Path(__file__).parent
if script_path.name == "src":
    project_root = script_path.parent
else:
    project_root = script_path

data_raw = project_root / "data" / "raw"
data_output = project_root / "data" / "output"

# Create output dir if needed
data_output.mkdir(parents=True, exist_ok=True)

# ============================================================
# 1. LOAD DATA
# ============================================================

core = pd.read_csv(str(data_raw / "core_banking.csv"))
credit = pd.read_csv(str(data_raw / "credit_card.csv"))
loan = pd.read_csv(str(data_raw / "loan_system.csv"))

reference = pd.read_csv(str(data_raw / "reference_data.csv"))


# ============================================================
# 2. NORMALIZATION FUNCTIONS
# ============================================================

def normalize_name(value):
    """Proper case without breaking names like McDonald"""
    if pd.isna(value):
        return ""

    value = str(value).strip()
    # Remove extra spaces
    value = re.sub(r"\s+", " ", value)
    
    # Capitalize each word properly (McCarthy, O'Brien, etc.)
    return " ".join(word.capitalize() for word in value.split())


def normalize_email(value):
    if pd.isna(value):
        return ""

    return str(value).strip().lower()


def normalize_phone(value):
    if pd.isna(value):
        return ""

    value = str(value).strip()
    # Keep digits only
    value = re.sub(r"\D", "", value)

    return value


# ============================================================
# 3. ADDRESS STANDARDIZATION
# ============================================================

address_mapping = dict(
    zip(
        reference["Short_Form"].astype(str).str.lower(),
        reference["Long_Form"].astype(str).str.lower()
    )
)


def normalize_address(value):
    if pd.isna(value):
        return ""

    value = str(value).strip().lower()

    # Use supplied reference data
    for short_form, long_form in address_mapping.items():
        value = value.replace(short_form, long_form)

    # Remove extra spaces
    value = re.sub(r"\s+", " ", value)

    return value.strip()


# ============================================================
# 4. CORE BANKING → COMMON FORMAT
# ============================================================

# Use flexible column detection
core_id_col = find_column(core, ["Customer_ID", "ID", "Cust_ID"])
core_name_col = find_column(core, ["Name"])
core_email_col = find_column(core, ["Email"])
core_phone_col = find_column(core, ["Phone"])
core_dob_col = find_column(core, ["DOB", "Date_of_Birth"])
core_address_col = find_column(core, ["Address"])

core_common = core.rename(columns={
    core_id_col: "source_id",
    core_name_col: "name",
    core_email_col: "email",
    core_phone_col: "phone",
    core_dob_col: "dob",
    core_address_col: "address"
})

core_common["source"] = "SourceA"
core_common = core_common[["source", "source_id", "name", "email", "phone", "dob", "address"]]

# Deduplicate within source
core_common = core_common.drop_duplicates(subset=["source_id"], keep="first")


# ============================================================
# 5. CREDIT CARD → COMMON FORMAT
# ============================================================

credit_id_col = find_column(credit, ["Cust_Ref", "Customer_ID", "ID"])
credit_name_col = find_column(credit, ["Name"])
credit_email_col = find_column(credit, ["Email"])
credit_phone_col = find_column(credit, ["Phone"])
credit_address_col = find_column(credit, ["Address"])

credit_common = credit.rename(columns={
    credit_id_col: "source_id",
    credit_name_col: "name",
    credit_email_col: "email",
    credit_phone_col: "phone",
    credit_address_col: "address"
})

credit_common["source"] = "SourceB"
credit_common["dob"] = None

credit_common = credit_common[["source", "source_id", "name", "email", "phone", "dob", "address"]]

# Deduplicate within source
credit_common = credit_common.drop_duplicates(subset=["source_id"], keep="first")


# ============================================================
# 6. LOAN SYSTEM → COMMON FORMAT
# ============================================================

loan_id_col = find_column(loan, ["Loan_Cust_ID", "Customer_ID", "ID"])
loan_name_col = find_column(loan, ["Name"])
loan_phone_col = find_column(loan, ["Phone"])
loan_address_col = find_column(loan, ["Address"])

loan_common = loan.rename(columns={
    loan_id_col: "source_id",
    loan_name_col: "name",
    loan_phone_col: "phone",
    loan_address_col: "address"
})

loan_common["source"] = "SourceC"
loan_common["email"] = None
loan_common["dob"] = None

loan_common = loan_common[["source", "source_id", "name", "email", "phone", "dob", "address"]]

# Deduplicate within source
loan_common = loan_common.drop_duplicates(subset=["source_id"], keep="first")


# ============================================================
# 7. COMBINE ALL SOURCES
# ============================================================

customers = pd.concat(
    [
        core_common,
        credit_common,
        loan_common
    ],
    ignore_index=True
)


# ============================================================
# 8. NORMALIZE DATA
# ============================================================

customers["name"] = customers["name"].apply(normalize_name)
customers["email"] = customers["email"].apply(normalize_email)
customers["phone"] = customers["phone"].apply(normalize_phone)
customers["address"] = customers["address"].apply(normalize_address)


# ============================================================
# 9. EXACT EMAIL MATCHING
# ============================================================

print()
print("==========================================")
print("EXACT EMAIL MATCHING")
print("==========================================")

email_records = customers[customers["email"] != ""]

duplicate_emails = (
    email_records
    .groupby("email")
    .filter(lambda group: len(group) > 1)
)

email_matches = []

for email, group in duplicate_emails.groupby("email"):

    records = group.to_dict("records")

    for i in range(len(records)):

        for j in range(i + 1, len(records)):

            record_a = records[i]
            record_b = records[j]

            if record_a["source_id"] == record_b["source_id"]:
                continue

            email_matches.append({
                "source_a": record_a["source_id"],
                "source_b": record_b["source_id"],
                "source_a_system": record_a["source"],
                "source_b_system": record_b["source"],
                "method": "EXACT_EMAIL",
                "score": 1.0
            })


print("Exact email matches:", len(email_matches))


# ============================================================
# 10. EXACT PHONE MATCHING
# ============================================================

print()
print("==========================================")
print("EXACT PHONE MATCHING")
print("==========================================")

phone_records = customers[customers["phone"] != ""]

duplicate_phones = (
    phone_records
    .groupby("phone")
    .filter(lambda group: len(group) > 1)
)

phone_matches = []

for phone, group in duplicate_phones.groupby("phone"):

    records = group.to_dict("records")

    for i in range(len(records)):

        for j in range(i + 1, len(records)):

            record_a = records[i]
            record_b = records[j]

            if record_a["source_id"] == record_b["source_id"]:
                continue

            phone_matches.append({
                "source_a": record_a["source_id"],
                "source_b": record_b["source_id"],
                "source_a_system": record_a["source"],
                "source_b_system": record_b["source"],
                "method": "EXACT_PHONE",
                "score": 1.0
            })


print("Exact phone matches:", len(phone_matches))


# ============================================================
# 11. STORE EXACT MATCH PAIRS
# ============================================================

exact_pairs = set()

for match in email_matches:

    pair = tuple(sorted([
        match["source_a"],
        match["source_b"]
    ]))

    exact_pairs.add(pair)


for match in phone_matches:

    pair = tuple(sorted([
        match["source_a"],
        match["source_b"]
    ]))

    exact_pairs.add(pair)


# ============================================================
# 12. FUZZY MATCHING CONFIGURATION
# ============================================================

FUZZY_THRESHOLD = 0.85


# ============================================================
# 13. FUZZY NAME + ADDRESS MATCHING
# ============================================================

print()
print("==========================================")
print("FUZZY NAME + ADDRESS MATCHING")
print("==========================================")

fuzzy_matches = []

records = customers.to_dict("records")

total_comparisons = 0


for i in range(len(records)):

    record_a = records[i]

    for j in range(i + 1, len(records)):

        record_b = records[j]

        # Same record
        if record_a["source_id"] == record_b["source_id"]:
            continue

        # If exact matching already identified the pair,
        # do not process it again with fuzzy matching.
        pair = tuple(sorted([
            record_a["source_id"],
            record_b["source_id"]
        ]))

        if pair in exact_pairs:
            continue

        # We need Name and Address for fuzzy matching
        if not record_a["name"] or not record_b["name"]:
            continue

        if not record_a["address"] or not record_b["address"]:
            continue

        total_comparisons += 1

        # Name similarity
        name_score = fuzz.ratio(
            record_a["name"].lower(),
            record_b["name"].lower()
        ) / 100

        # Address similarity
        address_score = fuzz.ratio(
            record_a["address"].lower(),
            record_b["address"].lower()
        ) / 100

        # Both fields must meet the threshold
        if (
            name_score >= FUZZY_THRESHOLD
            and
            address_score >= FUZZY_THRESHOLD
        ):

            final_score = (
                name_score + address_score
            ) / 2

            fuzzy_matches.append({
                "source_a": record_a["source_id"],
                "source_b": record_b["source_id"],
                "source_a_system": record_a["source"],
                "source_b_system": record_b["source"],
                "method": "FUZZY_NAME_ADDRESS",
                "name_score": round(name_score, 4),
                "address_score": round(address_score, 4),
                "score": round(final_score, 4)
            })


print("Fuzzy comparisons performed:", total_comparisons)
print("Fuzzy matches found:", len(fuzzy_matches))


# ============================================================
# 14. DISPLAY FUZZY MATCH EXAMPLES
# ============================================================

if fuzzy_matches:

    print()
    print("Sample fuzzy matches:")

    for match in fuzzy_matches[:20]:

        print(
            match["source_a"],
            "<->",
            match["source_b"],
            "| Name:",
            match["name_score"],
            "| Address:",
            match["address_score"],
            "| Final:",
            match["score"]
        )


# ============================================================
# 15. CREATE ALL MATCH RESULTS
# ============================================================

all_matches = (
    email_matches
    + phone_matches
    + fuzzy_matches
)


# ============================================================
# 16. SAVE MATCH RESULTS
# ============================================================

matches_df = pd.DataFrame(all_matches)

matches_df.to_csv(
    str(data_output / "match_results.csv"),
    index=False
)


# ============================================================
# 17. SAVE NORMALIZED CUSTOMERS
# ============================================================

customers.to_csv(
    str(data_output / "normalized_customers.csv"),
    index=False
)


# ============================================================
# 18. FINAL SUMMARY
# ============================================================

print()
print("==========================================")
print("MATCHING ENGINE SUMMARY")
print("==========================================")

print("Exact Email matches :", len(email_matches))
print("Exact Phone matches :", len(phone_matches))
print("Fuzzy matches       :", len(fuzzy_matches))
print("------------------------------------------")
print("Total match pairs   :", len(all_matches))

print()
print("Saved results to:")
print("  - match_results.csv")
print("  - normalized_customers.csv")
