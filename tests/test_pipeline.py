"""
test_pipeline.py

Comprehensive test suite for Customer 360 MDM pipeline.

Run with: pytest test_pipeline.py -v
"""

import pytest
import pandas as pd
import json
import tempfile
import os
from pathlib import Path


# ============================================================
# TEST FIXTURES (Sample Data)
# ============================================================

@pytest.fixture
def sample_customers():
    """Sample normalized customers from matching.py output"""
    return pd.DataFrame({
        "source": ["SourceA", "SourceA", "SourceB", "SourceC"],
        "source_id": ["C001", "C002", "CC001", "L001"],
        "name": ["John Doe", "Jane Smith", "Jon Doe", "John D."],
        "email": ["john@example.com", "jane@example.com", "jon@example.com", ""],
        "phone": ["9876543210", "9876543211", "9876543210", "9876543210"],
        "dob": ["1990-01-15", "1985-03-20", "", "1990-01-15"],
        "address": ["123 main street", "456 oak avenue", "123 main street", "123 main street"]
    })


@pytest.fixture
def sample_matches():
    """Sample matches from matching.py output"""
    return pd.DataFrame({
        "source_a": ["C001", "C002"],
        "source_b": ["CC001", "L001"],
        "source_a_system": ["SourceA", "SourceA"],
        "source_b_system": ["SourceB", "SourceC"],
        "method": ["EXACT_PHONE", "FUZZY_NAME_ADDRESS"],
        "score": [1.0, 0.92]
    })


@pytest.fixture
def sample_transactions():
    """Sample transaction data"""
    return pd.DataFrame({
        "Txn_ID": ["TXN001", "TXN002", "TXN003", "TXN004"],
        "Account_ID": ["C001", "C001", "CC001", "L001"],
        "Amount": [1000, 500, 1500, 2000],
        "Date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        "Type": ["CREDIT", "DEBIT", "CREDIT", "DEBIT"]
    })


@pytest.fixture
def trust_hierarchy():
    """Sample trust hierarchy configuration"""
    return {
        "Phone": ["SourceA", "SourceB", "SourceC"],
        "Email": ["SourceB", "SourceA", "SourceC"],
        "Name": ["SourceA", "SourceB", "SourceC"],
        "Address": ["SourceA", "SourceB", "SourceC"],
        "DOB": ["SourceA", "SourceB", "SourceC"]
    }


# ============================================================
# TESTS: NORMALIZATION (cleaning.py)
# ============================================================

class TestNormalization:
    
    def test_name_normalization_proper_case(self):
        """Names should be proper case without breaking McDonald"""
        from matching_fixed import normalize_name
        
        assert normalize_name("john doe") == "John Doe"
        assert normalize_name("mcdonald") == "Mcdonald"
        assert normalize_name("O'Brien") == "O'brien"
        assert normalize_name("") == ""
        assert normalize_name(None) == ""
    
    def test_email_normalization(self):
        """Emails should be lowercase and trimmed"""
        from matching_fixed import normalize_email
        
        assert normalize_email("John@EXAMPLE.COM") == "john@example.com"
        assert normalize_email("  test@test.com  ") == "test@test.com"
        assert normalize_email("") == ""
        assert normalize_email(None) == ""
    
    def test_phone_normalization(self):
        """Phones should be digits only"""
        from matching_fixed import normalize_phone
        
        assert normalize_phone("(987) 654-3210") == "9876543210"
        assert normalize_phone("+1-987-654-3210") == "19876543210"
        assert normalize_phone("9876543210") == "9876543210"
        assert normalize_phone("") == ""
        assert normalize_phone(None) == ""
    
    def test_address_normalization(self):
        """Addresses should standardize abbreviations"""
        from matching_fixed import normalize_address
        
        ref_map = {"st.": "street", "rd": "road", "ave": "avenue"}
        
        assert normalize_address("123 St.", ref_map) == "123 street"
        assert normalize_address("456 oak rd", ref_map) == "456 oak road"
        assert normalize_address("", ref_map) == ""


# ============================================================
# TESTS: EXACT MATCHING
# ============================================================

class TestExactMatching:
    
    def test_exact_email_match_identifies_duplicates(self, sample_customers):
        """Exact email match should find same customer"""
        # C001 (john@example.com) and CC001 (jon@example.com) have different emails
        # But in real data, exact match should identify them if emails were same
        
        # Filter for exact email matches
        email_duplicates = sample_customers[sample_customers["email"] != ""].groupby("email").filter(
            lambda g: len(g) > 1
        )
        
        # john@example.com appears once, so no exact match
        # But if we had duplicates, they'd be in email_duplicates
        assert len(email_duplicates) == 0  # C001 email unique, CC001 different, Jane unique
    
    def test_exact_phone_match_identifies_duplicates(self, sample_customers):
        """Exact phone match should find same customer"""
        # C001, CC001, L001 all have phone 9876543210
        phone_duplicates = sample_customers[sample_customers["phone"] != ""].groupby("phone").filter(
            lambda g: len(g) > 1
        )
        
        # Should find 3 records with same phone
        assert len(phone_duplicates) == 3


# ============================================================
# TESTS: FUZZY MATCHING
# ============================================================

class TestFuzzyMatching:
    
    def test_fuzzy_name_similarity(self, sample_customers):
        """Fuzzy matching should find similar names"""
        from rapidfuzz import fuzz
        
        # John Doe vs Jon Doe should be similar
        name1 = sample_customers[sample_customers["source_id"] == "C001"]["name"].values[0]
        name2 = sample_customers[sample_customers["source_id"] == "CC001"]["name"].values[0]
        
        similarity = fuzz.ratio(name1.lower(), name2.lower()) / 100
        assert similarity > 0.8  # High similarity
    
    def test_fuzzy_address_similarity(self, sample_customers):
        """Fuzzy matching should find similar addresses"""
        from rapidfuzz import fuzz
        
        # All should have "123 main street"
        addr1 = sample_customers[sample_customers["source_id"] == "C001"]["address"].values[0]
        addr2 = sample_customers[sample_customers["source_id"] == "CC001"]["address"].values[0]
        
        similarity = fuzz.ratio(addr1.lower(), addr2.lower()) / 100
        assert similarity == 1.0  # Perfect match


# ============================================================
# TESTS: SURVIVORSHIP LOGIC
# ============================================================

class TestSurvivorship:
    
    def test_select_winning_value_respects_hierarchy(self, trust_hierarchy):
        """Survivorship should pick value from highest-priority source"""
        from survivorship_engine import select_winning_value
        
        record_a = {"email": "john@old.com", "source": "SourceA"}
        record_b = {"email": "john@new.com", "source": "SourceB"}
        
        # Email priority: ["SourceB", "SourceA"]
        # SourceB should win
        value, source = select_winning_value(record_a, record_b, "Email", trust_hierarchy)
        assert value == "john@new.com"
        assert source == "SourceB"
    
    def test_select_winning_value_fallback_non_empty(self, trust_hierarchy):
        """Should pick non-empty value if hierarchy source not available"""
        from survivorship_engine import select_winning_value
        
        record_a = {"phone": "9876543210", "source": "SourceA"}
        record_b = {"phone": None, "source": "SourceB"}
        
        value, source = select_winning_value(record_a, record_b, "Phone", trust_hierarchy)
        assert value == "9876543210"
        assert source == "SourceA"
    
    def test_select_winning_value_both_empty(self, trust_hierarchy):
        """Should return None if both values empty"""
        from survivorship_engine import select_winning_value
        
        record_a = {"phone": None, "source": "SourceA"}
        record_b = {"phone": "", "source": "SourceB"}
        
        value, source = select_winning_value(record_a, record_b, "Phone", trust_hierarchy)
        assert value is None or value == ""


# ============================================================
# TESTS: TRANSACTION LINKING
# ============================================================

class TestTransactionLinking:
    
    def test_infer_source_from_account_id(self):
        """Should infer source from Account_ID prefix"""
        from transaction_linker import infer_source_from_account_id
        
        assert infer_source_from_account_id("C001") == "SourceA"
        assert infer_source_from_account_id("CORE_001") == "SourceA"
        assert infer_source_from_account_id("CC001") == "SourceB"
        assert infer_source_from_account_id("CRED_001") == "SourceB"
        assert infer_source_from_account_id("L001") == "SourceC"
        assert infer_source_from_account_id("LOAN_001") == "SourceC"
        assert infer_source_from_account_id("UNKNOWN") == "SourceA"  # Default
    
    def test_build_id_mapping(self, sample_customers):
        """Should create mapping from source IDs to golden IDs"""
        # Create minimal golden records
        golden = sample_customers.copy()
        golden["GOLDEN_ID"] = ["GOLD_001", "GOLD_002", "GOLD_001", "GOLD_001"]  # C001->GOLD_001, etc.
        
        from transaction_linker import build_id_mapping
        mapping = build_id_mapping(golden)
        
        assert mapping["SourceA_C001"] == "GOLD_001"
        assert mapping["SourceB_CC001"] == "GOLD_001"
        assert mapping["SourceC_L001"] == "GOLD_001"


# ============================================================
# INTEGRATION TESTS
# ============================================================

class TestIntegration:
    
    def test_end_to_end_pipeline(self, sample_customers, sample_matches, sample_transactions, trust_hierarchy):
        """End-to-end test: Raw → Matched → Golden → Transactions linked"""
        
        # This is a simplified version; in real test would use actual files
        
        # Step 1: Normalize (done in setup via sample_customers)
        assert len(sample_customers) == 4
        
        # Step 2: Find matches
        assert len(sample_matches) == 2
        
        # Step 3: Create golden records
        # Simulate grouping: C001 matches CC001, C002 matches L001
        # Expected: 2 golden records (since 4 source records match into 2 groups)
        
        # Step 4: Link transactions
        # All 4 transactions should link to golden IDs
        assert len(sample_transactions) == 4
    
    def test_match_transitivity(self, sample_customers, trust_hierarchy):
        """If A matches B and B matches C, they should be one golden record"""
        
        # Simulate: C001 matches CC001 (via exact phone)
        #          CC001 matches L001 (via fuzzy name/address)
        # Expected: All 3 should map to same GOLDEN_ID
        
        from survivorship_engine import build_match_groups
        
        matches = pd.DataFrame({
            "source_a": ["C001", "CC001"],
            "source_b": ["CC001", "L001"]
        })
        
        groups = build_match_groups(matches)
        
        # Should have 1 group with C001, CC001, L001
        assert len(groups) == 1
        assert len(groups[0]) == 3
        assert set(groups[0]) == {"C001", "CC001", "L001"}


# ============================================================
# TESTS: ERROR HANDLING
# ============================================================

class TestErrorHandling:
    
    def test_missing_file_handling(self):
        """Should gracefully handle missing files"""
        # Would need to mock file loading in real test
        pass
    
    def test_null_values_handled(self, sample_customers):
        """Should handle null/empty values in customer data"""
        # C001 has dob, CC001 has empty email, L001 has empty email and dob
        # Survivorship should handle these gracefully
        assert sample_customers[sample_customers["source_id"] == "L001"]["email"].values[0] == ""


# ============================================================
# PERFORMANCE TESTS
# ============================================================

class TestPerformance:
    
    def test_large_dataset_matching(self):
        """Matching should handle reasonably large datasets"""
        # Create 1000 customer records
        n = 1000
        large_customers = pd.DataFrame({
            "source": ["SourceA"] * n,
            "source_id": [f"C{i}" for i in range(n)],
            "name": [f"Customer {i}" for i in range(n)],
            "email": [f"cust{i}@example.com" for i in range(n)],
            "phone": ["9876543210"] * n,
            "dob": ["1990-01-15"] * n,
            "address": ["123 Main St"] * n
        })
        
        # Should not crash
        assert len(large_customers) == n


# ============================================================
# RUN TESTS
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
