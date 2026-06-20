import streamlit as st
import pandas as pd
import numpy as np

st.title("Prepare Row-Level Seed Trait Ledger")

uploaded_file = st.file_uploader("Upload aabc_seed_group_ledger.csv", type="csv")

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file, low_memory=False)
    st.success(f"Loaded {len(df):,} rows")

    # === Standardize columns ===
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

    df["winner_core"] = df["winner_core"].astype(str).str.zfill(3)

    # Optional: add missing useful traits
    if "seed_sum" in df.columns and "seed_sum_bucket" not in df.columns:
        df["seed_sum_bucket"] = pd.cut(
            df["seed_sum"], bins=[0, 9, 13, 18, 27], 
            labels=["low", "mid_low", "mid_high", "high"]
        ).astype(str)

    # Reorder columns
    front = ["date", "stream", "seed", "winner_core", "winner_member"]
    rest = [c for c in df.columns if c not in front]
    df = df[front + rest]

    st.write("Preview of standardized ledger:")
    st.dataframe(df.head(10))

    # Download button
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Standardized Ledger (row_level_seed_trait_ledger.csv)",
        data=csv,
        file_name="row_level_seed_trait_ledger.csv",
        mime="text/csv"
    )

    # Missing traits check
    important = ["seed_parity_pattern", "seed_highlow_pattern", "seed_sum_bucket", 
                 "seed_structure", "seed_mirror_signature"]
    missing = [t for t in important if t not in df.columns]
    if missing:
        st.warning(f"Missing important traits: {missing}")
    else:
        st.success("All key seed traits are present.")
