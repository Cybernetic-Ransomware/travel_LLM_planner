import type { OptimizeRequest, OptimizeResponse, TransportMode } from './optimizer.js';

export interface SaveTripRequest {
	name: string;
	date: string;
	optimizer_request: OptimizeRequest;
	optimizer_response: OptimizeResponse;
}

export interface SingleDayTripSummaryOut {
	plan_type: 'SINGLE_DAY';
	id: string;
	name: string;
	date: string;
	created_at: string;
}

export interface MultiDayTripSummaryOut {
	plan_type: 'MULTI_DAY';
	id: string;
	name: string;
	start_date: string;
	end_date: string;
	num_days: number;
	created_at: string;
}

export type TripSummaryOut = SingleDayTripSummaryOut | MultiDayTripSummaryOut;

export interface SingleDayTripOut extends SingleDayTripSummaryOut {
	updated_at?: string | null;
	optimizer_request: OptimizeRequest;
	optimizer_response: OptimizeResponse;
	selected_place_ids: string[];
	transport_mode: TransportMode;
	day_start_hour: number;
	day_end_hour: number;
}

export interface MultiDayTripOut extends MultiDayTripSummaryOut {
	updated_at?: string | null;
	transport_mode: TransportMode;
	// Intentionally minimal — full multi-day itinerary typing (days/accommodations/transfers/
	// route_segments) is a later stage's concern, not this compatibility tail's.
}

export type TripOut = SingleDayTripOut | MultiDayTripOut;
