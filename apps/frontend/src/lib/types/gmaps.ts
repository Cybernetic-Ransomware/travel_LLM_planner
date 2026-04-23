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

export interface PlacePatch {
	preferred_hour_from?: number | null;
	preferred_hour_to?: number | null;
	visit_duration_min?: number | null;
	skipped?: boolean | null;
}

export interface ImportRequest {
	list_url: string;
}

export interface ImportResponse {
	list_url: string;
	list_name: string | null;
	scraped_at: string;
	total: number;
	upserted: number;
}

export interface EnrichRequest {
	limit: number;
}

export interface EnrichResponse {
	scanned: number;
	updated: number;
}
