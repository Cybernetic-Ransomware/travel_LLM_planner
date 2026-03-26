"""Streamlit location management panel for Travel Planner."""

import folium
import pendulum
import polars as pl
import streamlit as st
from streamlit_folium import st_folium

from src.panel.api_client import (
    delete_place,
    enrich_places,
    import_list,
    list_places,
    optimize_route,
    patch_place,
)

st.set_page_config(page_title="Travel Planner", layout="wide")
st.title("Travel Planner")

tab_import, tab_locations, tab_optimizer = st.tabs(["Import & Enrich", "Locations", "Route Optimizer"])

with tab_import:
    st.subheader("Import from Google Maps list")
    st.caption("Paste the URL of a public Google Maps saved list (e.g. maps.app.goo.gl/...).")

    list_url = st.text_input("Google Maps list URL")
    if st.button("Import", type="primary", disabled=not list_url):
        with st.spinner("Scraping list — this may take up to 2 minutes…"):
            try:
                res = import_list(list_url)
                st.success(
                    f"**{res.get('list_name') or 'List'}** imported: "
                    f"{res['total']} places found, {res['upserted']} new/updated."
                )
            except Exception as e:
                st.error(f"Import failed: {e}")

    st.divider()

    st.subheader("Enrich places")
    st.caption("Fetches address, coordinates and opening hours from Google Places API for places that are missing them.")

    try:
        all_places = list_places()
        missing = sum(1 for p in all_places if not p.get("address"))
        st.info(f"{missing} of {len(all_places)} places still need enrichment.")
    except Exception as e:
        st.warning(f"Could not load place count: {e}")

    limit = st.slider("Batch size", min_value=1, max_value=100, value=20)
    if st.button("Run enrichment", type="primary"):
        with st.spinner("Enriching…"):
            try:
                res = enrich_places(limit)
                st.success(f"Scanned {res['scanned']} places, updated {res['updated']}.")
            except Exception as e:
                st.error(f"Enrichment failed: {e}")

with tab_locations:
    with st.sidebar:
        st.header("Filters")
        skipped_option = st.selectbox("Show", ["All", "Active only", "Skipped only"])
        list_name_filter = st.text_input("List name")

    skipped_filter: bool | None = None
    if skipped_option == "Active only":
        skipped_filter = False
    elif skipped_option == "Skipped only":
        skipped_filter = True

    try:
        places = list_places(skipped=skipped_filter, list_name=list_name_filter or None)
    except Exception as e:
        st.error(f"Cannot connect to API: {e}")
        st.stop()

    if not places:
        st.info("No places match the current filters.")
        st.stop()

    DISPLAY_COLUMNS = [
        "name",
        "address",
        "lat",
        "lng",
        "enriched_at",
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

with tab_optimizer:
    try:
        all_places = list_places(skipped=False)
    except Exception as e:
        st.error(f"Cannot connect to API: {e}")
        st.stop()

    active_with_coords = [p for p in all_places if p.get("lat") and p.get("lng")]

    if not active_with_coords:
        st.info("No active places with coordinates. Import and enrich some places first.")
        st.stop()

    place_options = {p["name"] or p["id"]: p["id"] for p in active_with_coords}

    col_left, col_right = st.columns([2, 1])

    with col_left:
        selected_names = st.multiselect(
            "Places to visit",
            options=list(place_options.keys()),
            default=list(place_options.keys()),
        )

    with col_right:
        transport_mode = st.selectbox("Transport mode", ["WALK", "DRIVE", "BICYCLE", "TRANSIT"])
        col_start, col_end = st.columns(2)
        with col_start:
            day_start_hour = st.number_input("Start hour", min_value=0, max_value=23, value=9)
        with col_end:
            day_end_hour = st.number_input("End hour", min_value=1, max_value=24, value=21)
        departure_date = st.date_input("Departure date (optional)", value=None)

    if len(selected_names) < 2:
        st.warning("Select at least 2 places.")
        st.stop()

    if st.button("Optimize Route", type="primary", use_container_width=True):
        payload: dict = {
            "place_ids": [place_options[n] for n in selected_names],
            "transport_mode": transport_mode,
            "day_start_hour": int(day_start_hour),
            "day_end_hour": int(day_end_hour),
        }
        if departure_date:
            payload["departure_date"] = departure_date.isoformat()

        try:
            result = optimize_route(payload)
        except Exception as e:
            st.error(f"Optimization failed: {e}")
            st.stop()

        steps = result.get("steps", [])
        skipped = result.get("skipped", [])

        if not steps:
            st.warning("No feasible route found for the selected places and time constraints.")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Travel time", f"{result['total_travel_time_s'] // 60} min")
            m2.metric("Visit time", f"{result['total_visit_time_min']} min")
            m3.metric("Waiting time", f"{result['total_wait_min']} min")

            st.subheader("Route")
            for i, step in enumerate(steps, 1):
                travel_min = step["travel_from_previous_s"] // 60
                wait = step["wait_min"]
                travel_info = f"🚶 {travel_min} min travel" if i > 1 else "Start"
                wait_info = f" · ⏳ {wait} min wait" if wait > 0 else ""
                with st.expander(f"{i}. {step['name']} — {step['arrival_time']}–{step['departure_time']}", expanded=True):
                    st.caption(f"{travel_info}{wait_info} · visit {step['visit_duration_min']} min")

            map_points = [(s["lat"], s["lng"], s["name"], i) for i, s in enumerate(steps, 1) if s["lat"] and s["lng"]]
            if map_points:
                center_lat = sum(p[0] for p in map_points) / len(map_points)
                center_lng = sum(p[1] for p in map_points) / len(map_points)
                m = folium.Map(location=[center_lat, center_lng], zoom_start=14)

                coords = [(p[0], p[1]) for p in map_points]
                folium.PolyLine(coords, color="#4A90E2", weight=3, opacity=0.8).add_to(m)

                for lat, lng, name, idx in map_points:
                    folium.Marker(
                        location=[lat, lng],
                        tooltip=f"{idx}. {name}",
                        icon=folium.DivIcon(
                            html=(
                                f'<div style="background:#4A90E2;color:white;border-radius:50%;'
                                f"width:24px;height:24px;display:flex;align-items:center;"
                                f'justify-content:center;font-weight:bold;font-size:12px;">{idx}</div>'
                            ),
                            icon_size=(24, 24),
                            icon_anchor=(12, 12),
                        ),
                    ).add_to(m)

                st_folium(m, use_container_width=True, height=400, returned_objects=[])

        if skipped:
            with st.expander(f"Skipped places ({len(skipped)})"):
                for s in skipped:
                    st.write(f"- **{s['name'] or s['place_id']}** — {s['reason']}")
