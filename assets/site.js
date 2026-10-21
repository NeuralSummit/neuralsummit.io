// Each page's own behaviour (the contents, the tabs, folding) is a setup run when the page loads, and again whenever
// another page is swapped in (at the end); what it adds to the window or document goes with its page, through
// the signal it's given. The rest (the shapes, the glow, the logo and its sound) runs once and stays.
const pageSetups = [];
const onPage = (setup) => pageSetups.push(setup);
const on = (signal, target, type, fn, opts = {}) => target.addEventListener(type, fn, {...opts, signal});

// Faint outlines drifting behind the page, as in the videos (remotion/src/ui.tsx's Background): seeded, so they
// start in the same places every visit. A moving mouse nudges nearby ones away (not over the text cards, and
// not on touch screens); they ease back once it stops. With reduced motion they stay put.
(() => {
	const svg = document.querySelector('.shapes');
	if (!svg) return;
	const NS = 'http://www.w3.org/2000/svg';
	const COLOURS = ['#f0883e', '#4ea1ff', '#8d96a3'];
	const KINDS = ['triangle', 'rect', 'square', 'circle', 'line'];
	const REACH = 220; // px around the pointer that shapes feel
	const PUSH = 700; // px/s² at the pointer, fading to 0 at REACH
	const SPRING = 2.2; // pull back towards the drift path, per s²
	const DAMP = 2.6; // so they glide back without wobbling
	const MAX = 60; // px a shape can be pushed off its path
	const QUIET = 0.12; // s after the last move that the pointer stops pushing
	const BOXES = '.entry, .term, .intro details, .check-line, .peek'; // the text cards: no pushing from over them

	let seed = 7;
	const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
	const sign = () => (rnd() < 0.5 ? -1 : 1);
	const shapes = Array.from({length: 12}, (_, i) => {
		const s = {
			kind: KINDS[i % KINDS.length], x: rnd(), y: rnd(), size: 50 + rnd() * 110,
			vx: sign() * (5 + rnd() * 9), vy: sign() * (3 + rnd() * 6), rot: rnd() * 360, spin: sign() * (2 + rnd() * 5),
			ox: 0, oy: 0, ovx: 0, ovy: 0, // the push: offset from the drift path, and its velocity
		};
		const g = document.createElementNS(NS, 'g');
		g.setAttribute('stroke', COLOURS[Math.floor(rnd() * 3)]);
		g.setAttribute('opacity', (0.07 + rnd() * 0.07).toFixed(3));
		const h = s.size / 2;
		const el = (tag, attrs) => {
			const e = document.createElementNS(NS, tag);
			for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
			g.appendChild(e);
		};
		if (s.kind === 'circle') el('circle', {r: h});
		else if (s.kind === 'square') el('rect', {x: -h, y: -h, width: s.size, height: s.size});
		else if (s.kind === 'rect') el('rect', {x: -h, y: -h * 0.55, width: s.size, height: s.size * 0.55});
		else if (s.kind === 'line') el('line', {x1: -h * 1.3, x2: h * 1.3, y1: 0, y2: 0});
		else el('polygon', {points: `0,${-h} ${h * 0.87},${h / 2} ${-h * 0.87},${h / 2}`});
		svg.appendChild(g);
		return {...s, g};
	});

	const pointer = {x: 0, y: 0, at: -1};
	addEventListener('pointermove', (e) => {
		if (e.pointerType !== 'mouse') return;
		if (e.target instanceof Element && e.target.closest(BOXES)) return void (pointer.at = -1);
		Object.assign(pointer, {x: e.clientX, y: e.clientY, at: performance.now() / 1000});
	}, {passive: true});

	const wrap = (v, lo, hi) => lo + ((((v - lo) % (hi - lo)) + (hi - lo)) % (hi - lo));
	const still = matchMedia('(prefers-reduced-motion: reduce)');
	const start = performance.now() / 1000;
	let last = start;
	const draw = (now) => {
		const t = now - start, dt = Math.min(0.05, now - last);
		last = now;
		const pushing = pointer.at > 0 && now - pointer.at < QUIET;
		const w = innerWidth, hgt = innerHeight;
		for (const s of shapes) {
			const bx = wrap(s.x * w + s.vx * t, -200, w + 200), by = wrap(s.y * hgt + s.vy * t, -200, hgt + 200);
			let ax = -SPRING * s.ox - DAMP * s.ovx, ay = -SPRING * s.oy - DAMP * s.ovy;
			if (pushing) {
				const dx = bx + s.ox - pointer.x, dy = by + s.oy - pointer.y, d = Math.hypot(dx, dy);
				if (d < REACH && d > 0.01) {
					const f = PUSH * (1 - d / REACH) ** 2;
					ax += (dx / d) * f;
					ay += (dy / d) * f;
				}
			}
			s.ovx += ax * dt;
			s.ovy += ay * dt;
			s.ox += s.ovx * dt;
			s.oy += s.ovy * dt;
			const off = Math.hypot(s.ox, s.oy);
			if (off > MAX) {
				s.ox *= MAX / off;
				s.oy *= MAX / off;
			}
			s.g.setAttribute('transform', `translate(${(bx + s.ox).toFixed(1)} ${(by + s.oy).toFixed(1)}) rotate(${(s.rot + s.spin * t).toFixed(1)})`);
		}
	};
	const tick = (ms) => {
		draw(ms / 1000);
		if (!still.matches) requestAnimationFrame(tick);
	};
	draw(start);
	requestAnimationFrame(tick);
	addEventListener('resize', () => draw(performance.now() / 1000));
})();

// The contents highlight the section you're reading: the last one whose start has scrolled past a third of the
// way down the window, or the title above them all.
onPage((signal) => {
	// the title (first) is highlighted until the first section reaches that line
	const links = [...document.querySelectorAll('.toc li a')];
	if (links.length < 2) return;
	const targets = links.map((a) => document.getElementById(a.hash.slice(1)));
	const update = () => {
		const line = innerHeight / 3;
		let i = 0;
		if (document.documentElement.dataset.tab === 'checks') i = -1; // the contents are the transcript's: none lit
		else targets.forEach((el, k) => {
			if (k && el && el.getBoundingClientRect().top <= line) i = k;
		});
		links.forEach((a, k) => a.parentElement.classList.toggle('active', k === i));
		if (i < 0) return;
		// keep the highlighted entry in view when the contents scroll on a short screen
		const box = links[i].closest('.toc');
		const r = links[i].getBoundingClientRect(), b = box.getBoundingClientRect();
		if (box.scrollHeight > box.clientHeight && (r.top < b.top || r.bottom > b.bottom)) box.scrollTop += r.top - b.top - b.height / 2;
	};
	on(signal, window, 'scroll', update, {passive: true});
	on(signal, window, 'resize', update);
	update();
});

// On a phone the contents sit above the title as a list of chips; they fold into one "## contents" line that opens
// them (style.css), and close again once you pick one.
onPage((signal) => {
	const toc = document.querySelector('.toc');
	const label = toc?.querySelector('.label');
	if (!label) return;
	const set = (open) => {
		toc.classList.toggle('open', open);
		label.setAttribute('aria-expanded', String(open));
	};
	label.addEventListener('click', () => set(!toc.classList.contains('open')), {signal});
	label.addEventListener('keydown', (ev) => (ev.key === 'Enter' || ev.key === ' ') && (ev.preventDefault(), set(!toc.classList.contains('open'))), {signal});
	toc.querySelector('ol').addEventListener('click', (ev) => ev.target.closest('a') && set(false), {signal});
});

// A neon glow around selected text, in the colour of whose words they are. The selection itself stays the browser's
// (a solid fill, in style.css); this draws only the glow, as box-shadows on empty boxes laid over each selected line,
// so nothing covers the text.
(() => {
	const layer = document.createElement('div');
	layer.className = 'glow-layer';
	document.body.appendChild(layer);
	const colour = (node) => {
		const card = (node.nodeType === 1 ? node : node.parentElement)?.closest('.entry');
		return card?.classList.contains('claude') ? 'claude' : card?.classList.contains('gemini') ? 'gemini' : 'neutral';
	};
	const draw = () => {
		layer.replaceChildren();
		const sel = getSelection();
		if (!sel.rangeCount || sel.isCollapsed) return;
		const range = sel.getRangeAt(0);
		const root = range.commonAncestorContainer.nodeType === 1 ? range.commonAncestorContainer : range.commonAncestorContainer.parentNode;
		// only text that's on screen: a closed <details> still reports where its hidden lines would be
		const shown = (n) => {
			const el = n.parentElement;
			if (!el || (el.checkVisibility && !el.checkVisibility({contentVisibilityAuto: true, visibilityProperty: true}))) return false;
			const shut = el.closest('details:not([open])');
			return !shut || !!el.closest('summary');
		};
		const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {acceptNode: (n) => (range.intersectsNode(n) && n.data.trim() && shown(n) ? 1 : 2)});
		// pieces that touch on a line become one box (an italic word is its own text node, and its own glow would tint
		// its neighbours); pieces with a gap between them (a header's spaced-out parts, a dot) stay apart, or the
		// glow would frame the unselected gap
		// what of each piece is actually showing: an element that clips its overflow (a fact-check marker's line,
		// cut off with "…") hides the rest, which still reports where it would be
		const clips = new Map();
		const clipOf = (el) => {
			if (!clips.has(el)) {
				let box = el.parentElement && el.parentElement !== document.body ? clipOf(el.parentElement) : null;
				const css = getComputedStyle(el);
				if (css.overflowX !== 'visible' || css.overflowY !== 'visible') {
					const r = el.getBoundingClientRect();
					box = box ? {left: Math.max(box.left, r.left), right: Math.min(box.right, r.right), top: Math.max(box.top, r.top), bottom: Math.min(box.bottom, r.bottom)} : r;
				}
				clips.set(el, box);
			}
			return clips.get(el);
		};
		const lines = [];
		let nodes = 0;
		for (let n = walk.nextNode(); n && nodes < 2000; n = walk.nextNode(), nodes++) {
			const part = document.createRange();
			part.selectNodeContents(n);
			if (n === range.startContainer) part.setStart(n, range.startOffset);
			if (n === range.endContainer) part.setEnd(n, range.endOffset);
			const kind = colour(n);
			const clip = clipOf(n.parentElement);
			for (const whole of part.getClientRects()) {
				const r = clip ? {left: Math.max(whole.left, clip.left), right: Math.min(whole.right, clip.right), top: Math.max(whole.top, clip.top), bottom: Math.min(whole.bottom, clip.bottom)} : whole;
				r.height = r.bottom - r.top;
				if (r.right - r.left < 1 || r.height < 1) continue;
				const mid = r.top + r.height / 2;
				const line = lines.find((l) => l.kind === kind && Math.abs((l.top + l.bottom) / 2 - mid) < r.height / 3 &&
					r.left <= l.right + 2 && r.right >= l.left - 2);
				if (line) {
					line.left = Math.min(line.left, r.left);
					line.right = Math.max(line.right, r.right);
					line.top = Math.min(line.top, r.top);
					line.bottom = Math.max(line.bottom, r.bottom);
				} else lines.push({kind, left: r.left, right: r.right, top: r.top, bottom: r.bottom});
			}
		}
		for (const l of lines) {
			const box = document.createElement('div');
			box.className = `glow-box ${l.kind}`;
			Object.assign(box.style, {left: `${l.left}px`, top: `${l.top}px`, width: `${l.right - l.left}px`, height: `${l.bottom - l.top}px`});
			layer.appendChild(box);
		}
	};
	let queued = false;
	const soon = () => {
		if (queued) return;
		queued = true;
		requestAnimationFrame(() => {
			queued = false;
			draw();
		});
	};
	document.addEventListener('selectionchange', soon);
	addEventListener('scroll', soon, {passive: true});
	addEventListener('resize', soon);
})();

// Mousing over the channel logo replays the video's sting (remotion/src/Sting.tsx): the two halves start apart and
// spiral in like water down a drain, faster as they close, then lock with a burst of colour split.
(() => {
	const brand = document.querySelector('.brand');
	const svg = brand?.querySelector('svg.logo');
	if (!svg || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
	const SWIRL = 0.65; // s until the halves lock (quicker than the video's 1 s: it's a hover, not an intro)
	const TILT = -35, SPIN = 540, SPREAD = 300; // degrees at rest, degrees turned on the way in, logo units apart at the start
	const halves = (who) => svg.querySelectorAll(`[data-half="${who}"]`);
	const shifts = svg.querySelectorAll('[data-shift]');
	const lock = svg.querySelector('.lock');
	// The video's zap as the halves lock (sfx/zap.wav, embedded by build_site.py as window.ZAP so it also works
	// opened from disk). Web Audio, decoded ahead: an <audio> element took a noticeable moment to start.
	// Browsers only let a page make sound once the visitor has clicked, tapped or typed; Chrome also counts a click
	// on the page that led here (same site). So it's set up as the page loads, and starts running as soon as it's
	// allowed: straight away after such a click, or on the first click on this page. Hovers before that are silent.
	const AHEAD = 0.04;
	let audio = null, buffer = null, zapped = false;
	if (window.ZAP && window.AudioContext) {
		audio = new AudioContext();
		// a signal far too quiet to hear (about -84 dB) keeps the sound output awake: an idle device, a Bluetooth
		// headset especially, sleeps on exact silence and swallows the start of the next sound as it wakes
		const noise = audio.createBuffer(1, audio.sampleRate, audio.sampleRate);
		const ch = noise.getChannelData(0);
		for (let i = 0; i < ch.length; i++) ch[i] = (Math.random() * 2 - 1) * 6e-5;
		const hum = audio.createBufferSource();
		hum.buffer = noise;
		hum.loop = true;
		hum.connect(audio.destination);
		hum.start();
		const bytes = Uint8Array.from(atob(window.ZAP), (c) => c.charCodeAt(0));
		audio.decodeAudioData(bytes.buffer).then((b) => (buffer = b), () => {});
		const wake = () => audio.state !== 'running' && audio.resume().catch(() => {});
		for (const type of ['pointerdown', 'keydown', 'touchend']) addEventListener(type, wake, {capture: true, passive: true});
	}
	// it's scheduled AHEAD s out (so it starts cleanly, not part-way into the audio thread's current block), plus
	// the device's own latency (known once it's running): trigger it that much before the lock, so it's heard on it
	const lead = () => (audio ? AHEAD + (audio.baseLatency || 0) + (audio.outputLatency || 0) : 0);
	const play = () => {
		if (!audio || !buffer) return;
		const go = () => {
			const src = audio.createBufferSource(), gain = audio.createGain();
			gain.gain.value = 0.18;
			src.buffer = buffer;
			src.connect(gain).connect(audio.destination);
			src.start(audio.currentTime + AHEAD);
		};
		if (audio.state === 'running') return go();
		// not running (no click yet, or the window's in the background): try to wake it, and play only if it wakes
		// at once. Otherwise every hover's zap would wait and all go off together when it did
		const asked = performance.now();
		audio.resume().then(() => performance.now() - asked < 120 && go(), () => {});
	};
	const mark = brand.querySelector('.wordmark');
	let start = null;
	const frame = (ms) => {
		const t = (ms - start) / 1000;
		const p = Math.min(1, Math.max(0, t / SWIRL));
		const spin = TILT + SPIN * (1 - p * p); // faster the closer they get, then stops dead
		const r = SPREAD * Math.pow(1 - p, 1.3);
		for (const [who, away] of [['claude', 180], ['gemini', 0]]) {
			const a = ((spin + away) * Math.PI) / 180;
			for (const g of halves(who)) g.setAttribute('transform', `translate(${(r * Math.cos(a)).toFixed(1)} ${(r * Math.sin(a)).toFixed(1)}) rotate(${spin.toFixed(1)} 500 500)`);
		}
		const hit = t >= SWIRL ? Math.exp(-(t - SWIRL) / 0.09) : 0; // the lock: a sharp spike that dies in a few frames
		if (t >= SWIRL - lead() && !zapped) {
			zapped = true;
			play();
		}
		for (const f of shifts) f.setAttribute('dx', (f.dataset.shift * (14 + 40 * hit)).toFixed(1));
		lock.setAttribute('transform', `translate(500 500) scale(${(1 + 0.08 * hit).toFixed(3)}) translate(-500 -500)`);
		if (mark) mark.style.setProperty('--rgb', `${(1.5 + 6 * hit).toFixed(2)}px`); // the name's fringes jolt with the lock
		if (t < SWIRL + 0.5) requestAnimationFrame(frame);
		else start = null, running = false;
	};
	// Clicking the logo opens the next page with the pointer still on it, and the browser then reports a fresh
	// mouseenter. So a page only spins the logo once the pointer has been seen off it: arriving on it does nothing
	// until it leaves and comes back. (No storage: Firefox keeps it per file when the site is opened from disk.)
	let armed = false;
	addEventListener('pointermove', (e) => {
		if (!(e.target instanceof Element && e.target.closest('.brand'))) armed = true;
	}, {passive: true});
	brand.addEventListener('mouseleave', () => (armed = true));
	let running = false; // a frame is scheduled
	brand.addEventListener('mouseenter', () => {
		if (!armed) return;
		// a new hover starts the spin again once the halves have locked (and zapped), so quick repeat hovers each
		// get their own; one mid-swirl is let finish, or the lock would never come
		if (start !== null && (performance.now() - start) / 1000 < SWIRL) return;
		start = performance.now();
		zapped = false;
		if (!running) requestAnimationFrame(frame);
		running = true;
	});
})();

// Mousing over a link (YouTube, the repo) jolts its colour split wide and lets it settle, like the logo's lock.
(() => {
	if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
	for (const a of document.querySelectorAll('.ln')) a.addEventListener('mouseenter', () => {
		const shifts = a.querySelectorAll('[data-shift]'), t0 = performance.now();
		const step = (t) => {
			const k = Math.min(1, (t - t0) / 420), amp = 0.34 + 1.6 * (1 - k) ** 2; // the mark's units: 0.34 at rest
			shifts.forEach((s) => s.setAttribute('dx', (amp * s.dataset.shift).toFixed(3)));
			if (k < 1) requestAnimationFrame(step);
		};
		requestAnimationFrame(step);
	});
})();

// The transcript page's two tabs: the transcript, where each fact-check is a one-line marker, and the fact-checks
// themselves as full cards. The address says which is open (#checks, #fc-7: the checks; anything else: the transcript),
// so links to a check still work, including the old #check-7 ones. Without JS both show, one after the other.
onPage((signal) => {
	const panels = [...document.querySelectorAll('[data-panel]')];
	if (!panels.length) return;
	const root = document.documentElement;
	const nav = document.querySelector('.tabs');
	const tabs = [...nav.querySelectorAll('[data-tab]')];
	const tabOf = (hash) => (/^#(checks$|fc-|check-)/.test(hash) ? 'checks' : 'transcript');
	const target = (hash) => {
		const old = hash.match(/^#check-(\w+)$/);
		return hash.length > 1 ? document.getElementById(old ? `fc-${old[1]}` : decodeURIComponent(hash.slice(1))) : null;
	};
	const show = (tab) => {
		root.dataset.tab = tab;
		panels.forEach((el) => (el.hidden = el.dataset.panel !== tab));
		tabs.forEach((a) => a.setAttribute('aria-selected', String(a.dataset.tab === tab)));
	};
	const flash = (el) => {
		el.classList.remove('flash');
		void el.offsetWidth; // restart the animation
		el.classList.add('flash');
	};
	// where you'd scrolled to in each tab, so switching back returns you there
	const pos = {};
	const go = (hash, push, back = false) => {
		const tab = tabOf(hash), switching = root.dataset.tab !== tab;
		if (switching) pos[root.dataset.tab] = scrollY;
		show(tab);
		// each history entry keeps its own spots, so the back button can return to them
		if (push) history.pushState({pos: {...pos}}, '', hash);
		else history.replaceState({...history.state, pos: {...pos}}, '');
		const el = hash === '#checks' || hash === '#transcript' ? null : target(hash);
		// a tab, or the back button: back to where you were in it. A link to a place (a contents entry, a check)
		// goes to that place
		if (switching && (!el || back) && pos[tab] !== undefined) scrollTo({top: pos[tab], behavior: 'instant'});
		else if (el) {
			el.scrollIntoView({behavior: switching ? 'instant' : 'smooth'});
			if (el.matches('.entry, .check-line')) flash(el);
		} else if (switching) {
			// the tabs stay on screen, so a switch from further down starts the other tab from its top
			const panel = document.getElementById(tab);
			if (panel.getBoundingClientRect().top < nav.getBoundingClientRect().bottom) panel.scrollIntoView({behavior: 'instant'});
		}
		dispatchEvent(new Event('scroll')); // the contents highlight
	};
	root.classList.add('tabbed');
	// pinned or not: the cover behind them (style.css) only once they're pinned, or it hides what's just above them
	const stuck = () => nav.classList.toggle('stuck', nav.getBoundingClientRect().top <= parseFloat(getComputedStyle(nav).top) + 0.5);
	on(signal, window, 'scroll', stuck, {passive: true});
	on(signal, window, 'resize', stuck);
	stuck();
	signal.addEventListener('abort', () => {
		root.classList.remove('tabbed');
		delete root.dataset.tab;
	});
	Object.assign(pos, history.state?.pos); // after a reload, or coming back from another page
	show(tabOf(location.hash));
	// the browser looked for the address's place before it was shown; a spot to return to (below) wins over it
	if (target(location.hash) && history.state?.y === undefined) requestAnimationFrame(() => go(location.hash, false));
	const path = location.pathname;
	on(signal, window, 'popstate', () => location.pathname === path && go(location.hash, false, true));
	// in-page links switch tabs as they go; 🔎 links open a preview instead (below)
	on(signal, document, 'click', (ev) => {
		const a = ev.target.closest('a[href^="#"]');
		if (!a || a.hasAttribute('data-check') || ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
		ev.preventDefault();
		closePeek();
		go(a.hash || '#top', a.hash !== location.hash);
	});

	// the filters over the fact-checks: whose claim, and the verdict
	const cards = [...document.querySelectorAll('[data-panel="checks"] .entry')];
	const none = document.querySelector('[data-panel="checks"] .none');
	const want = {by: 'all', verdict: 'all'};
	const fits = (c, w) => ['by', 'verdict'].every((k) => w[k] === 'all' || c.dataset[k] === w[k]);
	const buttons = [...document.querySelectorAll('.filters button')];
	const key = (b) => ('by' in b.dataset ? 'by' : 'verdict');
	// each chip counts the checks it would show, given the other filter as it's set: pick Argon, and the
	// verdicts count Argon's claims only
	const recount = () =>
		buttons.forEach((b) => {
			const n = cards.filter((c) => fits(c, {...want, [key(b)]: b.dataset[key(b)]})).length;
			b.querySelector('.n').textContent = n;
			b.classList.toggle('empty', n === 0);
		});
	buttons.forEach((b) =>
		b.addEventListener('click', () => {
			want[key(b)] = b.dataset[key(b)];
			buttons.filter((x) => key(x) === key(b)).forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
			let shown = 0;
			cards.forEach((c) => {
				c.hidden = !fits(c, want);
				shown += !c.hidden;
			});
			none.hidden = shown > 0;
			recount();
		}),
	);

	// The preview: a copy of the check's card beside the 🔎 link (hover with a mouse, click to keep it open), or a
	// sheet up from the bottom on a touch screen. It links on to the card in the fact-checks tab.
	const peek = document.createElement('div');
	peek.className = 'peek';
	peek.setAttribute('role', 'dialog');
	document.body.append(peek);
	signal.addEventListener('abort', () => peek.remove());
	const mouse = matchMedia('(hover: hover) and (pointer: fine)');
	let owner = null, pinned = false, opening = 0, closing = 0;
	const place = () => {
		if (!owner || !mouse.matches) return;
		// below the link, or above it if there's more room there (under the pinned header), shrunk to fit
		const r = owner.getBoundingClientRect();
		const room = {below: innerHeight - r.bottom - 22, above: r.top - 10 - 104};
		peek.style.maxHeight = '';
		const full = peek.offsetHeight;
		const below = full <= room.below || room.below >= room.above;
		const h = Math.min(full, below ? room.below : room.above);
		peek.style.maxHeight = `${h}px`;
		peek.style.left = `${Math.max(16, Math.min(r.left, innerWidth - peek.offsetWidth - 16))}px`;
		peek.style.top = `${below ? r.bottom + 10 : r.top - 10 - h}px`;
	};
	const openPeek = (a, pin) => {
		const card = target(a.hash);
		if (!card) return;
		if (owner !== a) {
			const copy = card.cloneNode(true);
			copy.removeAttribute('id');
			copy.removeAttribute('hidden');
			copy.querySelector('.back')?.remove();
			copy.querySelectorAll('[id]').forEach((x) => x.removeAttribute('id'));
			const foot = document.createElement('div');
			foot.className = 'peek-foot';
			foot.innerHTML = `<a href="${a.hash}">open in fact-checks →</a><button type="button" aria-label="Close">${mouse.matches ? 'esc' : 'close'}</button>`;
			foot.querySelector('button').onclick = closePeek;
			peek.replaceChildren(copy, foot);
			peek.scrollTop = 0;
		}
		owner = a;
		pinned = pinned || pin;
		peek.classList.toggle('sheet', !mouse.matches);
		peek.classList.add('on');
		place();
	};
	function closePeek() {
		clearTimeout(opening);
		peek.classList.remove('on');
		owner = null;
		pinned = false;
	}
	const later = () => {
		clearTimeout(closing);
		closing = setTimeout(() => !pinned && closePeek(), 220);
	};
	on(signal, document, 'mouseover', (ev) => {
		if (!mouse.matches) return;
		const a = ev.target.closest('a[data-check]');
		if (a && !peek.contains(a)) {
			clearTimeout(closing);
			clearTimeout(opening);
			if (!pinned) opening = setTimeout(() => openPeek(a, false), 260);
		} else if (peek.contains(ev.target)) clearTimeout(closing);
	});
	on(signal, document, 'mouseout', (ev) => {
		const from = ev.target.closest('a[data-check], .peek');
		if (from && !from.contains(ev.relatedTarget)) {
			clearTimeout(opening);
			later();
		}
	});
	on(signal, document, 'click', (ev) => {
		const a = ev.target.closest('a[data-check]');
		if (a && !ev.metaKey && !ev.ctrlKey && !ev.shiftKey) {
			ev.preventDefault();
			if (owner === a && pinned) closePeek();
			else openPeek(a, true);
		} else if (owner && !peek.contains(ev.target)) closePeek();
	});
	on(signal, window, 'keydown', (ev) => ev.key === 'Escape' && closePeek());
	on(signal, window, 'scroll', place, {passive: true});
	on(signal, window, 'resize', place);
});

// Folded turns (build_site.py's folded()): a button expands or minimises one; "expand all" in the tabs does every one,
// keeping what you're reading where it is. Find-in-page opens a folded one by itself (hidden="until-found").
onPage((signal) => {
	const entries = [...document.querySelectorAll('.entry')].filter((e) => e.querySelector(':scope > .text > .fold'));
	if (!entries.length) return;
	const all = document.querySelector('.tabs .all');
	const set = (entry, open) => {
		for (const m of entry.querySelectorAll(':scope > .text > .more')) open ? m.removeAttribute('hidden') : m.setAttribute('hidden', 'until-found');
		entry.classList.toggle('open', open);
		entry.querySelector('.fold').setAttribute('aria-expanded', String(open));
	};
	const settle = () => {
		const open = entries.every((e) => e.classList.contains('open'));
		all?.setAttribute('aria-pressed', String(open));
		if (all) all.innerHTML = `${open ? 'minimise' : 'expand'}<span class="long"> all</span>`; // phones show just the verb
		dispatchEvent(new Event('scroll')); // the contents highlight and the selection glow
	};
	for (const e of entries) {
		e.querySelector('.fold').addEventListener('click', () => {
			const open = !e.classList.contains('open');
			set(e, open);
			// folding one you'd scrolled into leaves you looking at its start, not at whatever moved up under you
			if (!open && e.getBoundingClientRect().top < 0) e.scrollIntoView({behavior: 'instant'});
			settle();
		});
	}
	on(signal, document, 'beforematch', (ev) => {
		const e = ev.target.closest('.entry');
		if (e && entries.includes(e)) {
			set(e, true);
			settle();
		}
	});
	all?.addEventListener('click', () => {
		const open = all.getAttribute('aria-pressed') !== 'true';
		// hold the first thing on screen (under the tabs) still while everything above and below it changes height
		const line = document.querySelector('.tabs').getBoundingClientRect().bottom;
		const anchor = [...document.querySelectorAll('#transcript > *')].find((el) => el.getBoundingClientRect().bottom > line);
		const before = anchor?.getBoundingClientRect().top;
		entries.forEach((e) => set(e, open));
		if (anchor && before !== undefined) scrollBy({top: anchor.getBoundingClientRect().top - before, behavior: 'instant'});
		settle();
	});
});

// The index terminal's window buttons do nothing useful, so clicking one types its command at the prompt and gets
// refused by a cow in that button's colour (close: Opus orange, minimise: the fact-checker's yellow, full screen:
// Argon blue), lit like the buttons. Clicking the same button again escalates (the second tries sudo; by the third
// the two sides finally agree on something), then cycles; another button starts from its own first reply. Only the
// latest try stays on screen.
onPage((signal) => {
	const lights = [...document.querySelectorAll('.term .lights .l')];
	const prompt = [...document.querySelectorAll('.term .row.prompt')].pop();
	const cursor = prompt?.querySelector('.cursor');
	if (lights.length !== 3 || !cursor) return;
	const COMMANDS = ['exit', 'minimise', 'fullscreen'];
	const COLOURS = ['claude', 'evidence', 'gemini'];
	const FIRST = ['Denied.', 'Denied. Nothing here gets minimised.', "Denied. You're already seeing the whole picture."];
	const LATER = ['Denied. Even with sudo.', 'Opus and Argon finally agree on something: denied.'];
	const instant = matchMedia('(prefers-reduced-motion: reduce)').matches;
	let last = -1, tries = 0, busy = false;
	const egg = document.createElement('div');
	egg.className = 'egg';
	prompt.before(egg);
	const typed = document.createElement('span');
	cursor.before(typed);

	const cow = (msg) => {
		// cowsay's own layout: the message wrapped at 30 characters in a bubble, the cow below
		// The cow is from cowsay by Tony Monroe (1999), used under its Artistic License / GPL terms.
		const lines = [];
		for (const word of msg.split(' ')) {
			const end = lines.length - 1;
			if (end >= 0 && (lines[end] + ' ' + word).length <= 30) lines[end] += ' ' + word;
			else lines.push(word);
		}
		const w = Math.max(...lines.map((l) => l.length));
		const edge = (i) => (lines.length === 1 ? ['<', '>'] : i === 0 ? ['/', '\\'] : i === lines.length - 1 ? ['\\', '/'] : ['|', '|']);
		return [
			' ' + '_'.repeat(w + 2),
			...lines.map((l, i) => `${edge(i)[0]} ${l.padEnd(w)} ${edge(i)[1]}`),
			' ' + '-'.repeat(w + 2),
			'        \\   ^__^',
			'         \\  (oo)\\_______',
			'            (__)\\       )\\/\\',
			'                ||----w |',
			'                ||     ||',
		];
	};
	const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
	const paint = (rows, colour) => {
		const pre = document.createElement('pre');
		pre.className = `cow ${colour}`;
		// the two sides' names in their own colours, wherever the cow says them
		pre.innerHTML = esc(rows.join('\n')).replace(/\b(Opus|Argon)\b/g, (m) => `<span class="${m === 'Opus' ? 'claude' : 'gemini'}">${m}</span>`);
		return pre;
	};

	lights.forEach((light, i) =>
		light.addEventListener('click', async () => {
			if (busy) return;
			busy = true;
			if (i !== last) tries = 0; // another button starts over
			last = i;
			const n = tries++ % 3;
			const command = n === 0 ? COMMANDS[i] : `sudo ${COMMANDS[i]}`;
			const said = n === 0 ? FIRST[i] : LATER[n - 1];
			egg.replaceChildren();
			typed.textContent = '';
			for (const ch of command) {
				typed.textContent += ch;
				if (!instant) await new Promise((r) => setTimeout(r, 55));
			}
			if (!instant) await new Promise((r) => setTimeout(r, 260)); // enter
			if (signal.aborted) return;
			const ran = prompt.cloneNode(true);
			ran.querySelector('.cursor')?.remove();
			egg.replaceChildren(ran, paint(cow(said), COLOURS[i]));
			typed.textContent = '';
			busy = false;
		}, {signal}),
	);
});

// Listening: a card's speaker button reads that card, in the voice of whoever wrote it (the narrator for summaries
// and fact-checks), voiced ahead of time with the videos' Kokoro voices (build_site.py --voice); the playing card's
// button pauses it and plays it on. Then it carries on through the page like a podcast of the discussion, hearing
// each fact-check where it landed (its marker plays the check). It carries on in one of two ways: a quick listen
// starts at the coin toss, leaves the sides' responses to their rounds' summaries and hears only the checks that
// caught something (build_site.py marks what it leaves out, data-skim); a full listen reads every word. The tabs'
// "▶ listen" starts either from the beginning, and a player bar along the bottom (once something plays) pauses,
// skips, scrubs and switches between the two.
// Starting takes a copy of the running order (each card's audio, title, colour and whether a quick listen skips it),
// so playing doesn't depend on the page: it carries on while you're on another page, and with the phone locked (the
// lock screen gets the title, the logo, play/pause, skip and a position bar). Back on the page, the card being read
// lights up again. The player keeps what's being read on screen: each card comes up under the tabs, and a long one
// scrolls on as its reading goes (by how far into its audio it is). Scrolling yourself stops that, so it never
// fights you; the bar's card title, ⏮/⏭, a card's speaker or starting a listen take it up again.
(() => {
	const player = new Audio();
	player.preload = 'auto';
	// A log of what the player and the page go through, to find out why a listen stops with the phone locked. Kept in
	// this browser only (the last 400 lines) and shown by adding #listen-log to the address. Each line: the time, the
	// page's visibility (v: on screen, h: hidden, e.g. locked) and what happened.
	const LOGKEY = 'ns-listen-log';
	const log = (what) => {
		try {
			const lines = JSON.parse(localStorage.getItem(LOGKEY) || '[]');
			lines.push(`${new Date().toISOString().slice(11, 23)} ${document.visibilityState[0]} ${what}`);
			localStorage.setItem(LOGKEY, JSON.stringify(lines.slice(-400)));
		} catch {}
	};
	for (const ev of ['play', 'playing', 'pause', 'ended', 'waiting', 'stalled', 'emptied', 'abort', 'error'])
		player.addEventListener(ev, () => log(`${ev}${ev === 'error' ? ` (code ${player.error?.code})` : ''} at ${player.currentTime.toFixed(1)}s of ${(player.duration || 0).toFixed(1)}s`));
	for (const ev of ['visibilitychange', 'freeze', 'resume']) document.addEventListener(ev, () => log(`page ${ev}`));
	for (const ev of ['pagehide', 'pageshow']) addEventListener(ev, () => log(`page ${ev}`));
	const showLog = () => {
		document.querySelector('.listen-log')?.remove();
		if (location.hash !== '#listen-log') return;
		let lines = [];
		try { lines = JSON.parse(localStorage.getItem(LOGKEY) || '[]'); } catch {}
		const box = document.createElement('div');
		box.className = 'listen-log';
		box.innerHTML = `<div class="bar"><b>listen log</b> · ${lines.length} lines <button type="button" data-do="copy">copy</button><button type="button" data-do="clear">clear</button><button type="button" data-do="close">close</button></div><pre></pre>`;
		box.querySelector('pre').textContent = lines.join('\n') || '(empty: start a listen, then come back here)';
		box.addEventListener('click', (ev) => {
			const d = ev.target.dataset?.do;
			if (d === 'copy') navigator.clipboard?.writeText(lines.join('\n'));
			if (d === 'clear') { try { localStorage.removeItem(LOGKEY); } catch {} history.replaceState(null, '', location.pathname); box.remove(); }
			if (d === 'close') { history.replaceState(null, '', location.pathname); box.remove(); }
		});
		document.body.append(box);
	};
	addEventListener('hashchange', showLog);
	showLog();
	let list = []; // the running order: {id, src, title, colour, skim}
	let at = -1; // which of it is playing, or paused part-way
	let mode = 'quick';
	let follow = true; // keeping what's read on screen
	const now = () => list[at];
	const el = (item) => (item?.id ? document.getElementById(item.id) : null) || item?.node || null; // its card, if it's on this page
	const button = (c) => c?.querySelector(':scope > .say');
	const src = (c) => (c?.matches('.check-line') ? c.dataset.say : button(c)?.dataset.audio);
	const colour = (c) => (c.matches('.claude') ? 'claude' : c.matches('.gemini') ? 'gemini' : c.matches('.evidence, .check-line') ? 'evidence' : 'narrator');
	const titleOf = (c) => (c.matches('.check-line') ? `Fact-check ${c.querySelector('.num')?.textContent || ''}`
		: `${c.querySelector('header .kind')?.textContent.trim() || ''} · ${c.querySelector('header .who')?.textContent.trim() || ''}`);
	const entry = (c) => ({id: c.id || null, node: c.id ? null : c, src: new URL(src(c), location.href).href, title: titleOf(c), colour: colour(c), skim: c.hasAttribute('data-skim')});
	// the order a card belongs to: everything with audio alongside it (a preview's copy of a card is on its own)
	const orderOf = (c) => [...c.parentElement.querySelectorAll(':scope > .entry, :scope > .check-line[data-say]')].filter(src).map(entry);
	const skip = (item) => mode === 'quick' && item.skim;
	const clock = (s) => (Number.isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}` : '0:00');

	// the bar
	const bar = document.createElement('div');
	bar.className = 'player';
	bar.hidden = true;
	bar.innerHTML = `<div class="in">
		<button type="button" class="prev" aria-label="Previous card"><svg viewBox="0 0 16 16"><path d="M3.5 3v10M13 3.5 6 8l7 4.5z"/></svg></button>
		<button type="button" class="toggle" aria-label="Pause"><svg viewBox="0 0 16 16"><path class="pause" d="M5.5 3.5v9M10.5 3.5v9"/><path class="play" d="M5 3l8 5-8 5z"/></svg></button>
		<button type="button" class="next" aria-label="Next card"><svg viewBox="0 0 16 16"><path d="M12.5 3v10M3 3.5 10 8l-7 4.5z"/></svg></button>
		<button type="button" class="what" title="Show this card"></button>
		<input class="scrub" type="range" min="0" max="1" step="0.1" value="0" aria-label="Position in this card">
		<span class="time">0:00 / 0:00</span>
		<span class="mode" role="group" aria-label="Carry on with"><button type="button" data-mode="quick">quick</button><button type="button" data-mode="full">full</button></span>
		<button type="button" class="close" aria-label="Stop"><svg viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8"/></svg></button></div>`;
	document.body.append(bar);
	const $ = (s) => bar.querySelector(s);
	const scrub = $('.scrub');
	let dragging = false;
	const show = () => {
		const item = now();
		const g = document.querySelector('.listen .go');
		if (g) g.textContent = !item ? '▶ listen' : player.paused ? '▶ resume' : '❚❚ pause';
		bar.hidden = !item;
		document.body.classList.toggle('with-player', !!item);
		if (!item) return;
		bar.dataset.c = item.colour;
		$('.toggle').classList.toggle('paused', player.paused);
		$('.toggle').setAttribute('aria-label', player.paused ? 'Play' : 'Pause');
		$('.what').textContent = item.title;
		for (const b of bar.querySelectorAll('.mode button')) b.setAttribute('aria-pressed', String(b.dataset.mode === mode));
	};
	let told = 0;
	const tick = () => {
		const d = player.duration || 0;
		if (!dragging) {
			scrub.max = d || 1;
			scrub.value = player.currentTime;
		}
		scrub.style.setProperty('--p', d ? (player.currentTime / d).toFixed(4) : 0);
		$('.time').textContent = `${clock(player.currentTime)} / ${clock(d)}`;
		if (d) button(el(now()))?.style.setProperty('--p', (player.currentTime / d).toFixed(3)); // the card's ring fills too
		// the lock screen's position bar, now and then
		if (d && 'mediaSession' in navigator && navigator.mediaSession.setPositionState && performance.now() - told > 1000) {
			told = performance.now();
			try {
				navigator.mediaSession.setPositionState({duration: d, position: Math.min(player.currentTime, d), playbackRate: player.playbackRate});
			} catch {}
		}
	};
	// the card being read, lit (when it's on this page)
	const mark = () => {
		for (const c of document.querySelectorAll('.speaking')) {
			c.classList.remove('speaking');
			button(c)?.setAttribute('aria-pressed', 'false');
			button(c)?.style.removeProperty('--p');
		}
		const c = el(now());
		if (!c) return;
		const on = !player.paused;
		c.classList.toggle('speaking', on);
		button(c)?.setAttribute('aria-pressed', String(on));
	};
	const top = () => {
		// just under the tabs where they're pinned (before the page has scrolled to them, they sit lower down)
		const t = document.querySelector('.tabs');
		return t ? parseFloat(getComputedStyle(t).top) + t.offsetHeight + 12 : 12;
	};
	const bottom = () => innerHeight - (bar.hidden ? 0 : bar.offsetHeight) - 24; // just above the bar
	let bringing = 0; // until when a card's being brought up (keep() leaves the scroll alone meanwhile)
	const bringTo = (c) => {
		bringing = performance.now() + 1200;
		scrollBy({top: c.getBoundingClientRect().top - top(), behavior: 'smooth'});
	};
	const bring = () => {
		// a card that starts comes up under the tabs, unless it's already near there
		const c = el(now());
		if (!c || !follow || document.hidden) return;
		const r = c.getBoundingClientRect();
		if (r.top < top() || r.top > top() + (bottom() - top()) * 0.4) bringTo(c);
	};
	const keep = () => {
		// the point the reading has reached, roughly: as far down the card as the audio is through it
		const c = el(now());
		if (!c || !follow || player.paused || !player.duration || document.hidden || performance.now() < bringing) return;
		const r = c.getBoundingClientRect();
		const y = r.top + r.height * (player.currentTime / player.duration);
		if (y > bottom()) scrollBy({top: y - (top() + (bottom() - top()) * 0.3), behavior: 'smooth'});
	};
	for (const type of ['wheel', 'touchmove']) addEventListener(type, () => (follow = false), {passive: true});
	addEventListener('keydown', (ev) => {
		if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(ev.key) && !ev.target.closest?.('input, button')) follow = false;
	});

	// The next cards' audio is fetched into memory while this one plays, so a card ending never waits on the network.
	// With the phone locked, Android (Samsung's especially) cuts a page's network and timers in any gap where nothing
	// plays; a next card still loading then stalled or errored, and the listen stopped.
	const ready = new Map(); // src → its in-memory copy (a blob: URL), once fetched
	const fetching = new Map(); // src → the fetch under way
	const ahead = () => {
		const want = new Set();
		for (let i = at, n = 0; list[i] && n < 5; i++) if (i === at || !skip(list[i])) want.add(list[i].src), n++;
		for (const s of want) {
			if (ready.has(s) || fetching.has(s)) continue;
			fetching.set(s, fetch(s).then((r) => (r.ok ? r.blob() : null)).then((b) => {
				if (b && fetching.has(s)) ready.set(s, URL.createObjectURL(b)), log(`fetched ahead: ${ready.size} in memory`);
			}).catch((e) => log(`fetch ahead failed: ${e.name}`)).finally(() => fetching.delete(s)));
		}
		for (const [s, u] of ready) if (!want.has(s)) ready.delete(s), URL.revokeObjectURL(u); // the ones gone by
		for (const s of fetching.keys()) if (!want.has(s)) fetching.delete(s);
	};
	const playAt = (i) => {
		at = i;
		const item = now();
		player.src = ready.get(item.src) || item.src; // the copy in memory if it's there: no network at all
		log(`card ${i + 1} of ${list.length} (${player.src.startsWith('blob:') ? 'from memory' : 'from the network'}): ${item.title}`);
		player.play().catch((e) => log(`play() refused: ${e.name}: ${e.message}`));
		ahead();
		show();
		mark();
		bring();
		if ('mediaSession' in navigator) {
			navigator.mediaSession.metadata = new MediaMetadata({title: item.title, artist: 'Neural Summit', album: document.title.replace(/ · .*$/, ''),
				artwork: [{src: artwork, sizes: '512x512', type: 'image/png'}]});
		}
	};
	// the site's root, from the logo's link home, for the lock screen's artwork
	const artwork = new URL(document.querySelector('.brand')?.getAttribute('href') || 'index.html', location.href).href.replace(/index\.html$/, '') + 'artwork.png';
	const start = (c) => {
		// a card's own order, starting at it
		list = orderOf(c);
		const i = list.findIndex((x) => (c.id ? x.id === c.id : x.node === c));
		playAt(Math.max(0, i));
	};
	const resume = () => {
		player.play().catch((e) => log(`play() refused on resume: ${e.name}: ${e.message}`));
	};
	const pause = () => player.pause();
	const stop = () => {
		player.pause();
		at = -1;
		list = [];
		ahead(); // lets go of the copies in memory
		mark();
		show();
	};
	const step = (by) => {
		if (!now()) return;
		let i = at + by;
		while (list[i] && skip(list[i])) i += by;
		if (!list[i]) return by > 0 ? stop() : (player.currentTime = 0);
		playAt(i);
	};
	const menu = (open) => {
		const m = document.querySelector('.listen .menu');
		if (!m) return;
		m.hidden = !open;
		document.querySelector('.listen .go')?.setAttribute('aria-expanded', String(open));
	};

	$('.toggle').addEventListener('click', () => (player.paused ? resume() : pause()));
	$('.prev').addEventListener('click', () => ((follow = true), player.currentTime > 3 ? (player.currentTime = 0) : step(-1)));
	$('.next').addEventListener('click', () => ((follow = true), step(1)));
	$('.close').addEventListener('click', stop);
	$('.what').addEventListener('click', () => {
		follow = true;
		const c = el(now());
		if (c) bringTo(c);
	});
	for (const b of bar.querySelectorAll('.mode button')) b.addEventListener('click', () => ((mode = b.dataset.mode), ahead(), show()));
	scrub.addEventListener('input', () => {
		dragging = true;
		player.currentTime = +scrub.value;
		tick();
	});
	scrub.addEventListener('change', () => (dragging = false));

	document.addEventListener('click', (ev) => {
		const b = ev.target.closest('.say');
		const g = ev.target.closest('.listen .go');
		const choice = ev.target.closest('.listen .menu [data-mode]');
		if (g) {
			if (now()) return player.paused ? resume() : pause();
			return menu(document.querySelector('.listen .menu').hidden);
		}
		if (choice) {
			// from the beginning: a quick listen's first card is the coin toss
			mode = choice.dataset.mode;
			menu(false);
			follow = true;
			const first = document.querySelector('#transcript > .entry, #transcript > .check-line[data-say]');
			if (!first) return;
			list = orderOf(first);
			const i = list.findIndex((x) => !skip(x));
			if (i >= 0) playAt(i);
			return;
		}
		if (!ev.target.closest('.listen')) menu(false);
		if (!b) return;
		const c = b.closest('.entry');
		follow = true;
		if (c === el(now())) return player.paused ? resume() : pause();
		start(c);
	});
	addEventListener('keydown', (ev) => ev.key === 'Escape' && menu(false));
	// another page swapped in (the nav at the end): light the card being read, if it's there
	addEventListener('pagestart', () => (mark(), show()));
	player.addEventListener('ended', () => step(1));
	player.addEventListener('error', () => {
		// a bad in-memory copy: fetch the file itself instead; only if that fails too does the listen stop
		const item = now();
		if (!item) return;
		if (player.src.startsWith('blob:')) {
			ready.delete(item.src);
			const t = player.currentTime;
			player.src = item.src;
			player.currentTime = t;
			player.play().catch(() => {});
		} else stop();
	});
	// the lock screen's play/pause shows what's actually happening, and Android keeps the notification while it's "playing"
	const state = (s) => 'mediaSession' in navigator && (navigator.mediaSession.playbackState = s);
	player.addEventListener('play', () => (show(), mark(), state('playing')));
	player.addEventListener('pause', () => (show(), mark(), state(now() ? 'paused' : 'none')));
	player.addEventListener('timeupdate', () => (tick(), keep()));
	player.addEventListener('loadedmetadata', tick);
	if ('mediaSession' in navigator) {
		const act = (name, fn) => {
			try {
				navigator.mediaSession.setActionHandler(name, (d) => (log(`lock screen: ${name}`), fn(d)));
			} catch {}
		};
		act('play', () => now() && resume());
		act('pause', () => now() && pause());
		act('nexttrack', () => now() && step(1));
		act('previoustrack', () => now() && (player.currentTime > 3 ? (player.currentTime = 0) : step(-1)));
		act('seekto', (d) => now() && (player.currentTime = d.seekTime));
		act('seekbackward', (d) => now() && (player.currentTime = Math.max(0, player.currentTime - (d.seekOffset || 10))));
		act('seekforward', (d) => now() && (player.currentTime = Math.min(player.duration || 0, player.currentTime + (d.seekOffset || 10))));
	}
})();

// Moving between the site's pages without loading a fresh one: a link to another page fetches it and swaps its
// content in, keeping the header, the drifting shapes and the sound running. Browsers only let a page make sound
// once the visitor has clicked on it, and a fresh page would start silent again. Static files and the browser's
// own fetch, so it works on GitHub Pages; opened from disk (file://), where pages can't fetch, links work as usual.
(() => {
	const root = document.documentElement;
	let ctl = null;
	const startPage = () => {
		ctl?.abort();
		ctl = new AbortController();
		for (const setup of pageSetups) setup(ctl.signal);
		dispatchEvent(new Event('pagestart')); // for what outlives a page (the player) to find its place on the new one
	};
	// the page puts you back itself (the browser's own restoring would use the spot from mid-tab-switch, when the
	// other tab had shortened the page, and can't know a swapped-in page): the spot is kept in each history entry
	// whenever scrolling stops (saving it as a page closes doesn't stick in Chrome)
	history.scrollRestoration = 'manual';
	const remember = () => history.replaceState({...history.state, y: scrollY}, '');
	let keep = 0;
	addEventListener('scroll', () => {
		clearTimeout(keep);
		keep = setTimeout(remember, 250);
	}, {passive: true});
	const returnTo = () => {
		const y = history.state?.y;
		if (y !== undefined) requestAnimationFrame(() => scrollTo({top: y, behavior: 'instant'}));
		return y !== undefined;
	};

	let here = location.pathname;
	const load = async (url, push) => {
		let next, doc;
		try {
			const res = await fetch(url);
			if (!res.ok) throw new Error(res.status);
			doc = new DOMParser().parseFromString(await res.text(), 'text/html');
			next = doc.getElementById('page');
			if (!next) throw new Error('no page');
		} catch {
			location.href = url; // anything odd: just go there
			return;
		}
		if (push) {
			clearTimeout(keep);
			remember();
			history.pushState({}, '', url);
		}
		here = location.pathname;
		document.title = doc.title;
		// the header stays, but its link home is relative to the page it's on
		document.querySelector('.brand')?.setAttribute('href', doc.querySelector('.brand')?.getAttribute('href') || 'index.html');
		document.getElementById('page').replaceWith(document.adoptNode(next));
		getSelection().removeAllRanges();
		startPage();
		if (!push && returnTo()) return;
		const at = location.hash.length > 1 && document.getElementById(decodeURIComponent(location.hash.slice(1)));
		if (at) at.scrollIntoView({behavior: 'instant'});
		else scrollTo({top: 0, behavior: 'instant'});
	};
	if (location.protocol !== 'file:') {
		document.addEventListener('click', (ev) => {
			if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
			const a = ev.target.closest('a[href]');
			if (!a || a.target || a.hasAttribute('download')) return;
			const url = new URL(a.href, location.href);
			// another of the site's pages; a place on this page is the page's own business
			if (url.origin !== location.origin || url.pathname === location.pathname || !/(\.html|\/)$/.test(url.pathname)) return;
			ev.preventDefault();
			load(url.href, true);
		});
		addEventListener('popstate', () => location.pathname !== here && load(location.href, false));
	}
	startPage();
	returnTo(); // after a reload
})();
