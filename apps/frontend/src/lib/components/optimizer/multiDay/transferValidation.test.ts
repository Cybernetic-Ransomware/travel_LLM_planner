import { describe, it, expect } from 'vitest';
import { isTransferBlockValid, allTransfersValid } from './transferValidation.js';
import type { TransferBlock } from '$lib/types/index.js';

function transfer(departure: string, arrival: string): TransferBlock {
	return { date: '2026-03-02', departure_time: departure, arrival_time: arrival };
}

describe('isTransferBlockValid', () => {
	it('accepts arrival after departure', () => {
		expect(isTransferBlockValid(transfer('10:00', '11:00'))).toBe(true);
	});

	it('rejects arrival equal to departure', () => {
		expect(isTransferBlockValid(transfer('10:00', '10:00'))).toBe(false);
	});

	it('rejects arrival before departure', () => {
		expect(isTransferBlockValid(transfer('11:00', '10:00'))).toBe(false);
	});

	it('rejects an incomplete (empty) departure time', () => {
		expect(isTransferBlockValid(transfer('', '11:00'))).toBe(false);
	});

	it('rejects an incomplete (empty) arrival time', () => {
		expect(isTransferBlockValid(transfer('10:00', ''))).toBe(false);
	});
});

describe('allTransfersValid', () => {
	it('is true for an empty map', () => {
		expect(allTransfersValid(new Map())).toBe(true);
	});

	it('is true when every transfer is valid', () => {
		const transfers = new Map([
			['2026-03-02', transfer('10:00', '11:00')],
			['2026-03-05', transfer('09:00', '09:30')]
		]);
		expect(allTransfersValid(transfers)).toBe(true);
	});

	it('is false when any transfer is invalid', () => {
		const transfers = new Map([
			['2026-03-02', transfer('10:00', '11:00')],
			['2026-03-05', transfer('09:00', '')]
		]);
		expect(allTransfersValid(transfers)).toBe(false);
	});
});
