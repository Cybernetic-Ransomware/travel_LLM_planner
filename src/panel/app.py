"""Streamlit location management panel for Travel Planner."""

import datetime as _dt

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
    optimize_trip,
    patch_place,
)
from src.panel.chat_client import ChatHistory, stream_chat
from src.panel.messages import (
    ERR_API_UNREACHABLE,
    ERR_ENRICHMENT_FAILED,
    ERR_IMPORT_FAILED,
    ERR_OPTIMIZATION_FAILED,
    ERR_PLACE_COUNT,
    ERR_TRIP_FAILED,
    SKIP_REASON,
)

st.set_page_config(page_title="Travel Planner", layout="wide")
st.title("Travel Planner")


def _hour_to_time(h: int | None) -> pendulum.Time | None:
    return pendulum.time(int(h), 0) if h is not None else None


def _render_day_route(steps: list[dict], skipped: list[dict]) -> None:
    """Render route steps and a folium map for a single day."""
    if not steps:
        st.warning("No feasible route found for the selected places and time constraints.")
    else:
        total_travel_min = sum(s["travel_from_previous_s"] for s in steps) // 60
        total_visit_min = sum(s["visit_duration_min"] for s in steps)
        total_wait_min = sum(s.get("wait_min", 0) for s in steps)
        m1, m2, m3 = st.columns(3)
        m1.metric("Travel time", f"{total_travel_min} min")
        m2.metric("Visit time", f"{total_visit_min} min")
        m3.metric("Waiting time", f"{total_wait_min} min")

        for i, step in enumerate(steps, 1):
            travel_min = step["travel_from_previous_s"] // 60
            wait = step.get("wait_min", 0)
            travel_info = f"🚶 {travel_min} min travel" if i > 1 else "Start"
            wait_info = f" · ⏳ {wait} min wait" if wait > 0 else ""
            with st.expander(f"{i}. {step['name']} — {step['arrival_time']}–{step['departure_time']}", expanded=True):
                st.caption(f"{travel_info}{wait_info} · visit {step['visit_duration_min']} min")

        map_points = [(s["lat"], s["lng"], s["name"], i) for i, s in enumerate(steps, 1) if s.get("lat") and s.get("lng")]
        if map_points:
            center_lat = sum(p[0] for p in map_points) / len(map_points)
            center_lng = sum(p[1] for p in map_points) / len(map_points)
            m = folium.Map(location=[center_lat, center_lng], zoom_start=14)
            folium.PolyLine([(p[0], p[1]) for p in map_points], color="#4A90E2", weight=3, opacity=0.8).add_to(m)
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
                st.write(f"- **{s['name'] or s['place_id']}** — {SKIP_REASON.get(s['reason'], s['reason'])}")


if "chat_history" not in st.session_state:
    st.session_state.chat_history = ChatHistory()

with st.sidebar, st.expander("💬 Chat", expanded=False):
    history: ChatHistory = st.session_state.chat_history
    for msg in history.messages:
        with st.chat_message(msg.role):
            st.write(msg.content)

    try:
        _place_ids = [p["id"] for p in list_places(skipped=False)]
    except Exception:
        _place_ids = []

    if prompt := st.chat_input("Ask about your trip…", key="chat_input"):
        history.add("user", prompt)
        with st.chat_message("user"):
            st.write(prompt)
        try:
            with st.chat_message("assistant"):
                full = str(st.write_stream(stream_chat(history, _place_ids)))
            history.add("assistant", full)
        except Exception as e:
            st.error(str(e))

tab_import, tab_locations, tab_optimizer, tab_multiday = st.tabs(
    ["Import & Enrich", "Locations", "Route Optimizer", "Multi-Day Trip"]
)

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
                st.error(ERR_IMPORT_FAILED.format(detail=e))

    st.divider()

    st.subheader("Enrich places")
    st.caption("Fetches address, coordinates and opening hours from Google Places API for places that are missing them.")

    try:
        all_places = list_places()
        missing = sum(1 for p in all_places if not p.get("address"))
        st.info(f"{missing} of {len(all_places)} places still need enrichment.")
    except Exception:
        st.warning(ERR_PLACE_COUNT)

    limit = st.slider("Batch size", min_value=1, max_value=100, value=20)
    if st.button("Run enrichment", type="primary"):
        with st.spinner("Enriching…"):
            try:
                res = enrich_places(limit)
                st.success(f"Scanned {res['scanned']} places, updated {res['updated']}.")
            except Exception as e:
                st.error(ERR_ENRICHMENT_FAILED.format(detail=e))

with tab_locations:
    col_show, col_list = st.columns([1, 2])
    skipped_option = col_show.selectbox("Show", ["All", "Active only", "Skipped only"])

    try:
        _all_places = list_places()
        _list_names = sorted({p["list_name"] for p in _all_places if p.get("list_name")})
    except Exception:
        _list_names = []

    list_name_choice = col_list.selectbox("List name", ["All"] + _list_names)
    list_name_filter = None if list_name_choice == "All" else list_name_choice

    skipped_filter: bool | None = None
    if skipped_option == "Active only":
        skipped_filter = False
    elif skipped_option == "Skipped only":
        skipped_filter = True

    try:
        places = list_places(skipped=skipped_filter, list_name=list_name_filter)
    except Exception:
        st.error(ERR_API_UNREACHABLE)
        st.stop()

    if not places:
        st.info("No places match the current filters.")
        st.stop()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", len(places))
    m2.metric("Active", sum(1 for p in places if not p.get("skipped")))
    m3.metric("Enriched", sum(1 for p in places if p.get("enriched_at")))
    m4.metric("With hours", sum(1 for p in places if p.get("preferred_hour_from") is not None))

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

    df = pl.DataFrame(places).select([c for c in DISPLAY_COLUMNS if c in pl.DataFrame(places).columns])
    display_df = df.with_columns(
        [pl.col(c).map_elements(_hour_to_time, return_dtype=pl.Object) for c in HOUR_COLS if c in df.columns]
    ).with_columns(pl.lit(False).alias("delete"))

    _table_ver: int = st.session_state.get("_table_key_ver", 0)
    _table_key = f"places_table_{_table_ver}"

    @st.dialog("Confirm deletion")
    def _confirm_delete_dialog() -> None:
        pending: dict = st.session_state.get("_pending_delete", {})
        names: list[str] = pending.get("names", [])
        ids: list[str] = pending.get("ids", [])
        st.write(f"Permanently delete {len(ids)} place(s)?")
        for name in names:
            st.write(f"- **{name}**")
        col1, col2 = st.columns(2)
        if col1.button("Delete", type="primary"):
            errors: list[str] = []
            for place_id in ids:
                try:
                    delete_place(place_id)
                except Exception as e:
                    errors.append(str(e))
            st.session_state.pop("_pending_delete", None)
            st.session_state["_table_key_ver"] = _table_ver + 1
            st.session_state["_table_save_result"] = ("error", errors) if errors else ("ok", len(ids))
            st.rerun()
        if col2.button("Cancel"):
            st.session_state.pop("_pending_delete", None)
            st.session_state["_table_key_ver"] = _table_ver + 1
            st.rerun()

    def _apply_table_changes() -> None:
        table_state: dict = st.session_state.get(_table_key) or {}
        edits: dict = table_state.get("edited_rows", {})
        if not edits:
            return

        to_delete_indices = {idx for idx, ch in edits.items() if ch.get("delete")}
        to_patch = {
            idx: {k: v for k, v in ch.items() if k != "delete"}
            for idx, ch in edits.items()
            if idx not in to_delete_indices and any(k != "delete" for k in ch)
        }

        if to_delete_indices:
            st.session_state["_pending_delete"] = {
                "ids": [places[idx]["id"] for idx in to_delete_indices],
                "names": [places[idx].get("name") or places[idx]["id"] for idx in to_delete_indices],
            }

        errors: list[str] = []
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
            st.session_state["_table_save_result"] = ("error", errors)
        elif to_patch:
            st.session_state["_table_save_result"] = ("ok", len(to_patch))

    if "_pending_delete" in st.session_state:
        _confirm_delete_dialog()

    st.data_editor(
        display_df,
        use_container_width=True,
        disabled=[c for c in display_df.columns if c not in EDITABLE],
        column_config={
            "skipped": st.column_config.CheckboxColumn("Skipped"),
            "delete": st.column_config.CheckboxColumn("🗑️"),
            "preferred_hour_from": st.column_config.TimeColumn("Hour from", step=3600),
            "preferred_hour_to": st.column_config.TimeColumn("Hour to", step=3600),
            "visit_duration_min": st.column_config.NumberColumn("Duration (min)", min_value=1, max_value=480, step=5),
        },
        key=_table_key,
        on_change=_apply_table_changes,
    )

    if _result := st.session_state.pop("_table_save_result", None):
        _kind, _data = _result
        if _kind == "error":
            st.error("\n".join(_data))
        else:
            st.success(f"Saved {_data} change(s).")

    map_places = [p for p in places if p.get("lat") and p.get("lng")]
    if map_places:
        center_lat = sum(p["lat"] for p in map_places) / len(map_places)
        center_lng = sum(p["lng"] for p in map_places) / len(map_places)
        loc_map = folium.Map(location=[center_lat, center_lng], zoom_start=13)
        for p in map_places:
            color = "#6c757d" if p.get("skipped") else "#28a745"
            folium.Marker(
                location=[p["lat"], p["lng"]],
                tooltip=p.get("name") or p["id"],
                icon=folium.DivIcon(
                    html=(
                        f'<div style="background:{color};color:white;border-radius:50%;'
                        f"width:20px;height:20px;display:flex;align-items:center;"
                        f'justify-content:center;font-size:10px;">●</div>'
                    ),
                    icon_size=(20, 20),
                    icon_anchor=(10, 10),
                ),
            ).add_to(loc_map)
        st_folium(loc_map, use_container_width=True, height=400, returned_objects=[])

with tab_optimizer:
    try:
        all_places = list_places(skipped=False)
    except Exception:
        st.error(ERR_API_UNREACHABLE)
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
        departure_date = st.date_input("Departure date (optional)", value=None, min_value=_dt.date.today())

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
            st.error(ERR_OPTIMIZATION_FAILED.format(detail=e))
            st.stop()

        _render_day_route(result.get("steps", []), result.get("skipped", []))

with tab_multiday:
    try:
        all_places_md = list_places(skipped=False)
    except Exception:
        st.error(ERR_API_UNREACHABLE)
        st.stop()

    active_md = [p for p in all_places_md if p.get("lat") and p.get("lng")]

    if not active_md:
        st.info("No active places with coordinates. Import and enrich some places first.")
        st.stop()

    col_days_cfg, col_mode_cfg = st.columns([3, 1])
    with col_days_cfg:
        num_days = int(st.number_input("Number of days", min_value=1, max_value=14, value=2, step=1))
    with col_mode_cfg:
        trip_transport = st.selectbox("Transport mode", ["WALK", "DRIVE", "BICYCLE"], key="trip_transport")

    st.subheader("Day schedule")
    day_dates = []
    day_start_hours = []
    day_end_hours = []

    for i in range(num_days):
        cols = st.columns([2, 1, 1])
        with cols[0]:
            d = st.date_input(
                f"Day {i + 1} date",
                value=_dt.date.today() + _dt.timedelta(days=i),
                min_value=_dt.date.today(),
                key=f"trip_date_{i}",
            )
            day_dates.append(d)
        with cols[1]:
            sh = st.number_input("Start hour", min_value=0, max_value=23, value=9, key=f"trip_start_{i}")
            day_start_hours.append(int(sh))
        with cols[2]:
            eh = st.number_input("End hour", min_value=1, max_value=24, value=21, key=f"trip_end_{i}")
            day_end_hours.append(int(eh))

    st.subheader("Place assignment")
    st.caption("Add multiple rows for the same place to give it flexible day alternatives.")
    day_options = ["Auto"] + [f"Day {i + 1}" for i in range(num_days)]
    name_to_id = {p.get("name") or p["id"]: p["id"] for p in active_md}
    place_names = list(name_to_id.keys())

    assign_df = pl.DataFrame(
        {
            "place": place_names,
            "day": ["Auto"] * len(active_md),
            "hour_from": [None] * len(active_md),
            "hour_to": [None] * len(active_md),
        },
        schema={"place": pl.String, "day": pl.String, "hour_from": pl.Object, "hour_to": pl.Object},
    )

    edited_df = st.data_editor(
        assign_df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "place": st.column_config.SelectboxColumn("Place", options=place_names, required=True),
            "day": st.column_config.SelectboxColumn("Day", options=day_options),
            "hour_from": st.column_config.TimeColumn("Hour from", step=3600),
            "hour_to": st.column_config.TimeColumn("Hour to", step=3600),
        },
        key="trip_assignment_table",
    )

    if st.button("Plan Multi-Day Trip", type="primary", use_container_width=True):
        days_payload = [
            {
                "date": day_dates[i].isoformat(),
                "day_start_hour": day_start_hours[i],
                "day_end_hour": day_end_hours[i],
            }
            for i in range(num_days)
        ]

        places_by_id: dict[str, list[dict]] = {}
        for row in edited_df.to_dicts():
            place_name = row.get("place")
            place_id = name_to_id.get(place_name) if place_name else None
            if place_id is None:
                continue
            if place_id not in places_by_id:
                places_by_id[place_id] = []
            day_val = row.get("day") or "Auto"
            if day_val != "Auto":
                slot: dict = {"day_index": int(day_val.split(" ")[1]) - 1}
                for field, key in (("hour_from", "preferred_hour_from"), ("hour_to", "preferred_hour_to")):
                    val = row.get(field)
                    if val is not None:
                        slot[key] = val.hour if hasattr(val, "hour") else int(str(val).split(":")[0])
                places_by_id[place_id].append(slot)

        places_payload = [{"place_id": pid, "day_preferences": slots} for pid, slots in places_by_id.items()]

        trip_payload = {
            "days": days_payload,
            "places": places_payload,
            "transport_mode": trip_transport,
        }

        try:
            trip_result = optimize_trip(trip_payload)
        except Exception as e:
            st.error(ERR_TRIP_FAILED.format(detail=e))
            st.stop()

        for day_data in trip_result.get("days", []):
            day_label = f"Day {day_data['day_index'] + 1} — {day_data['date']}"
            with st.expander(day_label, expanded=True):
                _render_day_route(day_data.get("steps", []), day_data.get("skipped", []))

        if trip_result.get("unassigned"):
            with st.expander(f"Unassigned places ({len(trip_result['unassigned'])})"):
                for s in trip_result["unassigned"]:
                    st.write(f"- **{s['name'] or s['place_id']}** — {SKIP_REASON.get(s['reason'], s['reason'])}")
