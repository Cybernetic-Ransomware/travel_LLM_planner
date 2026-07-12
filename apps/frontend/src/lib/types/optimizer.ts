export type TransportMode = 'WALK' | 'DRIVE' | 'BICYCLE' | 'TRANSIT';
export type TransportModeNoTransit = 'WALK' | 'DRIVE' | 'BICYCLE';

export interface OptimizeRequest {
	place_ids: string[];
	transport_mode: TransportMode;
	day_start_hour: number;
	day_end_hour: number;
	start_lat?: number;
	start_lng?: number;
	departure_date?: string;
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

export interface SkippedPlace {
	place_id: string;
	name: string | null;
	reason:
		| 'NO_COORDINATES'
		| 'TIME_WINDOW_INFEASIBLE'
		| 'NO_MATRIX_ENTRY'
		| 'MATRIX_INCOMPLETE'
		| 'DROPPED_LOW_PRIORITY';
}

export interface OptimizeResponse {
	steps: RouteStep[];
	total_travel_time_s: number;
	total_visit_time_min: number;
	total_wait_min: number;
	transport_mode: TransportMode;
	skipped: SkippedPlace[];
}

export interface DayConfig {
	date: string;
	day_start_hour: number;
	day_end_hour: number;
}

export interface DaySlot {
	day_index: number;
	preferred_hour_from?: number;
	preferred_hour_to?: number;
}

export interface PlaceDayPreference {
	place_id: string;
	day_preferences: DaySlot[];
}

export interface MultiDayRequest {
	days: DayConfig[];
	places: PlaceDayPreference[];
	transport_mode: TransportModeNoTransit;
	start_lat?: number;
	start_lng?: number;
}

export interface DayPlan {
	day_index: number;
	date: string;
	steps: RouteStep[];
	skipped: SkippedPlace[];
}

export interface MultiDayResponse {
	days: DayPlan[];
	transport_mode: TransportModeNoTransit;
	unassigned: SkippedPlace[];
}
