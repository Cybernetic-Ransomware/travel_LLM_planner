import * as m from '$lib/paraglide/messages.js';
import type { SkippedPlace } from '$lib/types/index.js';

export type SkipReason = SkippedPlace['reason'];

const REASON_MESSAGES: Record<SkipReason, () => string> = {
	DROPPED_LOW_PRIORITY: m.skip_reason_dropped_low_priority,
	TIME_WINDOW_INFEASIBLE: m.skip_reason_time_window_infeasible,
	NO_COORDINATES: m.skip_reason_no_coordinates,
	NO_MATRIX_ENTRY: m.skip_reason_no_matrix_entry,
	MATRIX_INCOMPLETE: m.skip_reason_matrix_incomplete
};

export function skipReasonMessage(reason: string): string {
	const message = (REASON_MESSAGES as Record<string, () => string>)[reason];
	return message ? message() : m.skip_reason_unknown();
}

export function isLowPriorityDrop(reason: string): boolean {
	return reason === 'DROPPED_LOW_PRIORITY';
}
