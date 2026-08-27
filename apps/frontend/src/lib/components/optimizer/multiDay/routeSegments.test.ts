import { describe, it, expect } from 'vitest';
import { segmentsByKind } from './routeSegments.js';
import type { DayPlan, DayRouteSegment } from '$lib/types/index.js';

function segment(kind: DayRouteSegment['kind']): DayRouteSegment {
	return {
		kind,
		steps: [],
		total_travel_time_s: 0,
		total_visit_time_min: 0,
		total_wait_min: 0,
		skipped: []
	};
}

function day(overrides: Partial<DayPlan> = {}): DayPlan {
	return {
		day_index: 0,
		date: '2026-03-01',
		steps: [],
		total_travel_time_s: 0,
		total_visit_time_min: 0,
		total_wait_min: 0,
		skipped: [],
		...overrides
	};
}

describe('segmentsByKind', () => {
	it('finds PRE and POST regardless of order', () => {
		const result = segmentsByKind(
			day({ route_segments: [segment('POST_TRANSFER'), segment('PRE_TRANSFER')] })
		);
		expect(result.pre?.kind).toBe('PRE_TRANSFER');
		expect(result.post?.kind).toBe('POST_TRANSFER');
	});

	it('returns null for a missing segment rather than falling back positionally', () => {
		const result = segmentsByKind(day({ route_segments: [segment('PRE_TRANSFER')] }));
		expect(result.pre?.kind).toBe('PRE_TRANSFER');
		expect(result.post).toBeNull();
	});

	it('returns both null when route_segments is absent (ordinary day)', () => {
		const result = segmentsByKind(day());
		expect(result.pre).toBeNull();
		expect(result.post).toBeNull();
	});

	it('returns both null when route_segments is empty', () => {
		const result = segmentsByKind(day({ route_segments: [] }));
		expect(result.pre).toBeNull();
		expect(result.post).toBeNull();
	});
});
