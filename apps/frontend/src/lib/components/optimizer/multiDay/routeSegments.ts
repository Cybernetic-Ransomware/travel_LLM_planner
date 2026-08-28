import type { DayPlan, DayRouteSegment } from '$lib/types/index.js';

export interface SegmentsByKind {
	pre: DayRouteSegment | null;
	post: DayRouteSegment | null;
}

// Look up by kind, never index positionally — a round-tripped MultiDayResponse isn't order-guaranteed. See ADR-17/18.
export function segmentsByKind(day: DayPlan): SegmentsByKind {
	const segments = day.route_segments ?? [];
	return {
		pre: segments.find((s) => s.kind === 'PRE_TRANSFER') ?? null,
		post: segments.find((s) => s.kind === 'POST_TRANSFER') ?? null
	};
}
