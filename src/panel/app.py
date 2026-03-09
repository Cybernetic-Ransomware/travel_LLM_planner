"""Streamlit location management panel for Travel Planner."""

import pendulum
import polars as pl
import streamlit as st

from src.panel.api_client import delete_place, list_places, patch_place

st.set_page_config(page_title="Travel Planner — Locations", layout="wide")
st.title("Location Manager")

# --- Sidebar filters ---
with st.sidebar:
    st.header("Filters")
    skipped_option = st.selectbox("Show", ["All", "Active only", "Skipped only"])
    list_name_filter = st.text_input("List name")

skipped_filter: bool | None = None
if skipped_option == "Active only":
    skipped_filter = False
elif skipped_option == "Skipped only":
    skipped_filter = True

# --- Fetch places ---
try:
    places = list_places(
        skipped=skipped_filter,
        list_name=list_name_filter or None,
    )
except Exception as e:
    st.error(f"Cannot connect to API: {e}")
    st.stop()

if not places:
    st.info("No places match the current filters.")
    st.stop()

# --- Table ---
DISPLAY_COLUMNS = [
    "name",
    "address",
    "list_name",
    "skipped",
    "preferred_hour_from",
    "preferred_hour_to",
    "visit_duration_min",
]
EDITABLE = {"skipped", "preferred_hour_from", "preferred_hour_to", "visit_duration_min", "delete"}
HOUR_COLS = ("preferred_hour_from", "preferred_hour_to")


def _hour_to_time(h: int | None) -> pendulum.Time | None:
    return pendulum.time(int(h), 0) if h is not None else None


df = pl.DataFrame(places).select([c for c in DISPLAY_COLUMNS if c in pl.DataFrame(places).columns])
display_df = df.with_columns(
    [pl.col(c).map_elements(_hour_to_time, return_dtype=pl.Object) for c in HOUR_COLS if c in df.columns]
).with_columns(pl.lit(False).alias("delete"))

st.data_editor(
    display_df,
    width="stretch",
    disabled=[c for c in display_df.columns if c not in EDITABLE],
    column_config={
        "skipped": st.column_config.CheckboxColumn("Skipped"),
        "delete": st.column_config.CheckboxColumn("🗑️"),
        "preferred_hour_from": st.column_config.TimeColumn("Hour from", step=3600),
        "preferred_hour_to": st.column_config.TimeColumn("Hour to", step=3600),
        "visit_duration_min": st.column_config.NumberColumn("Duration (min)", min_value=1, max_value=480, step=5),
    },
    key="places_table",
)

table_state: dict = st.session_state.get("places_table") or {}
edits: dict = table_state.get("edited_rows", {})

to_delete = {idx for idx, ch in edits.items() if ch.get("delete")}
to_patch = {
    idx: {k: v for k, v in ch.items() if k != "delete"}
    for idx, ch in edits.items()
    if idx not in to_delete and len(ch) > (1 if "delete" in ch else 0)
}

col_apply, col_delete = st.columns([1, 1])

with col_apply:
    if to_patch and st.button("Apply changes", type="primary"):
        errors = []
        for row_idx, changes in to_patch.items():
            for col in HOUR_COLS:
                if col in changes:
                    val = changes[col]
                    if hasattr(val, "hour"):
                        changes[col] = val.hour
                    elif isinstance(val, str) and val:
                        changes[col] = int(val.split(":")[0])
            try:
                patch_place(places[row_idx]["id"], changes)
            except Exception as e:
                errors.append(str(e))
        if errors:
            st.error("\n".join(errors))
        else:
            st.success(f"Updated {len(to_patch)} place(s).")
            st.rerun()

with col_delete:
    if to_delete and st.button(f"Delete {len(to_delete)} selected", type="secondary"):
        errors = []
        for row_idx in to_delete:
            try:
                delete_place(places[row_idx]["id"])
            except Exception as e:
                errors.append(str(e))
        if errors:
            st.error("\n".join(errors))
        else:
            st.success(f"Deleted {len(to_delete)} place(s).")
            st.rerun()
