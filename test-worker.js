// The test site's files, answering range requests. To jump into an audio file (a card 31 minutes into a listen), a
// browser asks for just the part from there on; Workers' own file serving ignores that and sends the whole file, so on
// the test site every jump played the listen from its start. GitHub Pages, the live site, handles ranges itself.
// The file comes in whole (read by the runtime, not this script, and with no length given there's no other way to know
// its size) and the part asked for goes out as a view onto it, copying nothing: cheap enough for one tester.
export default {
	async fetch(request, env) {
		const range = /^bytes=(\d+)-(\d*)$/.exec(request.headers.get('Range') || '');
		const res = await env.ASSETS.fetch(request);
		if (!range || res.status !== 200 || !new URL(request.url).pathname.endsWith('.m4a')) return res;
		const buf = await res.arrayBuffer();
		const size = buf.byteLength;
		const start = Number(range[1]);
		const end = Math.min(range[2] ? Number(range[2]) : size - 1, size - 1);
		const headers = new Headers(res.headers);
		headers.set('Accept-Ranges', 'bytes');
		if (start > end) {
			headers.set('Content-Range', `bytes */${size}`);
			return new Response(null, {status: 416, headers});
		}
		headers.set('Content-Range', `bytes ${start}-${end}/${size}`);
		headers.set('Content-Length', String(end - start + 1));
		return new Response(new Uint8Array(buf, start, end - start + 1), {status: 206, headers});
	},
};
