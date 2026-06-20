#!/usr/bin/env python3
"""
Prepare Row-Level Seed Trait Ledger
Makes your existing aabc_seed_group_ledger.csv clean and audit-ready.
"""

import pandas as pd
import numpy as np
from pathlib import Path

def prepare_ledger(input_path: str, output_path: str = "row_level_seed_trait_ledger.csv"):
    print(f"Loading {input_path}...")
    df = pd.read_csv(input_path, low_memory=False)
    print(f"Original rows: {len(df):,}")

    # Standardize key columns
    col_map = {
        "winner_core": ["winner_core", "core", "winning_core"],
        "winner_member": ["winner_member", "member"],
        "date": ["Date", "date", "play_date", "draw_date", "DateParsed"],
        "stream": ["StreamKey", "stream", "stream_name", "game"],
        "seed": ["SeedResult", "seed", "result", "winning_number"],
    }

    for standard, candidates in col_map.items():
        found = None
        for c in candidates:
            if c in df.columns:
                found = c
                break
        if found:
            df[standard] = df[found]
        else:
            df[standard] = np.nan

    # Ensure winner_core is 3-digit string
    df["winner_core"] = df["winner_core"].astype(str).str.zfill(3)

    # Add a few useful derived traits if missing (example)
    if "seed_sum" in df.columns and "seed_sum_bucket" not in df.columns:
        df["seed_sum_bucket"] = pd.cut(
            df["seed_sum"], bins=[0, 9, 13, 18, 27], labels=["low", "mid_low", "mid_high", "high"]
        ).astype(str)

    # Final column order (put key columns first)
    front_cols = ["date", "stream", "seed", "winner_core", "winner_member"]
    other_cols = [c for c in df.columns if c not in front_cols]
    df = df[front_cols + other_cols]

    df.to_csv(output_path, index=False)
    print(f"Saved standardized ledger → {output_path}")
    print(f"Final rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")

    # Quick report on potentially missing important traits
    important_traits = [
        "seed_parity_pattern", "seed_highlow_pattern", "seed_sum_bucket",
        "seed_structure", "seed_mirror_signature", "seed_pair_signature"
    ]
    missing = [t for t in important_traits if t not in df.columns]
    if missing:
        print(f"\nWARNING: These important traits are missing: {missing}")
    else:
        print("\nAll key seed traits appear to be present.")

if __name__ == "__main__":
    # Change this path if your file is elsewhere
    prepare_ledger("aabc_seed_group_ledger.csv")