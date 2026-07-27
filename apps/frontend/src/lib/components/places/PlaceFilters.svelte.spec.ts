import { describe, it, expect } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import PlaceFilters from './PlaceFilters.svelte';

describe('PlaceFilters', () => {
	it('selecting "Active only" sets the skipped select to the new value', async () => {
		const { getByRole } = render(PlaceFilters, {
			props: { filterSkipped: true, filterListName: null, listNames: [] }
		});

		const skippedSelect = getByRole('combobox').first();
		await userEvent.selectOptions(skippedSelect, getByRole('option', { name: 'Active only' }));

		await expect.element(skippedSelect).toHaveValue('false');
	});

	it('does not snap the skipped select back to the previous value after the user changes it', async () => {
		const { getByRole } = render(PlaceFilters, {
			props: { filterSkipped: true, filterListName: null, listNames: [] }
		});

		const skippedSelect = getByRole('combobox').first();
		await expect.element(skippedSelect).toHaveValue('true');

		await userEvent.selectOptions(skippedSelect, getByRole('option', { name: 'Active only' }));

		await expect.element(skippedSelect).toHaveValue('false');
		await expect.element(skippedSelect).not.toHaveValue('true');
	});

	it('resets the skipped select to "All places" when filterSkipped becomes null externally', async () => {
		const { getByRole, rerender } = render(PlaceFilters, {
			props: { filterSkipped: true, filterListName: null, listNames: [] }
		});

		const skippedSelect = getByRole('combobox').first();
		await expect.element(skippedSelect).toHaveValue('true');

		await rerender({ filterSkipped: null, filterListName: null, listNames: [] });

		await expect.element(skippedSelect).toHaveValue('');
	});

	it('selecting a list name sets the list select to the new value', async () => {
		const { getByRole } = render(PlaceFilters, {
			props: { filterSkipped: null, filterListName: null, listNames: ['Test_krakow'] }
		});

		const listSelect = getByRole('combobox').nth(1);
		await userEvent.selectOptions(listSelect, getByRole('option', { name: 'Test_krakow' }));

		await expect.element(listSelect).toHaveValue('Test_krakow');
	});

	it('resets the list select to "All lists" when filterListName becomes null externally', async () => {
		const { getByRole, rerender } = render(PlaceFilters, {
			props: {
				filterSkipped: null,
				filterListName: 'Test_krakow',
				listNames: ['Test_krakow']
			}
		});

		const listSelect = getByRole('combobox').nth(1);
		await expect.element(listSelect).toHaveValue('Test_krakow');

		await rerender({
			filterSkipped: null,
			filterListName: null,
			listNames: ['Test_krakow']
		});

		await expect.element(listSelect).toHaveValue('');
	});
});
