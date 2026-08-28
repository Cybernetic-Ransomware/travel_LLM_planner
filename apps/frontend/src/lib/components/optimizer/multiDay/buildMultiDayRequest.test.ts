import { describe, it, expect } from 'vitest';
import {
	buildMultiDayRequest,
	defaultEditableState,
	hasIncompleteAccommodation,
	type MultiDayEditableState
} from './buildMultiDayRequest.js';
import { hydrateEditableState, countMissingPrefillPlaces } from './hydrateMultiDayState.js';
import { emptyAccommodationDraft } from './accommodationDraft.js';
import type { MultiDayRequest } from '$lib/types/index.js';

describe('defaultEditableState', () => {
	it('starts with one day and no accommodations/transfers', () => {
		const state = defaultEditableState();
		expect(state.days).toHaveLength(1);
		expect(state.accommodations).toEqual([]);
		expect(state.transfers.size).toBe(0);
		expect(state.transportMode).toBe('WALK');
	});
});

describe('buildMultiDayRequest', () => {
	it('builds places from full DaySlot[] entries, not bare indices', () => {
		const state: MultiDayEditableState = {
			...defaultEditableState(),
			placeSelections: new Map([
				['p1', [{ day_index: 0, preferred_hour_from: 9, preferred_hour_to: 12 }]]
			])
		};
		const request = buildMultiDayRequest(state);
		expect(request.places).toEqual([
			{
				place_id: 'p1',
				day_preferences: [{ day_index: 0, preferred_hour_from: 9, preferred_hour_to: 12 }]
			}
		]);
	});

	it('maps a complete accommodation draft to an AccommodationStay, without filtering by day range', () => {
		const state: MultiDayEditableState = {
			...defaultEditableState(),
			accommodations: [
				{
					localKey: 'k1',
					name: 'Hotel',
					lat: 1,
					lng: 2,
					check_in_date: '2026-01-01',
					check_out_date: '2099-01-01',
					check_in_from: null,
					check_out_by: null
				}
			]
		};
		const request = buildMultiDayRequest(state);
		expect(request.accommodations).toEqual([
			{
				name: 'Hotel',
				lat: 1,
				lng: 2,
				check_in_date: '2026-01-01',
				check_out_date: '2099-01-01',
				check_in_from: null,
				check_out_by: null
			}
		]);
	});

	it('never emits an AccommodationStay for an incomplete draft (null coordinates)', () => {
		const state: MultiDayEditableState = {
			...defaultEditableState(),
			accommodations: [emptyAccommodationDraft('k1', '2026-01-01')]
		};
		const request = buildMultiDayRequest(state);
		expect(request.accommodations).toEqual([]);
	});

	it('serializes null global anchors as null, not undefined', () => {
		const request = buildMultiDayRequest(defaultEditableState());
		expect(request.start_lat).toBeNull();
		expect(request.end_lng).toBeNull();
	});
});

describe('hasIncompleteAccommodation', () => {
	it('is false with no accommodation rows', () => {
		expect(hasIncompleteAccommodation(defaultEditableState())).toBe(false);
	});

	it('is true when a row has no coordinates yet', () => {
		const state: MultiDayEditableState = {
			...defaultEditableState(),
			accommodations: [emptyAccommodationDraft('k1', '2026-01-01')]
		};
		expect(hasIncompleteAccommodation(state)).toBe(true);
	});
});

describe('lossless round-trip: hydrate -> unrelated edit -> build', () => {
	const persisted: MultiDayRequest = {
		days: [
			{
				date: '2026-03-01',
				day_start_hour: 8,
				day_end_hour: 20,
				start_lat: 50.05,
				start_lng: 19.95
			},
			{ date: '2026-03-02', day_start_hour: 9, day_end_hour: 21 }
		],
		places: [
			{
				place_id: 'p1',
				day_preferences: [{ day_index: 0, preferred_hour_from: 10, preferred_hour_to: 12 }]
			},
			{ place_id: 'p2', day_preferences: [] }
		],
		transport_mode: 'DRIVE',
		start_lat: 50.06,
		start_lng: 19.94,
		end_lat: 50.07,
		end_lng: 19.93,
		accommodations: [
			{
				name: 'Hotel A',
				lat: 50.06,
				lng: 19.94,
				check_in_date: '2026-02-28',
				check_out_date: '2026-03-02'
			}
		],
		transfers: [
			{ date: '2026-03-02', departure_time: '10:00:00', arrival_time: '11:00:00', label: 'Taxi' }
		]
	};

	it('preserves every field the UI does not edit across an unrelated transportMode edit', () => {
		const state = hydrateEditableState(persisted);
		// Simulate an unrelated edit: change transport mode only.
		state.transportMode = 'WALK';
		const rebuilt = buildMultiDayRequest(state);

		expect(rebuilt.places[0].day_preferences).toEqual(persisted.places[0].day_preferences);
		expect(rebuilt.start_lat).toBe(persisted.start_lat);
		expect(rebuilt.start_lng).toBe(persisted.start_lng);
		expect(rebuilt.end_lat).toBe(persisted.end_lat);
		expect(rebuilt.end_lng).toBe(persisted.end_lng);
		expect(rebuilt.days[0].start_lat).toBe(persisted.days[0].start_lat);
		expect(rebuilt.days[0].start_lng).toBe(persisted.days[0].start_lng);
		expect(rebuilt.accommodations).toEqual([
			{
				name: 'Hotel A',
				lat: 50.06,
				lng: 19.94,
				check_in_date: '2026-02-28',
				check_out_date: '2026-03-02',
				check_in_from: null,
				check_out_by: null
			}
		]);
		expect(rebuilt.transfers).toEqual(persisted.transfers);
		expect(rebuilt.transport_mode).toBe('WALK');
	});

	it('drops a place preference whose place_id is no longer available, and counts it', () => {
		const available = new Set(['p1']);
		expect(countMissingPrefillPlaces(persisted, available)).toBe(1);
		const state = hydrateEditableState(persisted, available);
		expect([...state.placeSelections.keys()]).toEqual(['p1']);
	});
});
