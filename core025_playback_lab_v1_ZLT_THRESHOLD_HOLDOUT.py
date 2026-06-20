import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Prepare 120-Core Ledger", layout="wide")
st.title("Prepare aabc_seed_group_ledger_REBUILT.csv")

st.markdown("""
Upload your merged history file.  
This tool will create a clean, standardized ledger with all the seed traits needed for the assignment audit and future mining.
""")

uploaded_file = st.file_uploader("Upload merged_clean_history_....csv", type="csv")

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file, low_memory=False)
    st.success(f"Loaded {len(df):,} rows")

    with st.spinner("Processing and deriving traits..."):
        # Standardize columns
        df["date"] = df.get("Date", df.get("date", df.get("DateParsed", "")))
        df["stream"] = df.get("StreamKey", df.get("stream", df.get("game", "")))
        df["seed"] = df["Result4"].astype(str).str.zfill(4)
        df["winner_result"] = df["Result4"].astype(str).str.zfill(4)

        # These two usually come from your existing mapping.
        # Leaving blank for now — you can fill them later if needed.
        df["winner_core"] = ""
        df["winner_member"] = ""

        s = df["seed"]

        # Derive traits (vectorized where possible)
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
            if unique == 2: return "AABB" if s[0] == s[1] and s[2] == s[3] else "ABAB"
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

    st.success("Ledger prepared successfully!")

    # Preview
    st.subheader("Preview (first 10 rows)")
    st.dataframe(df_out.head(10))

    # Download button
    csv = df_out.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download aabc_seed_group_ledger_REBUILT.csv",
        data=csv,
        file_name="aabc_seed_group_ledger_REBUILT.csv",
        mime="text/csv"
    )

    st.info("You can now use this file with the stream_core_assignment_audit_v1.py script.")
