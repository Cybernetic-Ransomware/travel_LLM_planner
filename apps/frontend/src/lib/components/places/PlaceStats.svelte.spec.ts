import { describe, it, expect } from 'vitest';
import { render } from 'vitest-browser-svelte';
import PlaceStats from './PlaceStats.svelte';

describe('PlaceStats', () => {
	it('renders all four metric values', async () => {
		const { getByText } = render(PlaceStats, {
			props: { total: 42, active: 30, enriched: 25, withHours: 18 }
		});

		expect(getByText('42')).toBeTruthy();
		expect(getByText('30')).toBeTruthy();
		expect(getByText('25')).toBeTruthy();
		expect(getByText('18')).toBeTruthy();
	});

	it('renders metric labels in active locale', async () => {
		const { getByText } = render(PlaceStats, {
			props: { total: 0, active: 0, enriched: 0, withHours: 0 }
		});

		// Labels are locale-aware (Polish in test env: pl is base locale)
		expect(getByText('Wszystkie')).toBeTruthy();
		expect(getByText('Aktywne')).toBeTruthy();
		expect(getByText('Wzbogacone')).toBeTruthy();
		expect(getByText('Z godzinami')).toBeTruthy();
	});
});
