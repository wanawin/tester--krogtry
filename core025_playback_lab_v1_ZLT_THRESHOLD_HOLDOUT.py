import streamlit as st
import pandas as pd
import numpy as np
from collections import Counter

BUILD = "prepare_120_core_lagged_seed_ledger_v2_ZERO_PAD_CORE"

st.set_page_config(page_title="Prepare 120-Core Lagged Seed Ledger", layout="wide")
st.title("Prepare 120-Core Lagged Seed Trait Ledger — ZERO-PAD CORE FIX")

st.markdown("""
Upload your merged Pick 4 history CSV. This tool creates the ledger required for the stream/core assignment audit.

**v2 fix:** winner_core is always stored as a 3-character text value, preserving leading zero cores like 024, 025, 089.

Correct logic:
- **seed** = previous Result4 within the same stream
- **seed trait columns** = derived from that previous result
- **winner_result** = current Result4
- **winner_core / winner_member** = derived from the current winner only if it is a valid double: exactly 3 unique digits and one digit repeats twice
- non-core/non-double winners keep their seed traits, but get blank winner labels and `is_core_win = 0`
""")

uploaded_file = st.file_uploader("Upload merged_clean_history_....csv", type="csv")


def normalize_digit4(value) -> str:
    """Return exactly four digits when possible; otherwise blank."""
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits == "":
        return ""
    return digits.zfill(4)[-4:]


def is_valid_double_member(result4: str) -> bool:
    """Valid target member: exactly 3 unique digits and one repeats twice."""
    if not isinstance(result4, str) or len(result4) != 4 or not result4.isdigit():
        return False
    counts = Counter(result4)
    return len(counts) == 3 and sorted(counts.values()) == [1, 1, 2]


def winner_core_from_result(result4: str) -> str:
    """Core is sorted unique digits for valid AABC/ABBC/ABCC double winners."""
    if not is_valid_double_member(result4):
        return ""
    return "".join(sorted(set(result4))).zfill(3)


def seed_sum(seed: str):
    return sum(int(d) for d in seed) if isinstance(seed, str) and len(seed) == 4 and seed.isdigit() else np.nan


def parity_pattern(seed: str) -> str:
    return "".join("O" if int(d) % 2 else "E" for d in seed) if isinstance(seed, str) and len(seed) == 4 and seed.isdigit() else ""


def highlow_pattern(seed: str) -> str:
    return "".join("H" if int(d) >= 5 else "L" for d in seed) if isinstance(seed, str) and len(seed) == 4 and seed.isdigit() else ""


def sum_bucket(total):
    if pd.isna(total):
        return ""
    total = int(total)
    if total <= 9:
        return "low"
    if total <= 13:
        return "mid_low"
    if total <= 18:
        return "mid_high"
    return "high"


def structure(seed: str) -> str:
    if not isinstance(seed, str) or len(seed) != 4 or not seed.isdigit():
        return ""
    counts = sorted(Counter(seed).values(), reverse=True)
    if counts == [4]:
        return "AAAA"
    if counts == [3, 1]:
        return "AAAB"
    if counts == [2, 2]:
        return "AABB"
    if counts == [2, 1, 1]:
        return "AABC"
    if counts == [1, 1, 1, 1]:
        return "ABCD"
    return "OTHER"


def mirror_signature(seed: str) -> str:
    if not isinstance(seed, str) or len(seed) != 4 or not seed.isdigit():
        return ""
    # Preserve the earlier app's expected trait style.
    return "mirror_" + seed[0] + seed[3]


def prepare_lagged_ledger(df: pd.DataFrame, drop_rows_without_seed: bool = True) -> pd.DataFrame:
    required_any = {"date": ["Date", "date", "DateParsed"], "stream": ["StreamKey", "stream", "Stream", "game"], "result": ["Result4", "Result", "result", "winner_result"]}
    resolved = {}
    for key, options in required_any.items():
        for col in options:
            if col in df.columns:
                resolved[key] = col
                break
        if key not in resolved:
            raise ValueError(f"Missing required {key} column. Tried: {options}")

    work = df.copy()
    work["date"] = pd.to_datetime(work[resolved["date"]], errors="coerce")
    work["stream"] = work[resolved["stream"]].astype(str)
    work["winner_result"] = work[resolved["result"]].apply(normalize_digit4)

    # Stable tie-breaker preserves original order for same-date rows.
    work["_original_order"] = np.arange(len(work))
    work = work.sort_values(["stream", "date", "_original_order"], kind="mergesort").reset_index(drop=True)

    # Correct lagged seed: prior result in the same stream.
    work["seed"] = work.groupby("stream", sort=False)["winner_result"].shift(1).fillna("")

    # Current winner labels.
    work["winner_core"] = work["winner_result"].apply(winner_core_from_result)
    work["winner_member"] = np.where(work["winner_core"].ne(""), work["winner_result"], "")
    work["is_core_win"] = work["winner_core"].ne("").astype(int)

    # Seed traits from the prior winner/seed, not from the current winner.
    work["seed_sum"] = work["seed"].apply(seed_sum)
    work["seed_first_last_sum"] = work["seed"].apply(lambda x: int(x[0]) + int(x[3]) if isinstance(x, str) and len(x) == 4 and x.isdigit() else np.nan)
    work["seed_sum_mod3"] = work["seed_sum"] % 3
    work["seed_sum_mod5"] = work["seed_sum"] % 5
    work["seed_parity_pattern"] = work["seed"].apply(parity_pattern)
    work["seed_highlow_pattern"] = work["seed"].apply(highlow_pattern)
    work["seed_sum_bucket"] = work["seed_sum"].apply(sum_bucket)
    work["seed_structure"] = work["seed"].apply(structure)
    work["seed_mirror_signature"] = work["seed"].apply(mirror_signature)

    if drop_rows_without_seed:
        work = work[work["seed"].ne("")].copy()

    work["date"] = work["date"].dt.strftime("%Y-%m-%d")

    final_cols = [
        "date", "stream", "seed",
        "winner_result", "winner_core", "winner_member", "is_core_win",
        "seed_sum", "seed_sum_mod3", "seed_sum_mod5",
        "seed_parity_pattern", "seed_highlow_pattern",
        "seed_sum_bucket", "seed_structure", "seed_mirror_signature",
        "seed_first_last_sum"
    ]
    return work[final_cols].reset_index(drop=True)


if uploaded_file is not None:
    df = pd.read_csv(uploaded_file, low_memory=False, dtype=str)
    st.success(f"Loaded {len(df):,} raw history rows")

    drop_rows_without_seed = st.checkbox("Drop first row of each stream where no prior seed exists", value=True)

    with st.spinner("Building lagged seed ledger and labeling AABC/ABBC/ABCC double winners..."):
        try:
            df_out = prepare_lagged_ledger(df, drop_rows_without_seed=drop_rows_without_seed)
            df_out["winner_core"] = df_out["winner_core"].astype(str).replace({"nan": "", "None": ""}).apply(lambda x: x.zfill(3) if x and x.isdigit() else x)
            df_out["winner_member"] = df_out["winner_member"].astype(str).replace({"nan": "", "None": ""}).apply(lambda x: x.zfill(4) if x and x.isdigit() else x)
            df_out["seed"] = df_out["seed"].astype(str).replace({"nan": "", "None": ""}).apply(lambda x: x.zfill(4) if x and x.isdigit() else x)
            df_out["winner_result"] = df_out["winner_result"].astype(str).replace({"nan": "", "None": ""}).apply(lambda x: x.zfill(4) if x and x.isdigit() else x)
        except Exception as e:
            st.error(f"Ledger build failed: {e}")
            st.stop()

    st.success("Lagged 120-core seed ledger prepared successfully.")

    total_rows = len(df_out)
    core_wins = int(df_out["is_core_win"].sum())
    non_core = total_rows - core_wins
    core_rate = (core_wins / total_rows * 100) if total_rows else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ledger rows", f"{total_rows:,}")
    c2.metric("Core/double wins", f"{core_wins:,}")
    c3.metric("Non-core rows", f"{non_core:,}")
    c4.metric("Core win rate", f"{core_rate:.2f}%")

    st.subheader("Preview")
    st.dataframe(df_out.head(25), use_container_width=True)

    st.subheader("Top winner cores")
    top_cores = df_out[df_out["is_core_win"] == 1]["winner_core"].value_counts().head(25).reset_index()
    top_cores.columns = ["winner_core", "wins"]
    st.dataframe(top_cores, use_container_width=True)

    csv = df_out.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download lagged_120_core_seed_trait_ledger_ZERO_PADDED.csv",
        data=csv,
        file_name="lagged_120_core_seed_trait_ledger_ZERO_PADDED.csv",
        mime="text/csv"
    )

    st.info("Use this ledger as the input to stream_core_assignment_audit_v1.py.")
