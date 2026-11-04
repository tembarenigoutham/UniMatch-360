#!/usr/bin/env python
"""
pipeline_simple.py - Simplified pipeline that just runs

Usage:
    python pipeline_simple.py
"""

import os
import sys
import subprocess
import logging
from pathlib import Path
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print("""
╔════════════════════════════════════════════════════════════╗
║     CUSTOMER 360 MDM SOLUTION - END-TO-END PIPELINE        ║
║              BNP Paribas UniBank | Team 29                 ║
╚════════════════════════════════════════════════════════════╝
""")

start_time = time.time()
src_dir = Path(__file__).parent  # Current directory (src/)

try:
    # Step 2: Run matching
    print("\n" + "="*60)
    print("STEP 1: FIND MATCHES")
    print("="*60)
    logger.info("Running matching...")
    result = subprocess.run([sys.executable, str(src_dir / "matching_fixed.py")], timeout=300)
    if result.returncode != 0:
        raise RuntimeError("Matching failed")
    logger.info("✅ Matching complete")
    
    # Step 3: Create golden records
    print("\n" + "="*60)
    print("STEP 2: CREATE GOLDEN RECORDS")
    print("="*60)
    logger.info("Running survivorship engine...")
    result = subprocess.run([sys.executable, str(src_dir / "survivorship_engine.py")], timeout=300)
    if result.returncode != 0:
        raise RuntimeError("Survivorship failed")
    logger.info("✅ Golden records created")
    
    # Step 4: Link transactions
    print("\n" + "="*60)
    print("STEP 3: LINK TRANSACTIONS")
    print("="*60)
    logger.info("Running transaction linker...")
    result = subprocess.run([sys.executable, str(src_dir / "transaction_linker.py")], timeout=300)
    if result.returncode != 0:
        raise RuntimeError("Transaction linking failed")
    logger.info("✅ Transactions linked")
    
    elapsed = time.time() - start_time
    print(f"\n✅ Pipeline completed successfully in {elapsed:.1f} seconds")
    
except Exception as e:
    logger.error(f"❌ Pipeline failed: {e}")
    sys.exit(1)
