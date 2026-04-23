import { BACKEND_URL } from '$env/static/private';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ fetch }) => {
	try {
		const res = await fetch(`${BACKEND_URL}/api/v1/core/orchestrator/status`);
		if (!res.ok) return { orchestratorReady: false };
		const data = await res.json();
		return { orchestratorReady: data.ready ?? false };
	} catch {
		return { orchestratorReady: false };
	}
};
