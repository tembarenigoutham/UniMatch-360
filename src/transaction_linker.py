"""
transaction_linker.py

Links transaction records to Golden Record IDs.

Input:
  - transaction_data.csv (raw transactions with source Account_ID)
  - golden_records.csv (with GOLDEN_ID and source tracking)

Output:
  - transactions_with_golden_id.csv (transactions linked to GOLDEN_ID)

Usage:
    python transaction_linker.py
"""

import pandas as pd
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

data_raw = project_root / "data" / "raw"
data_output = project_root / "data" / "output"

# ============================================================
# 1. LOAD DATA
# ============================================================

def load_data():
    """Load transactions and golden records"""
    try:
        transactions = pd.read_csv(str(data_raw / "transaction_data.csv"))
        golden_records = pd.read_csv(str(data_output / "golden_records.csv"))
        
        logger.info(f"Loaded {len(transactions)} transactions")
        logger.info(f"Loaded {len(golden_records)} golden records")
        
        # Debug: Show golden records structure
        logger.info(f"Golden records columns: {list(golden_records.columns)}")
        
        return transactions, golden_records
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        raise


# ============================================================
# 2. BUILD ID MAPPING (FIXED)
# ============================================================

def build_id_mapping(golden_records):
    """
    Create mapping from (source, source_id) -> GOLDEN_ID
    
    The golden_records has a 'matched_source_ids' column that contains
    pipe-delimited IDs from all matched sources.
    
    Example:
      matched_source_ids: "C0490|CC_114|L_521"
      
    We need to parse this and map each to the GOLDEN_ID:
      "SourceA_C0490" -> GOLD_000001
      "SourceB_CC_114" -> GOLD_000001
      "SourceC_L_521" -> GOLD_000001
    """
    id_mapping = {}
    
    for _, row in golden_records.iterrows():
        golden_id = row.get("GOLDEN_ID")
        matched_ids_str = row.get("matched_source_ids")
        
        if pd.isna(matched_ids_str):
            logger.warning(f"No matched_source_ids for {golden_id}")
            continue
        
        # Parse pipe-delimited IDs
        matched_ids = str(matched_ids_str).split("|")
        
        for matched_id in matched_ids:
            matched_id = matched_id.strip()  # Remove whitespace
            
            if not matched_id:
                continue
            
            # Infer source from the ID prefix
            source = infer_source_from_account_id(matched_id)
            
            if source:
                key = f"{source}_{matched_id}"
                id_mapping[key] = golden_id
    
    logger.info(f"Built mapping for {len(id_mapping)} source ID entries from {len(golden_records)} golden records")
    return id_mapping


# ============================================================
# 3. LINK TRANSACTIONS
# ============================================================

def infer_source_from_account_id(account_id):
    """
    Infer which source system this Account_ID came from.
    
    Convention:
    - Core Banking (SourceA): IDs like "C001", "C0252", etc.
    - Credit Card (SourceB): IDs like "CC001", "CC701", etc.
    - Loan System (SourceC): IDs like "L001", "L521", etc.
    """
    account_id_str = str(account_id).upper()
    
    # More specific matching
    if account_id_str.startswith(("C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9")):
        return "SourceA"
    elif account_id_str.startswith(("CC", "CRED")):
        return "SourceB"
    elif account_id_str.startswith(("L", "LOAN")):
        return "SourceC"
    else:
        logger.warning(f"Could not infer source for account ID: {account_id}")
        return None


def link_transactions(transactions, id_mapping):
    """
    Map each transaction's Account_ID to GOLDEN_ID.
    """
    
    linked_txns = []
    unlinked_count = 0
    unlinked_details = {}
    
    for _, txn in transactions.iterrows():
        # Get Account_ID (handle column name variations)
        account_id = txn.get("Account_ID") or txn.get("account_id")
        
        if pd.isna(account_id):
            logger.warning("Transaction has null Account_ID")
            unlinked_count += 1
            continue
        
        # Infer source
        source = infer_source_from_account_id(account_id)
        if not source:
            unlinked_count += 1
            continue
        
        # Look up golden ID using (source, account_id) key
        mapping_key = f"{source}_{account_id}"
        golden_id = id_mapping.get(mapping_key)
        
        if not golden_id:
            # Track unlinked accounts
            if account_id not in unlinked_details:
                unlinked_details[account_id] = 0
            unlinked_details[account_id] += 1
            unlinked_count += 1
            # Skip this transaction
            continue
        
        # Create linked transaction
        linked_txn = txn.to_dict()
        linked_txn["GOLDEN_ID"] = golden_id
        linked_txn["source_system"] = source
        
        linked_txns.append(linked_txn)
    
    # Log summary
    logger.info(f"✅ Linked {len(linked_txns)} transactions")
    if unlinked_count > 0:
        logger.warning(f"⚠️  Could not link {unlinked_count} transactions")
        logger.warning(f"Top 10 unlinked accounts: {sorted(unlinked_details.items(), key=lambda x: x[1], reverse=True)[:10]}")
    
    return pd.DataFrame(linked_txns), unlinked_count, unlinked_details


# ============================================================
# 4. SAVE RESULTS
# ============================================================

def save_linked_transactions(df, unlinked_details):
    """Save transactions with GOLDEN_ID"""
    
    # Reorder columns: GOLDEN_ID first, then original columns
    cols = ["GOLDEN_ID", "source_system"] + [col for col in df.columns if col not in ["GOLDEN_ID", "source_system"]]
    
    output_df = df[cols]
    output_df.to_csv(str(data_output / "transactions_with_golden_id.csv"), index=False)
    
    logger.info("Saved transactions_with_golden_id.csv")
    
    # Print summary
    print("\n" + "="*60)
    print("TRANSACTION LINKING SUMMARY")
    print("="*60)
    print(f"Total Linked Transactions: {len(output_df)}")
    print(f"Unique Golden Customers: {output_df['GOLDEN_ID'].nunique()}")
    if 'Date' in output_df.columns:
        print(f"Date Range: {output_df['Date'].min()} to {output_df['Date'].max()}")
    if 'Amount' in output_df.columns:
        print(f"Total Amount: {output_df['Amount'].sum():.2f}")
    
    print("\nSample Transaction:")
    if len(output_df) > 0:
        print(output_df.iloc[0])
    else:
        print("No transactions linked!")
    
    if unlinked_details:
        print("\n⚠️  TOP 20 UNLINKED ACCOUNT IDS:")
        for account_id, count in sorted(unlinked_details.items(), key=lambda x: x[1], reverse=True)[:20]:
            print(f"  {account_id}: {count} transactions")
    
    print("="*60 + "\n")
    
    return output_df


# ============================================================
# 5. MAIN PIPELINE
# ============================================================

def main():
    """Execute the transaction linker"""
    
    try:
        # Step 1: Load data
        logger.info("Loading data...")
        transactions, golden_records = load_data()
        
        # Step 2: Build ID mapping
        logger.info("Building source ID to Golden ID mapping...")
        id_mapping = build_id_mapping(golden_records)
        
        # Step 3: Link transactions
        logger.info("Linking transactions to golden records...")
        linked_txns, unlinked_count, unlinked_details = link_transactions(transactions, id_mapping)
        
        # Step 4: Save results
        logger.info("Saving results...")
        linked_txns = save_linked_transactions(linked_txns, unlinked_details)
        
        # Calculate linkage rate
        linkage_rate = (len(linked_txns) / len(transactions) * 100) if len(transactions) > 0 else 0
        logger.info(f"📊 Linkage Rate: {linkage_rate:.1f}% ({len(linked_txns)}/{len(transactions)})")
        
        if linkage_rate < 90:
            logger.warning(f"⚠️  Linkage rate below 90%! Investigate unlinked accounts.")
        else:
            logger.info(f"✅ Transaction linking completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()