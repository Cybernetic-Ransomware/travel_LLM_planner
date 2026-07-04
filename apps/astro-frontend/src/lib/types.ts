// Explicit copies of the backend contracts used by this spike.
// Source of truth: src/gmaps/models.py (PlaceOut) and apps/frontend/src/lib/types/.

export interface PlaceOut {
	id: string;
	name: string | null;
	address: string | null;
	maps_url: string | null;
	lat: number | null;
	lng: number | null;
	gmaps_place_id: string | null;
	list_name: string | null;
	source_list_url: string | null;
	scraped_at: string | null;
	enriched_at: string | null;
	opening_hours: Record<string, unknown> | null;
	preferred_hour_from: number | null;
	preferred_hour_to: number | null;
	visit_duration_min: number | null;
	skipped: boolean;
}

export interface RouteStep {
	place_id: string;
	name: string | null;
	lat: number | null;
	lng: number | null;
	arrival_time: string;
	departure_time: string;
	travel_from_previous_s: number;
	visit_duration_min: number;
	wait_min: number;
}

export interface PlaceStats {
	total: number;
	active: number;
	enriched: number;
	withHours: number;
}

export type TransportMode = 'WALK' | 'DRIVE' | 'BICYCLE' | 'TRANSIT';

export interface SkippedPlace {
	place_id: string;
	name: string | null;
	reason: string;
}

export interface OptimizeRequest {
	place_ids: string[];
	transport_mode?: TransportMode;
	day_start_hour?: number;
	day_end_hour?: number;
	start_lat?: number;
	start_lng?: number;
	departure_date?: string;
}

export interface OptimizeResponse {
	steps: RouteStep[];
	total_travel_time_s: number;
	total_visit_time_min: number;
	total_wait_min: number;
	transport_mode: TransportMode;
	skipped: SkippedPlace[];
}
