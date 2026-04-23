import { describe, it, expect, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { userEvent } from 'vitest/browser';
import ToolProposal from './ToolProposal.svelte';
import type { ToolProposal as ToolProposalType } from '$lib/types/index.js';

const mockProposal: ToolProposalType = {
	tool: 'import_list',
	args: { url: 'https://www.google.com/maps/saved', limit: 50 }
};

describe('ToolProposal', () => {
	it('renders tool name', async () => {
		const { getByText } = render(ToolProposal, {
			props: { proposal: mockProposal, onconfirm: vi.fn(), oncancel: vi.fn() }
		});
		expect(getByText('import_list')).toBeTruthy();
	});

	it('renders confirm and cancel buttons', async () => {
		const { getByTestId } = render(ToolProposal, {
			props: { proposal: mockProposal, onconfirm: vi.fn(), oncancel: vi.fn() }
		});
		expect(getByTestId('proposal-confirm')).toBeTruthy();
		expect(getByTestId('proposal-cancel')).toBeTruthy();
	});

	it('calls onconfirm when confirm is clicked', async () => {
		const onconfirm = vi.fn();
		const { getByTestId } = render(ToolProposal, {
			props: { proposal: mockProposal, onconfirm, oncancel: vi.fn() }
		});
		await userEvent.click(getByTestId('proposal-confirm'));
		expect(onconfirm).toHaveBeenCalledOnce();
	});

	it('calls oncancel when cancel is clicked', async () => {
		const oncancel = vi.fn();
		const { getByTestId } = render(ToolProposal, {
			props: { proposal: mockProposal, onconfirm: vi.fn(), oncancel }
		});
		await userEvent.click(getByTestId('proposal-cancel'));
		expect(oncancel).toHaveBeenCalledOnce();
	});
});
