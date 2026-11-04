"""
clean_4_features.py

Simple cleaning script for 4 features only:
- name → standardized_name
- phone → standardized_phone
- email → standardized_email
- address → standardized_address

Adds new columns to original CSV (does NOT remove original columns).

Usage:
    python clean_4_features.py --input core_banking.csv --output core_banking_cleaned.csv
"""

import argparse
import re
from pathlib import Path
import pandas as pd


def load_reference_data(ref_path):
    """Load address standardization mapping from reference_data.csv"""
    if not ref_path.exists():
        print(f"Warning: {ref_path} not found - address standardization skipped")
        return {}
    
    ref = pd.read_csv(ref_path, dtype=str)
    ref.columns = [c.strip() for c in ref.columns]
    
    if "Short_Form" not in ref.columns or "Long_Form" not in ref.columns:
        print("Error: reference_data.csv must have 'Short_Form' and 'Long_Form' columns")
        return {}
    
    return dict(zip(ref["Short_Form"].str.strip(), ref["Long_Form"].str.strip()))


def clean_name(name):
    """Trim and convert to proper case"""
    if pd.isna(name) or str(name).strip() == "":
        return ""
    return " ".join(word.capitalize() for word in str(name).split())


def clean_phone(phone):
    """Extract digits only"""
    if pd.isna(phone) or str(phone).strip() == "":
        return ""
    return re.sub(r"\D", "", str(phone))


def clean_email(email):
    """Trim whitespace and convert to lowercase"""
    if pd.isna(email) or str(email).strip() == "":
        return ""
    return str(email).strip().lower()


def standardize_address(address, ref_map):
    """Replace short-form address tokens with long form"""
    if pd.isna(address) or str(address).strip() == "" or not ref_map:
        return str(address).strip() if not pd.isna(address) else ""
    
    text = str(address).strip()
    for short, long in ref_map.items():
        pattern = re.escape(short.rstrip("."))
        if short.endswith("."):
            text = re.sub(rf"\b{pattern}\.?(?!\w)", long, text)
        else:
            text = re.sub(rf"\b{pattern}\b", long, text)
    return text


def process_csv(input_path, output_path, ref_map):
    """Read CSV, clean 4 features, add as new columns, save"""
    print(f"\nProcessing: {input_path}")
    
    df = pd.read_csv(input_path, dtype=str)
    print(f"Loaded {len(df)} rows")
    
    # Find the actual column names (some might have Name, Email, Phone, Address)
    name_col = [col for col in df.columns if col.lower() == "name"][0] if any(col.lower() == "name" for col in df.columns) else None
    email_col = [col for col in df.columns if col.lower() == "email"][0] if any(col.lower() == "email" for col in df.columns) else None
    phone_col = [col for col in df.columns if col.lower() == "phone"][0] if any(col.lower() == "phone" for col in df.columns) else None
    address_col = [col for col in df.columns if col.lower() == "address"][0] if any(col.lower() == "address" for col in df.columns) else None
    
    # Clean each feature and add as new column
    if name_col:
        df["standardized_name"] = df[name_col].apply(clean_name)
        print(f"✓ Cleaned 'name' column")
    
    if phone_col:
        df["standardized_phone"] = df[phone_col].apply(clean_phone)
        print(f"✓ Cleaned 'phone' column")
    
    if email_col:
        df["standardized_email"] = df[email_col].apply(clean_email)
        print(f"✓ Cleaned 'email' column")
    
    if address_col:
        df["standardized_address"] = df[address_col].apply(lambda x: standardize_address(x, ref_map))
        print(f"✓ Cleaned and standardized 'address' column")
    
    # Save to output
    df.to_csv(output_path, index=False)
    print(f"✓ Saved to: {output_path}\n")
    
    return len(df)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Input CSV file")
    parser.add_argument("--output", required=True, help="Output CSV file")
    parser.add_argument("--ref-data", default="reference_data.csv", help="Reference data CSV for address standardization")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    ref_path = Path(args.ref_data)
    
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return
    
    ref_map = load_reference_data(ref_path)
    process_csv(input_path, output_path, ref_map)


if __name__ == "__main__":
    main()
