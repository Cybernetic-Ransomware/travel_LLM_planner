import type { DayConfig } from '$lib/types/index.js';

export const MIN_TRIP_DAYS = 1;
export const MAX_TRIP_DAYS = 31;

export type DayTimeMode = 'hour' | 'exact';

export interface DayBoundaryState {
	mode: DayTimeMode;
	hour: number;
	time: string | null;
}

// Mirrors DayConfig.day_start_hour/day_end_hour defaults in src/optimizer/solver/models.py.
export const DEFAULT_DAY_START_HOUR = 9;
export const DEFAULT_DAY_END_HOUR = 21;

export function hydrateBoundary(hour: number, time: string | null): DayBoundaryState {
	return time !== null ? { mode: 'exact', time, hour } : { mode: 'hour', hour, time: null };
}

// isEndBoundary guards against day_end_hour=24 + day_end_time both being set, which the backend rejects.
export function serializeBoundary(
	boundary: DayBoundaryState,
	isEndBoundary: boolean
): { hour: number; time: string | null } {
	if (boundary.mode === 'hour') return { hour: boundary.hour, time: null };
	const hour = isEndBoundary && boundary.hour === 24 ? 23 : boundary.hour;
	return { hour, time: boundary.time };
}

// Mirrors resolve_day_bound_s in src/optimizer/solver/models.py.
export function resolveBoundarySeconds(boundary: DayBoundaryState): number {
	if (boundary.mode === 'exact' && boundary.time) {
		const [h, min] = boundary.time.split(':').map(Number);
		return h * 3600 + min * 60;
	}
	return boundary.hour * 3600;
}

export interface BoundaryValidationResult {
	valid: boolean;
	errorKey?: 'day_end_time_midnight_invalid' | 'day_range_invalid';
}

// Pure domain validation — HTML constraints like <input min="00:01"> are UX hints only, never the real gate.
export function isValidBoundaryPair(
	start: DayBoundaryState,
	end: DayBoundaryState
): BoundaryValidationResult {
	if (end.mode === 'exact' && end.time === '00:00') {
		return { valid: false, errorKey: 'day_end_time_midnight_invalid' };
	}
	if (resolveBoundarySeconds(start) >= resolveBoundarySeconds(end)) {
		return { valid: false, errorKey: 'day_range_invalid' };
	}
	return { valid: true };
}

export function defaultDayConfig(date: string): DayConfig {
	return { date, day_start_hour: DEFAULT_DAY_START_HOUR, day_end_hour: DEFAULT_DAY_END_HOUR };
}

export function isDayConfigValid(day: DayConfig): boolean {
	const start = hydrateBoundary(
		day.day_start_hour ?? DEFAULT_DAY_START_HOUR,
		day.day_start_time ?? null
	);
	const end = hydrateBoundary(day.day_end_hour ?? DEFAULT_DAY_END_HOUR, day.day_end_time ?? null);
	return isValidBoundaryPair(start, end).valid;
}
