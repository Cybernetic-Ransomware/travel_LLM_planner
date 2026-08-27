import type { TransferBlock } from '$lib/types/index.js';

// Mirrors validate_same_day_arrival_after_departure in src/transfers/models.py.
export function isTransferBlockValid(transfer: TransferBlock): boolean {
	return (
		transfer.departure_time.length > 0 &&
		transfer.arrival_time.length > 0 &&
		transfer.arrival_time > transfer.departure_time
	);
}

export function allTransfersValid(transfers: Map<string, TransferBlock>): boolean {
	return [...transfers.values()].every(isTransferBlockValid);
}
