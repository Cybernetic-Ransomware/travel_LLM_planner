import { BACKEND_URL } from '$env/static/private';
import type { RequestHandler } from './$types';

const TIMEOUTS: Record<string, number> = {
	'core/gmaps/import': 120_000,
	'core/gmaps/enrich': 120_000,
	'core/orchestrator/chat': 60_000
};

export const fallback: RequestHandler = async ({ params, request }) => {
	const path = (params as { path: string }).path;
	const sourceUrl = new URL(request.url);
	const targetUrl = `${BACKEND_URL}/api/v1/${path}${sourceUrl.search}`;

	const timeout = TIMEOUTS[path] ?? 30_000;
	const controller = new AbortController();
	const timer = setTimeout(() => controller.abort(), timeout);

	const forwardHeaders = new Headers(request.headers);
	forwardHeaders.delete('host');

	try {
		const upstream = await fetch(targetUrl, {
			method: request.method,
			headers: forwardHeaders,
			body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
			signal: controller.signal,
			// @ts-expect-error — duplex is required for streaming request bodies in Node 18+
			duplex: 'half'
		});

		clearTimeout(timer);

		return new Response(upstream.body, {
			status: upstream.status,
			headers: upstream.headers
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
