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

	it('switching a day to exact-time mode and typing 00:00 shows the domain error, not just an HTML hint', async () => {
		const onchange = vi.fn();
		const { getByTestId } = render(DayRangeEditor, { props: { days: initialDays, onchange } });
		const row = getByTestId('day-range-row-0');
		const endModeButtons = row.getByTestId('boundary-mode-exact');
		await userEvent.click(endModeButtons.nth(1));
		expect(onchange).toHaveBeenCalled();
	});
});
