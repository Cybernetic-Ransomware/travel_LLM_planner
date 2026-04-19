import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import ImportForm from './ImportForm.svelte';

describe('ImportForm', () => {
	it('renders URL input and submit button', async () => {
		const { getByLabelText, getByTestId } = render(ImportForm, {
			props: { onimport: vi.fn() }
		});

		expect(getByLabelText(/url/i)).toBeTruthy();
		expect(getByTestId('import-submit')).toBeTruthy();
	});

	it('disables submit when URL is empty', async () => {
		const { getByTestId } = render(ImportForm, { props: { onimport: vi.fn() } });
		const button = getByTestId('import-submit').element() as HTMLButtonElement;
		expect(button.disabled).toBe(true);
	});

	it('enables submit when a valid URL is entered', async () => {
		const { getByLabelText, getByTestId } = render(ImportForm, { props: { onimport: vi.fn() } });
		await userEvent.fill(getByLabelText(/url/i), 'https://www.google.com/maps/saved');
		const button = getByTestId('import-submit').element() as HTMLButtonElement;
		expect(button.disabled).toBe(false);
	});

	it('keeps submit disabled for non-http input', async () => {
		const { getByLabelText, getByTestId } = render(ImportForm, { props: { onimport: vi.fn() } });
		await userEvent.fill(getByLabelText(/url/i), 'not-a-url');
		const button = getByTestId('import-submit').element() as HTMLButtonElement;
		expect(button.disabled).toBe(true);
	});
});
