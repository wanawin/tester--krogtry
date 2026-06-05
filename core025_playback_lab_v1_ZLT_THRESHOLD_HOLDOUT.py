"""
Core025 Playback Lab v1 — ZLT Threshold / Holdout Helper

Purpose
-------
A separate, disposable Streamlit lab for validating ZLT cut thresholds without
changing the production Core025 playlist app.

What this lab does safely:
1) Reads a full cleaned lottery history file.
2) Finds Core025 hits in a forward holdout window.
3) Creates one as-of history file per hit date, ending the day BEFORE the hit.
4) Lets you upload the v162 final-playlist exports you generate manually from
   those as-of files.
5) Audits whether the winner was preserved, cut, or had the right member played.
6) Tests ZLT threshold ideas like:
      cut if ZLT == 0
      cut if ZLT <= 1
      cut if ZLT <= 2
      cut if ZLT >= 5

Important
---------
This lab does NOT re-mine rules and does NOT change v162 ranking logic.
It is designed to preserve a true "as-if-played-that-day" test:
for each hit, v162 only sees history through the day before the hit.

Run
---
streamlit run core025_playback_lab_v1_ZLT_THRESHOLD_HOLDOUT.py
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import streamlit as st

APP_TITLE = "Core025 Playback Lab v1 — ZLT Threshold Holdout"
CORE025_SORTED_TO_MEMBER = {
    "0025": "0025",
    "0225": "0225",
    "0255": "0255",
}

DATE_FORMATS = [
    "%a, %b %d, %Y",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
]

COMMON_DATE_COLUMNS = ["Draw Date", "Date", "date", "draw_date"]
COMMON_STATE_COLUMNS = ["State", "state"]
COMMON_GAME_COLUMNS = ["Game", "game"]
COMMON_RESULT_COLUMNS = ["Results", "Result", "result", "results", "LastResult"]
COMMON_STREAM_COLUMNS = ["StreamKey", "RecommendedStream", "stream", "Stream"]


def _first_present(cols: Iterable[str], options: list[str]) -> Optional[str]:
    cols_set = set(cols)
    for opt in options:
        if opt in cols_set:
            return opt
    return None


def parse_date_value(x) -> pd.Timestamp:
    if pd.isna(x):
        return pd.NaT
    s = str(x).strip()
    if not s:
        return pd.NaT
    for fmt in DATE_FORMATS:
        try:
            return pd.Timestamp(datetime.strptime(s, fmt).date())
        except Exception:
            pass
    try:
        return pd.to_datetime(s, errors="coerce").normalize()
    except Exception:
        return pd.NaT


def normalize_result_to_4digits(raw) -> str:
    """Extract first four draw digits, ignoring Fireball/Wild Ball text."""
    if pd.isna(raw):
        return ""
    s = str(raw)
    # Only use the part before extra-ball labels.
    s = re.split(r",|Wild Ball|Fireball|Superball|Sum It Up", s, flags=re.I)[0]
    digits = re.findall(r"\d", s)
    if len(digits) < 4:
        return ""
    return "".join(digits[:4])


def core025_member(raw_result) -> str:
    four = normalize_result_to_4digits(raw_result)
    if len(four) != 4:
        return ""
    key = "".join(sorted(four))
    return CORE025_SORTED_TO_MEMBER.get(key, "")


def clean_stream_key(state, game) -> str:
    return f"{str(state).strip()} | {str(game).strip()}"


def read_table(uploaded_file) -> pd.DataFrame:
    """Read CSV/TXT/TSV with delimiter sniffing. Expected columns include date/state/game/results."""
    raw = uploaded_file.read()
    name = getattr(uploaded_file, "name", "uploaded_file")
    text = raw.decode("utf-8", errors="replace")
    sample = text[:5000]
    sep = "\t" if "\t" in sample else ","
    # If comma count is very low and tabs absent, try whitespace fallback later.
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)
    except Exception:
        df = pd.read_csv(io.StringIO(text), sep=None, engine="python", dtype=str, keep_default_na=False)

    # If it loaded as one column, retry tab and comma alternatives.
    if df.shape[1] == 1:
        for sep_try in ["\t", ","]:
            try:
                df2 = pd.read_csv(io.StringIO(text), sep=sep_try, dtype=str, keep_default_na=False)
                if df2.shape[1] > 1:
                    df = df2
                    break
            except Exception:
                pass
    df.attrs["source_name"] = name
    return df


def standardize_history(df: pd.DataFrame) -> pd.DataFrame:
    date_col = _first_present(df.columns, COMMON_DATE_COLUMNS)
    state_col = _first_present(df.columns, COMMON_STATE_COLUMNS)
    game_col = _first_present(df.columns, COMMON_GAME_COLUMNS)
    result_col = _first_present(df.columns, COMMON_RESULT_COLUMNS)

    missing = [
        label for label, col in [
            ("date", date_col),
            ("state", state_col),
            ("game", game_col),
            ("result", result_col),
        ] if col is None
    ]
    if missing:
        raise ValueError(f"Missing required history columns: {', '.join(missing)}. Found: {list(df.columns)}")

    out = pd.DataFrame()
    out["Date"] = df[date_col].map(parse_date_value)
    out["State"] = df[state_col].astype(str).str.strip()
    out["Game"] = df[game_col].astype(str).str.strip()
    out["Results"] = df[result_col].astype(str).str.strip()
    out["Result4"] = out["Results"].map(normalize_result_to_4digits)
    out["StreamKey"] = [clean_stream_key(s, g) for s, g in zip(out["State"], out["Game"])]
    out["Core025Member"] = out["Results"].map(core025_member)
    out = out.dropna(subset=["Date"])
    out = out[out["Result4"].str.len() == 4].copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.normalize()
    # Dedupe exact same draw row.
    out = out.drop_duplicates(subset=["Date", "State", "Game", "Result4"], keep="first")
    out = out.sort_values(["Date", "State", "Game", "Result4"], ascending=[True, True, True, True]).reset_index(drop=True)
    return out


def app_format_txt(df: pd.DataFrame) -> str:
    # Keep app-friendly columns only, tab-delimited.
    cols = ["Date", "State", "Game", "Results"]
    tmp = df[cols].copy()
    tmp["Date"] = pd.to_datetime(tmp["Date"]).dt.strftime("%a, %b %-d, %Y")
    # Windows-compatible fallback for platforms that dislike %-d.
    try:
        _ = tmp["Date"].iloc[0] if len(tmp) else ""
    except Exception:
        tmp["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%a, %b %d, %Y").str.replace(" 0", " ", regex=False)
    out = io.StringIO()
    tmp.to_csv(out, sep="\t", index=False, lineterminator="\n")
    return out.getvalue()


def find_forward_core025_hits(hist: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    hits = hist[(hist["Date"] >= start_date) & (hist["Date"] <= end_date) & (hist["Core025Member"] != "")].copy()
    hits = hits.sort_values(["Date", "State", "Game"]).reset_index(drop=True)
    hits["HitID"] = [f"H{i+1:03d}" for i in range(len(hits))]
    hits["AsOfDate"] = hits["Date"] - pd.Timedelta(days=1)
    return hits


def make_asof_zip(hist: pd.DataFrame, hits: pd.DataFrame) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest_rows = []
        for _, hit in hits.iterrows():
            asof = hit["AsOfDate"]
            hit_date = hit["Date"]
            safe_stream = re.sub(r"[^A-Za-z0-9]+", "_", hit["StreamKey"]).strip("_")[:60]
            fname = f"{hit['HitID']}_asof_{asof.date()}__hit_{hit_date.date()}__{safe_stream}.txt"
            cut = hist[hist["Date"] <= asof].copy()
            zf.writestr(fname, app_format_txt(cut))
            manifest_rows.append({
                "HitID": hit["HitID"],
                "HitDate": hit_date.date().isoformat(),
                "AsOfDate": asof.date().isoformat(),
                "WinningStreamKey": hit["StreamKey"],
                "WinningResult": hit["Result4"],
                "WinningMember": hit["Core025Member"],
                "AsOfHistoryFile": fname,
                "RowsInAsOfHistory": len(cut),
            })
        manifest = pd.DataFrame(manifest_rows)
        zf.writestr("PLAYBACK_MANIFEST.csv", manifest.to_csv(index=False))
        zf.writestr("README.txt", "Upload each as-of TXT into frozen v162, export final playlist, then upload those exports back into this lab.\n")
    return bio.getvalue()


def standardize_playlist_export(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # Make sure important fields exist.
    for col in [
        "StreamKey", "FINAL_ACTION_v162", "FINAL_MEMBERS_TO_PLAY_v162", "FINAL_PLAY_COUNT_v162",
        "v161_RuleFiredCount", "v161_FiredRuleIDs", "PlayOrder", "PredictedMember", "Top2_pred", "ThirdMember",
        "v162_PriorCore025WinnerDate", "v162_PriorCore025WinnerResult", "v162_PriorWinnerResolverStatus"
    ]:
        if col not in out.columns:
            out[col] = ""

    # Fallback stream column.
    if out["StreamKey"].astype(str).str.strip().eq("").all():
        stream_col = _first_present(out.columns, COMMON_STREAM_COLUMNS)
        if stream_col:
            out["StreamKey"] = out[stream_col]
    return out


def read_playlist_files(files) -> dict[str, pd.DataFrame]:
    result = {}
    for f in files:
        try:
            df = read_table(f)
            result[getattr(f, "name", f"playlist_{len(result)+1}")] = standardize_playlist_export(df)
        except Exception as e:
            st.warning(f"Could not read {getattr(f, 'name', 'file')}: {e}")
    return result


def match_export_to_hit(name: str, df: pd.DataFrame, hits: pd.DataFrame) -> Optional[pd.Series]:
    """Try filename date first; then target date column; otherwise no match."""
    text = name
    m = re.search(r"hit_(\d{4}-\d{2}-\d{2})", text)
    if m:
        d = pd.Timestamp(m.group(1))
        hit = hits[hits["Date"] == d]
        if len(hit):
            return hit.iloc[0]
    m = re.search(r"asof_(\d{4}-\d{2}-\d{2})", text)
    if m:
        asof = pd.Timestamp(m.group(1))
        hit = hits[hits["AsOfDate"] == asof]
        if len(hit):
            return hit.iloc[0]
    # If v162 target date exists in export, match target+1 to hit or target itself if app uses hit date.
    for col in ["PriorWinnerTargetDate_v162", "v162_PriorWinnerTargetDate", "Date"]:
        if col in df.columns:
            vals = pd.to_datetime(df[col], errors="coerce").dropna().dt.normalize().unique()
            for val in vals[:5]:
                t = pd.Timestamp(val)
                for d in [t, t + pd.Timedelta(days=1)]:
                    hit = hits[hits["Date"] == d]
                    if len(hit):
                        return hit.iloc[0]
    return None


def audit_uploaded_playlists(playlists: dict[str, pd.DataFrame], hits: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, df in playlists.items():
        hit = match_export_to_hit(name, df, hits)
        if hit is None:
            rows.append({"PlaylistFile": name, "AuditStatus": "NO_HIT_MATCH"})
            continue
        stream = hit["StreamKey"]
        match = df[df["StreamKey"].astype(str).str.strip() == str(stream).strip()]
        if match.empty:
            rows.append({
                "PlaylistFile": name,
                "HitID": hit["HitID"],
                "HitDate": hit["Date"].date().isoformat(),
                "WinningStreamKey": stream,
                "WinningMember": hit["Core025Member"],
                "AuditStatus": "WINNING_STREAM_NOT_IN_PLAYLIST",
            })
            continue
        r = match.iloc[0]
        action = str(r.get("FINAL_ACTION_v162", r.get("v161_Action", ""))).strip()
        members_raw = str(r.get("FINAL_MEMBERS_TO_PLAY_v162", r.get("v161_AdjustedMembersToPlay", ""))).strip()
        zlt = pd.to_numeric(r.get("v161_RuleFiredCount", 0), errors="coerce")
        zlt = int(zlt) if pd.notna(zlt) else 0
        play_count = pd.to_numeric(r.get("FINAL_PLAY_COUNT_v162", r.get("v161_AdjustedPlayCount", "")), errors="coerce")
        members_norm = re.sub(r"[^0-9]+", " ", members_raw).strip().split()
        # Normalize 25/225/255 to 0025/0225/0255.
        norm_members = []
        for m in members_norm:
            if m == "25": norm_members.append("0025")
            elif m == "225": norm_members.append("0225")
            elif m == "255": norm_members.append("0255")
            elif m in {"0025", "0225", "0255"}: norm_members.append(m)
        correct_played = hit["Core025Member"] in norm_members
        cut = action.upper().startswith("CUT") or (pd.notna(play_count) and int(play_count) == 0)
        rows.append({
            "PlaylistFile": name,
            "HitID": hit["HitID"],
            "HitDate": hit["Date"].date().isoformat(),
            "AsOfDate": hit["AsOfDate"].date().isoformat(),
            "WinningStreamKey": stream,
            "WinningResult": hit["Result4"],
            "WinningMember": hit["Core025Member"],
            "AuditStatus": "OK",
            "FinalAction": action,
            "FinalMembersToPlay": members_raw,
            "FinalPlayCount": int(play_count) if pd.notna(play_count) else None,
            "ZLTCount": zlt,
            "FiredRuleIDs": str(r.get("v161_FiredRuleIDs", "")),
            "WasStreamCut": bool(cut),
            "CorrectMemberPlayed": bool(correct_played),
            "PreservedCapture": bool((not cut) and correct_played),
        })
    return pd.DataFrame(rows)


def threshold_table(audit: pd.DataFrame) -> pd.DataFrame:
    ok = audit[audit.get("AuditStatus", "") == "OK"].copy()
    if ok.empty:
        return pd.DataFrame()
    tests = []
    for direction, label, pred in [
        ("eq0", "Cut if ZLT = 0", lambda s: s == 0),
        ("le1", "Cut if ZLT <= 1", lambda s: s <= 1),
        ("le2", "Cut if ZLT <= 2", lambda s: s <= 2),
        ("le3", "Cut if ZLT <= 3", lambda s: s <= 3),
        ("le4", "Cut if ZLT <= 4", lambda s: s <= 4),
        ("ge5", "Cut if ZLT >= 5", lambda s: s >= 5),
        ("ge6", "Cut if ZLT >= 6", lambda s: s >= 6),
        ("ge7", "Cut if ZLT >= 7", lambda s: s >= 7),
    ]:
        mask = ok["ZLTCount"].map(pred)
        winners_cut_by_test = int(mask.sum())
        # Existing v162 capture still matters. Threshold is additional cut, so it loses if winning row falls in cut mask.
        preserved_after_test = int((~mask & ok["PreservedCapture"]).sum())
        total = len(ok)
        tests.append({
            "TestID": direction,
            "ThresholdRule": label,
            "ForwardHitsTested": total,
            "WinningRowsMeetingCutRule": winners_cut_by_test,
            "WinnersPreservedAfterThreshold": preserved_after_test,
            "CaptureAfterThresholdPct": round(100 * preserved_after_test / total, 2) if total else 0,
            "WinnerZLTValuesCut": ", ".join(map(str, sorted(ok.loc[mask, "ZLTCount"].astype(int).tolist()))),
        })
    return pd.DataFrame(tests)


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption("Separate lab. Does not modify production v162.")

    st.markdown("""
    **Workflow**
    1. Upload cleaned full history through the holdout end date.
    2. Generate as-of history files for each Core025 hit.
    3. Run frozen v162 manually once per as-of file and export the final playlist.
    4. Upload those playlist exports back here to test ZLT thresholds.
    """)

    hist_file = st.file_uploader("Upload cleaned merged history TXT/CSV", type=["txt", "csv", "tsv"])
    if not hist_file:
        st.info("Upload your cleaned merged history file to begin.")
        return

    try:
        raw = read_table(hist_file)
        hist = standardize_history(raw)
    except Exception as e:
        st.error(f"Could not read/standardize history: {e}")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Rows", f"{len(hist):,}")
    with c2:
        st.metric("Date min", hist["Date"].min().date().isoformat())
    with c3:
        st.metric("Date max", hist["Date"].max().date().isoformat())

    st.subheader("1) Forward Core025 hit selection")
    min_d = hist["Date"].min().date()
    max_d = hist["Date"].max().date()
    col1, col2 = st.columns(2)
    with col1:
        start = st.date_input("Holdout start date", value=max(pd.Timestamp("2026-02-21").date(), min_d), min_value=min_d, max_value=max_d)
    with col2:
        end = st.date_input("Holdout end date", value=max_d, min_value=min_d, max_value=max_d)

    hits = find_forward_core025_hits(hist, pd.Timestamp(start), pd.Timestamp(end))
    st.write(f"Core025 hits in selected holdout: **{len(hits)}**")
    if not hits.empty:
        st.dataframe(hits[["HitID", "Date", "AsOfDate", "StreamKey", "Result4", "Core025Member"]], use_container_width=True)
        zip_bytes = make_asof_zip(hist, hits)
        st.download_button(
            "Download as-of history ZIP for manual v162 playback",
            data=zip_bytes,
            file_name=f"core025_asof_histories_{start}_to_{end}.zip",
            mime="application/zip",
        )
        st.download_button(
            "Download forward hit manifest CSV",
            data=hits.to_csv(index=False),
            file_name=f"core025_forward_hits_{start}_to_{end}.csv",
            mime="text/csv",
        )

    st.subheader("2) Upload v162 final playlist exports from manual playback")
    playlist_files = st.file_uploader(
        "Upload one or more v162 final playlist exports (.txt/.csv)",
        type=["txt", "csv", "tsv"],
        accept_multiple_files=True,
    )
    if playlist_files and not hits.empty:
        playlists = read_playlist_files(playlist_files)
        audit = audit_uploaded_playlists(playlists, hits)
        st.write(f"Playlist files read: **{len(playlists)}**")
        st.dataframe(audit, use_container_width=True)
        st.download_button(
            "Download winner audit CSV",
            data=audit.to_csv(index=False),
            file_name="core025_playback_winner_audit.csv",
            mime="text/csv",
        )
        tt = threshold_table(audit)
        if not tt.empty:
            st.subheader("3) ZLT threshold tests on uploaded playback exports")
            st.dataframe(tt, use_container_width=True)
            st.download_button(
                "Download ZLT threshold table CSV",
                data=tt.to_csv(index=False),
                file_name="core025_zlt_threshold_tests.csv",
                mime="text/csv",
            )
        else:
            st.warning("No matched OK playlist audits yet. Check filenames or upload matching exports.")

    st.subheader("Notes")
    st.markdown("""
    - **ZLTCount** is read from `v161_RuleFiredCount` in the v162 export.
    - A threshold is unsafe if the actual winning row meets that cut condition.
    - This lab is winner-centered. It tells whether a threshold would kill winners, not total plays saved.
      Once a threshold survives, we can add a full-play-count pass.
    """)


if __name__ == "__main__":
    main()
