import { BACKEND_URL } from '$env/static/private';
import type { RequestHandler } from './$types';

// The backend healthcheck lives at its root path, outside the /api/v1 prefix
// handled by the generic proxy route, so it needs a dedicated pass-through.
export const GET: RequestHandler = async () => {
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), 10_000);

	try {
		const upstream = await fetch(`${BACKEND_URL}/`, { signal: controller.signal });

		clearTimeout(timer);

		return new Response(upstream.body, {
			status: upstream.status,
			headers: { 'Content-Type': 'application/json' }
		});
	} catch (err) {
		clearTimeout(timer);

		if ((err as Error).name === 'AbortError') {
			return new Response(JSON.stringify({ detail: 'Gateway timeout' }), {
				status: 504,
				headers: { 'Content-Type': 'application/json' }
			});
		}

		return new Response(JSON.stringify({ detail: 'Bad gateway' }), {
			status: 502,
			headers: { 'Content-Type': 'application/json' }
		});
	}
};
