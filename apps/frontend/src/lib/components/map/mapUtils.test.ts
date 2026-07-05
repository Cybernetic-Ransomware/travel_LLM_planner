import { describe, it, expect } from 'vitest';
import { getMapCenter } from './mapUtils.js';
import type { PlaceOut, RouteStep } from '$lib/types/index.js';

const WARSAW: [number, number] = [52.23, 21.01];

function mockPlace(lat: number | null, lng: number | null): PlaceOut {
	return {
		id: 'p1',
		name: 'Test Place',
		address: null,
		maps_url: null,
		lat,
		lng,
		gmaps_place_id: null,
		list_name: null,
		source_list_url: null,
		scraped_at: null,
		enriched_at: null,
		opening_hours: null,
		preferred_hour_from: null,
		preferred_hour_to: null,
		visit_duration_min: null,
		skipped: false
	};
}

function mockStep(lat: number | null, lng: number | null): RouteStep {
	return {
		place_id: 's1',
		name: 'Test Step',
		lat,
		lng,
		arrival_time: '09:00:00',
		departure_time: '10:00:00',
		travel_from_previous_s: 0,
		visit_duration_min: 60,
		wait_min: 0
	};
}

describe('getMapCenter', () => {
	it('returns Warsaw fallback when places and steps are empty', () => {
		expect(getMapCenter([], [])).toEqual(WARSAW);
	});

	it('returns Warsaw fallback when all coordinates are null', () => {
		expect(getMapCenter([mockPlace(null, null)], [])).toEqual(WARSAW);
	});

	it('uses places center when steps is empty', () => {
		const places = [mockPlace(50.0, 20.0), mockPlace(52.0, 22.0)];
		const [lat, lng] = getMapCenter(places, []);
		expect(lat).toBeCloseTo(51.0);
		expect(lng).toBeCloseTo(21.0);
	});

	it('uses steps center when steps have coordinates, ignores places', () => {
		const places = [mockPlace(10.0, 10.0)];
		const steps = [mockStep(50.0, 20.0), mockStep(52.0, 22.0)];
		const [lat, lng] = getMapCenter(places, steps);
		expect(lat).toBeCloseTo(51.0);
		expect(lng).toBeCloseTo(21.0);
	});

	it('ignores steps with null coordinates', () => {
		const steps = [mockStep(null, null), mockStep(50.0, 20.0)];
		const [lat, lng] = getMapCenter([], steps);
		expect(lat).toBeCloseTo(50.0);
		expect(lng).toBeCloseTo(20.0);
	});
});
