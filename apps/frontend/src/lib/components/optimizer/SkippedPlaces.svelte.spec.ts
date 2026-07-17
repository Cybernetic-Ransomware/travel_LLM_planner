import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
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

	it('shows mark-as-must-see action for low-priority drops', async () => {
		const onmarkmustsee = vi.fn();
		const { getByRole } = render(SkippedPlaces, {
			props: {
				skipped: [mockSkipped('p1', 'DROPPED_LOW_PRIORITY')],
				onmarkmustsee
			}
		});

		await expect
			.element(getByRole('button', { name: m.skipped_action_mark_must_see() }))
			.toBeVisible();
	});

	it.each(
		REASON_CASES.filter(([reason]) => reason !== 'DROPPED_LOW_PRIORITY').map(([reason]) => reason)
	)('hides mark-as-must-see action for %s', (reason) => {
		const { getByRole } = render(SkippedPlaces, {
			props: {
				skipped: [mockSkipped('p1', reason)],
				onmarkmustsee: vi.fn()
			}
		});

		expect(getByRole('button', { name: m.skipped_action_mark_must_see() }).query()).toBeNull();
	});

	it('hides mark-as-must-see action when no callback is provided', () => {
		const { getByRole } = render(SkippedPlaces, {
			props: { skipped: [mockSkipped('p1', 'DROPPED_LOW_PRIORITY')] }
		});

		expect(getByRole('button', { name: m.skipped_action_mark_must_see() }).query()).toBeNull();
	});

	it('calls onmarkmustsee with the place id when clicked', async () => {
		const onmarkmustsee = vi.fn();
		const { getByRole } = render(SkippedPlaces, {
			props: {
				skipped: [mockSkipped('p1', 'DROPPED_LOW_PRIORITY')],
				onmarkmustsee
			}
		});

		await userEvent.click(getByRole('button', { name: m.skipped_action_mark_must_see() }));

		expect(onmarkmustsee).toHaveBeenCalledWith('p1');
	});

	it('hides mark-as-must-see action for a place already in promotedPlaceIds', () => {
		const { getByRole } = render(SkippedPlaces, {
			props: {
				skipped: [mockSkipped('p1', 'DROPPED_LOW_PRIORITY')],
				onmarkmustsee: vi.fn(),
				promotedPlaceIds: new Set(['p1'])
			}
		});

		expect(getByRole('button', { name: m.skipped_action_mark_must_see() }).query()).toBeNull();
	});

	it('disables and shows the updating label for the place currently being promoted', async () => {
		const { getByRole } = render(SkippedPlaces, {
			props: {
				skipped: [mockSkipped('p1', 'DROPPED_LOW_PRIORITY')],
				onmarkmustsee: vi.fn(),
				promotingPlaceId: 'p1'
			}
		});

		const button = getByRole('button', { name: m.optimizer_preference_updating() });
		await expect.element(button).toBeVisible();
		await expect.element(button).toBeDisabled();
	});

	it("leaves other places' buttons enabled while a different place is being promoted", async () => {
		const { getByRole } = render(SkippedPlaces, {
			props: {
				skipped: [
					mockSkipped('p1', 'DROPPED_LOW_PRIORITY'),
					mockSkipped('p2', 'DROPPED_LOW_PRIORITY')
				],
				onmarkmustsee: vi.fn(),
				promotingPlaceId: 'p1'
			}
		});

		await expect
			.element(getByRole('button', { name: m.optimizer_preference_updating() }))
			.toBeVisible();
		const p2Button = getByRole('button', { name: m.skipped_action_mark_must_see() });
		await expect.element(p2Button).toBeVisible();
		await expect.element(p2Button).not.toBeDisabled();
	});
});
