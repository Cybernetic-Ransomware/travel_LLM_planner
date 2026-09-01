/** Human-readable one-liners for the operations inside an edit_multi_day_trip proposal. */

type Op = Record<string, unknown>;

function hour(value: unknown): string | null {
	return typeof value === 'number' ? `${String(value).padStart(2, '0')}:00` : null;
}

function windowText(from: unknown, to: unknown): string {
	const a = hour(from);
	const b = hour(to);
	if (a && b) return `${a}–${b}`;
	if (a) return `from ${a}`;
	if (b) return `until ${b}`;
	return '';
}

export function formatTripEditOperation(op: Op): string {
	switch (op.op) {
		case 'set_place_auto':
			return `Let place ${op.place_id} be scheduled on any day`;
		case 'set_place_pinned': {
			const w = windowText(op.preferred_hour_from, op.preferred_hour_to);
			return `Pin place ${op.place_id} to day ${op.day_index}${w ? ` (${w})` : ''}`;
		}
		case 'set_place_flexible': {
			const days = Array.isArray(op.slots)
				? (op.slots as Op[]).map((s) => s.day_index).join(', ')
				: '';
			return `Make place ${op.place_id} flexible across days ${days}`;
		}
		case 'remove_place':
			return `Remove place ${op.place_id} from the trip`;
		case 'update_day_window': {
			const parts: string[] = [];
			const w = windowText(op.day_start_hour, op.day_end_hour);
			if (w) parts.push(`window ${w}`);
			if (op.day_start_time) parts.push(`start ${op.day_start_time}`);
			if (op.day_end_time) parts.push(`end ${op.day_end_time}`);
			if (op.clear_start_time) parts.push('clear start time');
			if (op.clear_end_time) parts.push('clear end time');
			return `Day ${op.day_index}: ${parts.join(', ') || 'no change'}`;
		}
		case 'set_transport_mode':
			return `Change transport mode to ${op.mode}`;
		case 'add_transfer':
			return `Add transfer on ${op.date}: depart ${op.departure_time}, arrive ${op.arrival_time}`;
		case 'update_transfer':
			return `Update the transfer on ${op.date}`;
		case 'remove_transfer':
			return `Remove the transfer on ${op.date}`;
		case 'add_accommodation':
			return `Add stay "${op.name}" ${op.check_in_date} → ${op.check_out_date}`;
		case 'update_accommodation':
			return `Update stay ${op.stay_index}`;
		case 'remove_accommodation':
			return `Remove stay ${op.stay_index}`;
		default:
			return JSON.stringify(op);
	}
}

export function formatTripEditBatch(args: Record<string, unknown>): string[] {
	const ops = Array.isArray(args.operations) ? (args.operations as Op[]) : [];
	return ops.map(formatTripEditOperation);
}

/** Human-readable one-liner for a revert_trip_revision proposal. */
export function formatRevertProposal(args: Record<string, unknown>): string {
	const target = args.target_revision;
	return typeof target === 'number'
		? `Restore this trip to revision ${target}`
		: 'Restore this trip to an earlier revision';
}
