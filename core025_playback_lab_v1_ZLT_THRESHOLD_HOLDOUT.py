#!/usr/bin/env python3
"""
Fast version of the ledger preparer (vectorized).
Run this locally or on Streamlit Cloud.
"""

import pandas as pd
import numpy as np
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", required=True)
    parser.add_argument("--out", default="aabc_seed_group_ledger_REBUILT.csv")
    args = parser.parse_args()

    print("Loading history...")
    df = pd.read_csv(args.history, low_memory=False)
    print(f"Loaded {len(df):,} rows")

    # Standardize
    df["date"] = df.get("Date", df.get("date", ""))
    df["stream"] = df.get("StreamKey", df.get("stream", df.get("game", "")))
    df["seed"] = df["Result4"].astype(str).str.zfill(4)
    df["winner_result"] = df["Result4"].astype(str).str.zfill(4)

    # For now, winner_core and winner_member are left blank
    # (they usually come from a separate mapping you already have)
    df["winner_core"] = ""
    df["winner_member"] = ""

    s = df["seed"]

    # Vectorized trait derivation
    df["seed_sum"] = s.apply(lambda x: sum(int(d) for d in x))
    df["seed_first_last_sum"] = s.str[0].astype(int) + s.str[3].astype(int)
    df["seed_sum_mod3"] = df["seed_sum"] % 3
    df["seed_sum_mod5"] = df["seed_sum"] % 5

    df["seed_parity_pattern"] = s.apply(lambda x: "".join("O" if int(d) % 2 else "E" for d in x))
    df["seed_highlow_pattern"] = s.apply(lambda x: "".join("H" if int(d) >= 5 else "L" for d in x))

    df["seed_sum_bucket"] = pd.cut(
        df["seed_sum"], bins=[0, 9, 13, 18, 28],
        labels=["low", "mid_low", "mid_high", "high"]
    ).astype(str)

    def get_structure(s):
        unique = len(set(s))
        if unique == 1: return "AAAA"
        if unique == 2: return "AABB" if s[0]==s[1] and s[2]==s[3] else "ABAB"
        if unique == 3: return "AABC"
        return "ABCD"
    df["seed_structure"] = s.apply(get_structure)

    df["seed_mirror_signature"] = "mirror_" + s.str[0] + s.str[3]

    # Final columns
    final_cols = [
        "date", "stream", "seed",
        "winner_result", "winner_core", "winner_member",
        "seed_sum", "seed_sum_mod3", "seed_sum_mod5",
        "seed_parity_pattern", "seed_highlow_pattern",
        "seed_sum_bucket", "seed_structure", "seed_mirror_signature",
        "seed_first_last_sum"
    ]

    df_out = df[[c for c in final_cols if c in df.columns]].copy()
    df_out.to_csv(args.out, index=False)

    print(f"\nSaved: {args.out}")
    print(f"Rows: {len(df_out):,}")

if __name__ == "__main__":
    main()
