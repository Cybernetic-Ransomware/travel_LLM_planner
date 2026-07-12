import { describe, it, expect } from 'vitest';
import * as m from '$lib/paraglide/messages.js';
import { skipReasonMessage, isLowPriorityDrop, type SkipReason } from './skippedReasons.js';

const ALL_REASONS: SkipReason[] = [
	'DROPPED_LOW_PRIORITY',
	'TIME_WINDOW_INFEASIBLE',
	'NO_COORDINATES',
	'NO_MATRIX_ENTRY',
	'MATRIX_INCOMPLETE'
];

describe('skipReasonMessage', () => {
	it.each(ALL_REASONS)('maps %s to a human-readable message', (reason) => {
		const message = skipReasonMessage(reason);
		expect(message).not.toBe('');
		expect(message).not.toBe(reason);
		expect(message).not.toContain('_');
	});

	it('maps DROPPED_LOW_PRIORITY to its dedicated message', () => {
		expect(skipReasonMessage('DROPPED_LOW_PRIORITY')).toBe(m.skip_reason_dropped_low_priority());
	});

	it('falls back to the generic message for an unknown reason', () => {
		expect(skipReasonMessage('SOME_FUTURE_REASON')).toBe(m.skip_reason_unknown());
	});
});

describe('isLowPriorityDrop', () => {
	it('returns true only for DROPPED_LOW_PRIORITY', () => {
		expect(isLowPriorityDrop('DROPPED_LOW_PRIORITY')).toBe(true);
		for (const reason of ALL_REASONS.filter((r) => r !== 'DROPPED_LOW_PRIORITY')) {
			expect(isLowPriorityDrop(reason)).toBe(false);
		}
	});
});
