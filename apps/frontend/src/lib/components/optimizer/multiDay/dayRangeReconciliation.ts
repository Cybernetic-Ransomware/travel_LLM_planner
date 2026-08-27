import type { DayConfig, TransferBlock } from '$lib/types/index.js';
import { defaultDayConfig } from './dayConfig.js';

export function addDays(dateStr: string, days: number): string {
	const d = new Date(`${dateStr}T00:00:00Z`);
	d.setUTCDate(d.getUTCDate() + days);
	return d.toISOString().slice(0, 10);
}

// Preserves per-day anchor overrides via {...prev, date} as long as a day's index doesn't shift (see ADR-15).
export function reconcileDays(
	existing: DayConfig[],
	startDate: string,
	numDays: number
): DayConfig[] {
	return Array.from({ length: numDays }, (_, i) => {
		const date = addDays(startDate, i);
		const prev = existing[i];
		return prev ? { ...prev, date } : defaultDayConfig(date);
	});
}

export interface DateRangeLike {
	check_in_date: string;
	check_out_date: string;
}

// Relevance is overlap of [check_in_date, check_out_date] with [tripStart, tripEnd], not containment — see ADR-15.
export function isStayRelevantToRange(
	stay: DateRangeLike,
	tripStart: string,
	tripEnd: string
): boolean {
	return stay.check_in_date <= tripEnd && stay.check_out_date >= tripStart;
}

export function pruneAccommodationsToRange<T extends DateRangeLike>(
	accommodations: T[],
	tripStart: string,
	tripEnd: string
): T[] {
	return accommodations.filter((entry) => isStayRelevantToRange(entry, tripStart, tripEnd));
}

export function pruneTransfersToRange(
	transfers: Map<string, TransferBlock>,
	dayDates: string[]
): Map<string, TransferBlock> {
	const validDates = new Set(dayDates);
	return new Map([...transfers].filter(([date]) => validDates.has(date)));
}

export interface DayAnchors<T> {
	start: T | null;
	end: T | null;
}

// Mirrors resolve_day_anchors in src/accommodations/resolver.py, keyed by localKey since AccommodationStay has no id.
export function resolveDayAnchors<T extends DateRangeLike & { localKey: string }>(
	dates: string[],
	accommodations: T[]
): DayAnchors<T>[] {
	return dates.map((day) => ({
		start: accommodations.find((a) => a.check_in_date < day && day <= a.check_out_date) ?? null,
		end: accommodations.find((a) => a.check_in_date <= day && day < a.check_out_date) ?? null
	}));
}

// Mirrors _is_transition_day in src/optimizer/solver/models.py.
export function isTransitionDay<T extends { localKey: string }>(anchors: DayAnchors<T>): boolean {
	return (
		anchors.start !== null &&
		anchors.end !== null &&
		anchors.start.localKey !== anchors.end.localKey
	);
}
