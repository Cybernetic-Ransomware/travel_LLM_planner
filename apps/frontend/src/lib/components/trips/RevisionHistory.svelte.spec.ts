import { describe, it, expect } from 'vitest';
import { render } from 'vitest-browser-svelte';
import RevisionHistory from './RevisionHistory.svelte';
import type { TripRevisionSummaryOut } from '$lib/types/index.js';

function rev(over: Partial<TripRevisionSummaryOut>): TripRevisionSummaryOut {
	return {
		revision: 0,
		source: 'CREATED',
		summary: 'Trip created',
		restored_from_revision: null,
		schema_version: 1,
		snapshot_hash: 'h',
		recorded_at: '2026-08-01T10:00:00Z',
		...over
	};
}

const revisions = [
	rev({ revision: 2, source: 'REVERT', summary: 'Restored revision 0', restored_from_revision: 0 }),
	rev({ revision: 1, source: 'MANUAL', summary: 'Manual update — SINGLE_DAY, 3 places' }),
	rev({ revision: 0, source: 'CREATED', summary: 'Trip created' })
];

describe('RevisionHistory', () => {
	it('renders each revision with its source label and recorded time', async () => {
		const { getByText } = render(RevisionHistory, {
			props: { tripId: 'abc', currentRevision: 2, revisions }
		});
		expect(getByText('#2').query()).toBeTruthy();
		expect(getByText('przywrócenie').query()).toBeTruthy(); // REVERT source label (pl)
		expect(getByText('edycja ręczna').query()).toBeTruthy(); // MANUAL
		expect(getByText('utworzenie').query()).toBeTruthy(); // CREATED
	});

	it('marks the current revision and shows revert provenance', async () => {
		const { getByText } = render(RevisionHistory, {
			props: { tripId: 'abc', currentRevision: 2, revisions }
		});
		expect(getByText('bieżąca').query()).toBeTruthy();
		expect(getByText(/z wersji 0/).query()).toBeTruthy();
	});

	it('hides Restore on the current revision but shows it on older ones', async () => {
		const { getByTestId } = render(RevisionHistory, {
			props: { tripId: 'abc', currentRevision: 2, revisions }
		});
		expect(getByTestId('restore-2').query()).toBeNull();
		expect(getByTestId('restore-1').query()).toBeTruthy();
		expect(getByTestId('restore-0').query()).toBeTruthy();
	});
});
