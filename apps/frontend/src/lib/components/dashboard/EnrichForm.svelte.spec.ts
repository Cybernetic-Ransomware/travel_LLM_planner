import { describe, it, expect } from 'vitest';
import { render } from 'vitest-browser-svelte';
import EnrichForm from './EnrichForm.svelte';

describe('EnrichForm', () => {
	it('renders slider and submit button', async () => {
		const { getByRole, getByTestId } = render(EnrichForm, { props: {} });
		expect(getByRole('slider')).toBeTruthy();
		expect(getByTestId('enrich-submit')).toBeTruthy();
	});

	it('slider defaults to 10', async () => {
		const { getByRole } = render(EnrichForm, { props: {} });
		const slider = getByRole('slider').element() as HTMLInputElement;
		expect(slider.value).toBe('10');
	});

	it('submit button is enabled by default', async () => {
		const { getByTestId } = render(EnrichForm, { props: {} });
		const button = getByTestId('enrich-submit').element() as HTMLButtonElement;
		expect(button.disabled).toBe(false);
	});
});
