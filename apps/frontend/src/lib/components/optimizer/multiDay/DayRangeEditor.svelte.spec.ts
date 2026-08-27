import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import DayRangeEditor from './DayRangeEditor.svelte';
import type { DayConfig } from '$lib/types/index.js';

const initialDays: DayConfig[] = [
	{ date: '2026-03-01', day_start_hour: 9, day_end_hour: 21 },
	{ date: '2026-03-02', day_start_hour: 9, day_end_hour: 21 }
];

describe('DayRangeEditor', () => {
	it('renders one row per day', async () => {
		const { getByTestId } = render(DayRangeEditor, {
			props: { days: initialDays, onchange: vi.fn() }
		});
		expect(getByTestId('day-range-row-0')).toBeTruthy();
		expect(getByTestId('day-range-row-1')).toBeTruthy();
	});

	it('increasing the day count reconciles a longer days array', async () => {
		const onchange = vi.fn();
		const { getByLabelText } = render(DayRangeEditor, { props: { days: initialDays, onchange } });
		const numDaysInput = getByLabelText('Liczba dni');
		await numDaysInput.fill('4');
		expect(onchange).toHaveBeenCalled();
		const lastCall = onchange.mock.calls.at(-1)?.[0] as DayConfig[];
		expect(lastCall).toHaveLength(4);
		expect(lastCall[0].date).toBe('2026-03-01');
	});

	it('switching the end boundary to exact mode shows a live time input, not a reverted hour field', async () => {
		const onchange = vi.fn();
		const { getByTestId, rerender } = render(DayRangeEditor, {
			props: { days: initialDays, onchange }
		});
		const row = getByTestId('day-range-row-0');
		await userEvent.click(row.getByTestId('boundary-mode-exact').nth(1));

		// The DTO write-back must carry a real time, not null — otherwise re-hydrating would revert to hour mode.
		const afterModeSwitch = onchange.mock.calls.at(-1)?.[0] as DayConfig[];
		expect(afterModeSwitch[0].day_end_time).not.toBeNull();

		// Re-render with the persisted DayConfig, as the owning component would after propagating onchange.
		await rerender({ days: afterModeSwitch, onchange });
		await expect.element(row.getByTestId('boundary-value-exact').nth(0)).toBeVisible();
	});

	it('typing an exact end time of 00:00 shows the domain error via pure validation, not an HTML hint', async () => {
		const onchange = vi.fn();
		const { getByTestId, rerender } = render(DayRangeEditor, {
			props: { days: initialDays, onchange }
		});
		const row = getByTestId('day-range-row-0');
		await userEvent.click(row.getByTestId('boundary-mode-exact').nth(1));
		const afterModeSwitch = onchange.mock.calls.at(-1)?.[0] as DayConfig[];
		await rerender({ days: afterModeSwitch, onchange });

		await userEvent.fill(row.getByTestId('boundary-value-exact').nth(0), '00:00');
		const afterTimeEdit = onchange.mock.calls.at(-1)?.[0] as DayConfig[];
		expect(afterTimeEdit[0].day_end_time).toBe('00:00');
		await rerender({ days: afterTimeEdit, onchange });

		await expect
			.element(
				row.getByText(
					'Godzina końcowa nie może być północą — użyj trybu godzinowego z wartością 24.'
				)
			)
			.toBeVisible();
	});

	it('an effective start >= end (typed via exact time) blocks with the range-invalid error', async () => {
		const onchange = vi.fn();
		const { getByTestId, rerender } = render(DayRangeEditor, {
			props: { days: initialDays, onchange }
		});
		const row = getByTestId('day-range-row-0');
		await userEvent.click(row.getByTestId('boundary-mode-exact').nth(1));
		const afterModeSwitch = onchange.mock.calls.at(-1)?.[0] as DayConfig[];
		await rerender({ days: afterModeSwitch, onchange });

		// The day's effective start (hour mode, 09:00) is later than this exact end time.
		await userEvent.fill(row.getByTestId('boundary-value-exact').nth(0), '08:00');
		const afterTimeEdit = onchange.mock.calls.at(-1)?.[0] as DayConfig[];
		expect(afterTimeEdit[0].day_end_time).toBe('08:00');
		await rerender({ days: afterTimeEdit, onchange });

		await expect
			.element(row.getByText('Efektywna godzina końcowa musi być późniejsza niż początkowa.'))
			.toBeVisible();
	});
});
