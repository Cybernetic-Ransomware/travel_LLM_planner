import { describe, it, expect } from 'vitest';
import { render } from 'vitest-browser-svelte';
import SkippedPlaces from './SkippedPlaces.svelte';
import * as m from '$lib/paraglide/messages.js';
import type { SkippedPlace } from '$lib/types/index.js';

const mockSkipped = (id: string, reason: SkippedPlace['reason']): SkippedPlace => ({
	place_id: id,
	name: `Place ${id}`,
	reason
});

const REASON_CASES: [SkippedPlace['reason'], () => string][] = [
	['DROPPED_LOW_PRIORITY', m.skip_reason_dropped_low_priority],
	['TIME_WINDOW_INFEASIBLE', m.skip_reason_time_window_infeasible],
	['NO_COORDINATES', m.skip_reason_no_coordinates],
	['NO_MATRIX_ENTRY', m.skip_reason_no_matrix_entry],
	['MATRIX_INCOMPLETE', m.skip_reason_matrix_incomplete]
];

describe('SkippedPlaces', () => {
	it.each(REASON_CASES)('renders translated message for %s', async (reason, message) => {
		const { getByText } = render(SkippedPlaces, {
			props: { skipped: [mockSkipped('p1', reason)] }
		});
		await expect.element(getByText(message())).toBeVisible();
	});

	it('never shows raw reason codes', () => {
		const skipped = REASON_CASES.map(([reason], i) => mockSkipped(`p${i}`, reason));
		const { container } = render(SkippedPlaces, { props: { skipped } });
		const text = container.textContent ?? '';
		for (const [reason] of REASON_CASES) {
			expect(text).not.toContain(reason);
		}
	});

	it('shows the low-priority tip when a place was dropped for priority', async () => {
		const { getByText } = render(SkippedPlaces, {
			props: {
				skipped: [mockSkipped('p1', 'DROPPED_LOW_PRIORITY'), mockSkipped('p2', 'NO_COORDINATES')]
			}
		});
		await expect.element(getByText(m.skip_tip_low_priority())).toBeVisible();
	});

	it('hides the tip when no place was dropped for priority', () => {
		const { getByText } = render(SkippedPlaces, {
			props: { skipped: [mockSkipped('p1', 'TIME_WINDOW_INFEASIBLE')] }
		});
		expect(getByText(m.skip_tip_low_priority()).query()).toBeNull();
	});

	it('renders nothing when there are no skipped places', () => {
		const { container } = render(SkippedPlaces, { props: { skipped: [] } });
		expect((container.textContent ?? '').trim()).toBe('');
	});
});
