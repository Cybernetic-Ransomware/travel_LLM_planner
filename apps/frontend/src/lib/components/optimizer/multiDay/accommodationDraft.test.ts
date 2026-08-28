import { describe, it, expect } from 'vitest';
import {
	emptyAccommodationDraft,
	stayToDraft,
	isCompleteAccommodationDraft,
	draftToStay,
	hasNoStayOverlaps
} from './accommodationDraft.js';
import type { AccommodationStay } from '$lib/types/index.js';

describe('emptyAccommodationDraft', () => {
	it('starts incomplete with null coordinates', () => {
		const draft = emptyAccommodationDraft('k1', '2026-01-01');
		expect(isCompleteAccommodationDraft(draft)).toBe(false);
	});
});

describe('isCompleteAccommodationDraft', () => {
	it('is incomplete without a name', () => {
		const draft = {
			...emptyAccommodationDraft('k1', '2026-01-01'),
			lat: 1,
			lng: 2,
			check_out_date: '2026-01-02'
		};
		expect(isCompleteAccommodationDraft(draft)).toBe(false);
	});

	it('is incomplete without coordinates', () => {
		const draft = {
			...emptyAccommodationDraft('k1', '2026-01-01'),
			name: 'Hotel',
			check_out_date: '2026-01-02'
		};
		expect(isCompleteAccommodationDraft(draft)).toBe(false);
	});

	it('is incomplete when checkout does not cover at least one night', () => {
		const draft = {
			...emptyAccommodationDraft('k1', '2026-01-01'),
			name: 'Hotel',
			lat: 1,
			lng: 2,
			check_out_date: '2026-01-01'
		};
		expect(isCompleteAccommodationDraft(draft)).toBe(false);
	});

	it('is complete with a name, coordinates, and a valid night', () => {
		const draft = {
			...emptyAccommodationDraft('k1', '2026-01-01'),
			name: 'Hotel',
			lat: 1,
			lng: 2,
			check_out_date: '2026-01-02'
		};
		expect(isCompleteAccommodationDraft(draft)).toBe(true);
	});
});

describe('draftToStay/stayToDraft', () => {
	it('round-trips a complete draft through a stay', () => {
		const stay: AccommodationStay = {
			name: 'Hotel A',
			lat: 50.1,
			lng: 20.1,
			check_in_date: '2026-01-01',
			check_out_date: '2026-01-03',
			check_in_from: '14:00',
			check_out_by: '11:00'
		};
		const draft = stayToDraft('k1', stay);
		expect(draftToStay(draft)).toEqual(stay);
	});

	it('throws when converting an incomplete draft', () => {
		expect(() => draftToStay(emptyAccommodationDraft('k1', '2026-01-01'))).toThrow();
	});
});

describe('hasNoStayOverlaps', () => {
	it('accepts non-overlapping complete stays, ignoring incomplete drafts', () => {
		const drafts = [
			{
				...emptyAccommodationDraft('a', '2026-01-01'),
				name: 'A',
				lat: 1,
				lng: 1,
				check_out_date: '2026-01-03'
			},
			{
				...emptyAccommodationDraft('b', '2026-01-03'),
				name: 'B',
				lat: 2,
				lng: 2,
				check_out_date: '2026-01-05'
			},
			emptyAccommodationDraft('c', '2026-05-01')
		];
		expect(hasNoStayOverlaps(drafts)).toBe(true);
	});

	it('rejects overlapping complete stays', () => {
		const drafts = [
			{
				...emptyAccommodationDraft('a', '2026-01-01'),
				name: 'A',
				lat: 1,
				lng: 1,
				check_out_date: '2026-01-05'
			},
			{
				...emptyAccommodationDraft('b', '2026-01-03'),
				name: 'B',
				lat: 2,
				lng: 2,
				check_out_date: '2026-01-06'
			}
		];
		expect(hasNoStayOverlaps(drafts)).toBe(false);
	});
});
