"""
survivorship_engine.py

Takes matched customer pairs and creates Golden Records using trust hierarchy.

Input:
  - normalized_customers.csv (from matching.py)
  - match_results.csv (from matching.py)
  - trust_hierarchy.json (config)

Output:
  - golden_records.csv (single version of truth for each customer)

Usage:
    python survivorship_engine.py
"""

import pandas as pd
import json
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Path resolution
script_path = Path(__file__).parent
if script_path.name == "src":
    project_root = script_path.parent
else:
    project_root = script_path

data_output = project_root / "data" / "output"
config_dir = project_root / "config"

# ============================================================
# 1. LOAD DATA
# ============================================================

def load_data():
    """Load normalized customers, matches, and trust hierarchy"""
    try:
        customers = pd.read_csv(str(data_output / "normalized_customers.csv"))
        matches = pd.read_csv(str(data_output / "match_results.csv"))
        
        with open(str(config_dir / "trust_hierarchy.json")) as f:
            hierarchy = json.load(f)
        
        logger.info(f"Loaded {len(customers)} customers, {len(matches)} matches")
        return customers, matches, hierarchy
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise


# ============================================================
# 2. SURVIVORSHIP LOGIC
# ============================================================

def select_winning_value(record_a, record_b, field, hierarchy):
    """
    Select which source's value wins based on trust hierarchy.
    
    Args:
        record_a: dict with customer data + "source" key
        record_b: dict with customer data + "source" key
        field: field name (e.g., "email", "phone")
        hierarchy: dict with trust order per field
    
    Returns:
        tuple: (winning_value, winning_source)
    """
    
    # Get trust order for this field
    trust_order = hierarchy.get(field, [])
    
    if not trust_order:
        logger.warning(f"No trust hierarchy defined for {field}, using first non-empty")
    
    # Check each source in priority order
    for source in trust_order:
        if record_a.get("source") == source and record_a.get(field):
            return record_a[field], source
        if record_b.get("source") == source and record_b.get(field):
            return record_b[field], source
    
    # Fallback: prefer non-empty value from record_a, then record_b
    if record_a.get(field):
        return record_a[field], record_a.get("source")
    if record_b.get(field):
        return record_b[field], record_b.get("source")
    
    return None, None


def merge_two_records(record_a, record_b, hierarchy, fields_to_merge):
    """
    Merge two matched customer records into one.
    
    Returns:
        dict: merged record with source tracking
    """
    merged = {}
    source_trace = {}
    
    for field in fields_to_merge:
        value, source = select_winning_value(record_a, record_b, field, hierarchy)
        merged[field] = value
        source_trace[f"{field}_source"] = source
    
    return merged, source_trace


# ============================================================
# 3. BUILD MATCH GROUPS
# ============================================================

def build_match_groups(matches):
    """
    Convert match pairs into groups of connected records.
    
    Example:
        If A matches B, and B matches C:
        Group: {A, B, C}
    """
    from collections import defaultdict
    
    # Union-Find to group connected records
    parent = {}
    
    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
    
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py
    
    # Build groups
    for _, match in matches.iterrows():
        union(match["source_a"], match["source_b"])
    
    # Group by root parent
    groups = defaultdict(list)
    for key in parent:
        root = find(key)
        groups[root].append(key)
    
    logger.info(f"Found {len(groups)} customer groups")
    return list(groups.values())


# ============================================================
# 4. CREATE GOLDEN RECORDS
# ============================================================

def create_golden_records(customers, match_groups, hierarchy):
    """
    Create one Golden Record per match group.
    
    Returns:
        DataFrame with golden records
    """
    
    golden_records = []
    fields_to_merge = ["name", "email", "phone", "address", "dob"]
    
    # Create index for fast lookup
    customer_index = {}
    for _, cust in customers.iterrows():
        key = (cust["source"], cust["source_id"])
        customer_index[key] = cust.to_dict()
    
    golden_id_counter = 1
    
    for group in match_groups:
        # Fetch all records in this group
        group_records = []
        source_ids = []
        
        for source_id in group:
            # Find which source this ID came from
            for source in ["SourceA", "SourceB", "SourceC"]:
                key = (source, source_id)
                if key in customer_index:
                    group_records.append(customer_index[key])
                    source_ids.append(source_id)
                    break
        
        if not group_records:
            logger.warning(f"No records found for group: {group}")
            continue
        
        # Start with first record
        golden_record = group_records[0].copy()
        source_trace = {}
        
        # Apply survivorship by merging all records in the group
        for i, record in enumerate(group_records):
            for field in fields_to_merge:
                value, source = select_winning_value(
                    golden_record, record, field, hierarchy
                )
                golden_record[field] = value
                source_trace[f"{field}_source"] = source
        
        # Add metadata
        golden_record["GOLDEN_ID"] = f"GOLD_{str(golden_id_counter).zfill(6)}"
        golden_record["matched_source_ids"] = "|".join(source_ids)
        golden_record["match_group_size"] = len(group)
        
        # Add source trace
        for field, source in source_trace.items():
            golden_record[field] = source
        
        golden_records.append(golden_record)
        golden_id_counter += 1
    
    # Handle unmatched records (singletons)
    matched_ids = set()
    for group in match_groups:
        matched_ids.update(group)
    
    for _, cust in customers.iterrows():
        if cust["source_id"] not in matched_ids:
            golden_record = cust.to_dict()
            golden_record["GOLDEN_ID"] = f"GOLD_{str(golden_id_counter).zfill(6)}"
            golden_record["matched_source_ids"] = cust["source_id"]
            golden_record["match_group_size"] = 1
            
            # Source trace for singletons
            for field in fields_to_merge:
                golden_record[f"{field}_source"] = cust["source"]
            
            golden_records.append(golden_record)
            golden_id_counter += 1
    
    logger.info(f"Created {len(golden_records)} golden records")
    return pd.DataFrame(golden_records)


# ============================================================
# 5. SAVE GOLDEN RECORDS
# ============================================================

def save_golden_records(df):
    """Save golden records with proper column ordering"""
    
    # Define output columns
    core_fields = ["GOLDEN_ID", "name", "email", "phone", "address", "dob"]
    source_fields = ["name_source", "email_source", "phone_source", "address_source", "dob_source"]
    meta_fields = ["source", "source_id", "matched_source_ids", "match_group_size"]
    
    # Select available columns
    output_cols = [col for col in core_fields + source_fields + meta_fields if col in df.columns]
    
    golden_df = df[output_cols].copy()
    golden_df.to_csv(str(data_output / "golden_records.csv"), index=False)
    
    logger.info("Saved golden_records.csv")
    
    # Print summary
    print("\n" + "="*60)
    print("GOLDEN RECORD CREATION SUMMARY")
    print("="*60)
    print(f"Total Golden Records: {len(golden_df)}")
    print(f"Matched Groups (size > 1): {len([g for g in golden_df['match_group_size'] if g > 1])}")
    print(f"Unmatched (singletons): {len([g for g in golden_df['match_group_size'] if g == 1])}")
    print("\nSample Golden Record:")
    print(golden_df.iloc[0] if len(golden_df) > 0 else "No records")
    print("\n" + "="*60)
    
    return golden_df


# ============================================================
# 6. MAIN PIPELINE
# ============================================================

def main():
    """Execute the survivorship engine"""
    
    try:
        # Step 1: Load data
        logger.info("Loading data...")
        customers, matches, hierarchy = load_data()
        
        # Step 2: Build match groups (handle transitive matches)
        logger.info("Building match groups...")
        match_groups = build_match_groups(matches)
        
        # Step 3: Create golden records
        logger.info("Creating golden records with survivorship logic...")
        golden_df = create_golden_records(customers, match_groups, hierarchy)
        
        # Step 4: Save results
        logger.info("Saving results...")
        golden_df = save_golden_records(golden_df)
        
        logger.info("✅ Survivorship engine completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
