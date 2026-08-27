import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import TransferEditor from './TransferEditor.svelte';
import type { AccommodationDraft } from './accommodationDraft.js';
import type { TransferBlock } from '$lib/types/index.js';

function stayDraft(localKey: string, checkIn: string, checkOut: string): AccommodationDraft {
	return {
		localKey,
		name: `Hotel ${localKey}`,
		lat: 50,
		lng: 20,
		check_in_date: checkIn,
		check_out_date: checkOut,
		check_in_from: null,
		check_out_by: null
	};
}

const dayDates = ['2026-03-01', '2026-03-02', '2026-03-03'];
const transitionAccommodations: AccommodationDraft[] = [
	stayDraft('A', '2026-02-28', '2026-03-02'),
	stayDraft('B', '2026-03-02', '2026-03-04')
];

describe('TransferEditor', () => {
	it('shows no transfer rows when there is no transition day', async () => {
		const { getByText, getByTestId } = render(TransferEditor, {
			props: { transfers: new Map(), accommodations: [], dayDates, onchange: vi.fn() }
		});
		expect(getByText(/Nie wykryto jeszcze dni przejściowych/)).toBeTruthy();
		expect(getByTestId('transfer-row-2026-03-02').query()).toBeNull();
	});

	it('detects the transition day from accommodations and renders one row', async () => {
		const { getByTestId } = render(TransferEditor, {
			props: {
				transfers: new Map(),
				accommodations: transitionAccommodations,
				dayDates,
				onchange: vi.fn()
			}
		});
		expect(getByTestId('transfer-row-2026-03-02')).toBeTruthy();
	});

	it('leaves the transfer unchecked by default (no transfer is a legal, non-error state)', async () => {
		const { getByTestId } = render(TransferEditor, {
			props: {
				transfers: new Map(),
				accommodations: transitionAccommodations,
				dayDates,
				onchange: vi.fn()
			}
		});
		const checkbox = getByTestId('transfer-row-2026-03-02')
			.element()
			.querySelector('input[type="checkbox"]');
		expect((checkbox as HTMLInputElement).checked).toBe(false);
	});

	it('checking the box creates a TransferBlock for that date', async () => {
		const onchange = vi.fn();
		const { getByTestId } = render(TransferEditor, {
			props: { transfers: new Map(), accommodations: transitionAccommodations, dayDates, onchange }
		});
		const row = getByTestId('transfer-row-2026-03-02');
		await userEvent.click(row.element().querySelector('input[type="checkbox"]')!);
		const next = onchange.mock.calls[0][0] as Map<string, TransferBlock>;
		expect(next.get('2026-03-02')).toBeTruthy();
	});

	it('flags an invalid arrival <= departure pair', async () => {
		const transfers = new Map([
			['2026-03-02', { date: '2026-03-02', departure_time: '11:00', arrival_time: '10:00' }]
		]);
		const { getByText } = render(TransferEditor, {
			props: { transfers, accommodations: transitionAccommodations, dayDates, onchange: vi.fn() }
		});
		expect(getByText('Przyjazd musi być późniejszy niż odjazd.')).toBeTruthy();
	});

	it('unchecking removes the TransferBlock for that date', async () => {
		const onchange = vi.fn();
		const transfers = new Map([
			['2026-03-02', { date: '2026-03-02', departure_time: '10:00', arrival_time: '11:00' }]
		]);
		const { getByTestId } = render(TransferEditor, {
			props: { transfers, accommodations: transitionAccommodations, dayDates, onchange }
		});
		const row = getByTestId('transfer-row-2026-03-02');
		await userEvent.click(row.element().querySelector('input[type="checkbox"]')!);
		const next = onchange.mock.calls[0][0] as Map<string, TransferBlock>;
		expect(next.has('2026-03-02')).toBe(false);
	});
});
