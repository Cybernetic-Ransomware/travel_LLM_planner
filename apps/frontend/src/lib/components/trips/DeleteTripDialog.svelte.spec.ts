import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import DeleteTripDialog from './DeleteTripDialog.svelte';

describe('DeleteTripDialog', () => {
	it('renders trip name in the confirm message', async () => {
		const { getByText } = render(DeleteTripDialog, {
			props: { open: true, tripName: 'Weekend in Kraków' }
		});
		expect(
			getByText(
				'Czy na pewno chcesz usunąć trasę "Weekend in Kraków"? Tej operacji nie można cofnąć.'
			)
		).toBeTruthy();
	});

	it('renders nothing when closed', async () => {
		const { getByText } = render(DeleteTripDialog, {
			props: { open: false, tripName: 'Weekend in Kraków' }
		});
		expect(getByText('Usuwanie trasy').query()).toBeNull();
	});

	it('confirm button fires onconfirm', async () => {
		const onconfirm = vi.fn();
		const { getByRole } = render(DeleteTripDialog, {
			props: { open: true, tripName: 'Weekend in Kraków', onconfirm }
		});
		await userEvent.click(getByRole('button', { name: 'Usuń', exact: true }));
		expect(onconfirm).toHaveBeenCalledOnce();
	});

	it('cancel button closes the dialog', async () => {
		const { getByRole, getByText } = render(DeleteTripDialog, {
			props: { open: true, tripName: 'Weekend in Kraków' }
		});
		await userEvent.click(getByRole('button', { name: 'Anuluj' }));
		expect(getByText('Usuwanie trasy').query()).toBeNull();
	});

	it('loading disables the confirm button', async () => {
		const { getByRole } = render(DeleteTripDialog, {
			props: { open: true, tripName: 'Weekend in Kraków', loading: true }
		});
		const btn = getByRole('button', { name: 'Usuń', exact: true }).element() as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
	});

	it('loading disables the cancel button', async () => {
		const { getByRole } = render(DeleteTripDialog, {
			props: { open: true, tripName: 'Weekend in Kraków', loading: true }
		});
		const btn = getByRole('button', { name: 'Anuluj' }).element() as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
	});
});
