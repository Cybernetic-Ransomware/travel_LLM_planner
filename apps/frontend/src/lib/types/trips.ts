import type { OptimizeRequest, OptimizeResponse, TransportMode } from './optimizer.js';

export interface SaveTripRequest {
	name: string;
	date: string;
	optimizer_request: OptimizeRequest;
	optimizer_response: OptimizeResponse;
}

export interface TripSummaryOut {
	id: string;
	name: string;
	date: string;
	created_at: string;
}

export interface TripOut extends TripSummaryOut {
	updated_at?: string | null;
	optimizer_request: OptimizeRequest;
	optimizer_response: OptimizeResponse;
	selected_place_ids: string[];
	transport_mode: TransportMode;
	day_start_hour: number;
	day_end_hour: number;
}
