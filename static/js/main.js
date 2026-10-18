/* ══════════════════════════════════════════════════════════════
   GESTIÓN FINANCIERA · Interacción
   Moneda · Hojas · Segmentados · Confirmación · Toasts · Gráficas
   ══════════════════════════════════════════════════════════════ */

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

// ──────────────────────────────────────────────
// MONEDA: formato $ XXX XXX,XX
// ──────────────────────────────────────────────

/**
 * Formatea un número a formato monetario $ 1 234 567,89
 * @param {number|string} value
 * @returns {string}
 */
function formatCurrency(value) {
    if (value === null || value === undefined || value === '') return '$ 0,00';
    let num = typeof value === 'string' ? parseFloat(value.replace(/[^0-9.-]+/g, '')) : value;
    if (isNaN(num)) return '$ 0,00';
    const sign = num < 0 ? '−' : '';
    const parts = Math.abs(num).toFixed(2).split('.');
    const integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    return `${sign}$ ${integerPart},${parts[1]}`;
}

/** Formato compacto para ejes y etiquetas: $ 1,2 M · $ 850 mil */
function formatCompact(value) {
    const abs = Math.abs(value);
    const sign = value < 0 ? '−' : '';
    const fmt = (n, unit) => `${sign}$ ${n.toLocaleString('es-CO', { maximumFractionDigits: n < 10 ? 1 : 0 })}${unit}`;
    if (abs >= 1e9) return fmt(abs / 1e9, ' mil M');
    if (abs >= 1e6) return fmt(abs / 1e6, ' M');
    if (abs >= 1e3) return fmt(abs / 1e3, ' mil');
    return `${sign}$ ${Math.round(abs)}`;
}

/**
 * Convierte "$ 1 234 567,89" (o un float crudo "1234567.89") a número.
 * @param {string} str
 * @returns {number}
 */
function parseCurrencyToNumber(str) {
    if (!str) return 0;
    let cleaned = str.toString().replace(/[$\s−]/g, '').trim();
    cleaned = cleaned.replace(',', '.');
    const val = parseFloat(cleaned);
    return isNaN(val) ? 0 : val;
}

/** Máscara en tiempo real para inputs .currency-input (los dos últimos dígitos son centavos). */
function setupCurrencyInputs(root = document) {
    root.querySelectorAll('.currency-input').forEach(input => {
        if (input.dataset.masked) return;
        input.dataset.masked = '1';
        input.setAttribute('inputmode', 'numeric');
        input.setAttribute('autocomplete', 'off');

        input.addEventListener('focus', function () {
            if (this.value === '$ 0,00' || this.value === '$ 0') {
                this.value = '';
            } else {
                requestAnimationFrame(() => this.select());
            }
        });

        input.addEventListener('input', function () {
            const rawValue = this.value.replace(/[^0-9]/g, '');
            if (!rawValue) {
                this.value = '';
                this.dataset.rawValue = '0';
                return;
            }
            const floatVal = parseFloat(rawValue) / 100;
            this.dataset.rawValue = floatVal.toString();
            this.value = formatCurrency(floatVal);
        });

        input.addEventListener('blur', function () {
            if (!this.value || this.value.trim() === '' || this.value === '$') {
                this.value = '$ 0,00';
                this.dataset.rawValue = '0';
            }
        });

        if (!input.value || input.value === '0' || input.value === '0.0') {
            input.value = '$ 0,00';
            input.dataset.rawValue = '0';
        } else {
            const parsed = parseCurrencyToNumber(input.value);
            input.value = formatCurrency(parsed);
            input.dataset.rawValue = parsed.toString();
        }
    });
}

/** Resetea un formulario y deja los montos en $ 0,00. */
function resetFormToZeros(form) {
    form.reset();
    form.querySelectorAll('.currency-input').forEach(input => {
        input.value = '$ 0,00';
        input.dataset.rawValue = '0';
    });
    form.querySelectorAll('input[type="number"]').forEach(input => {
        if (input.dataset.defaultVal !== undefined) input.value = input.dataset.defaultVal;
    });
    const type = form.querySelector('input[name="type"]:checked');
    if (type) {
        form.dataset.type = type.value;
        const amount = form.querySelector('.amount-field');
        if (amount) amount.dataset.tone = type.value;
    }
    form.querySelectorAll('[data-reveal]').forEach(t => t.dispatchEvent(new Event('change')));
    form.querySelectorAll('.segmented').forEach(syncSegmented);
}

// ──────────────────────────────────────────────
// HOJAS (sheets)
// En escritorio emergen desde el botón que las abre; en móvil suben desde
// abajo y se pueden arrastrar para cerrar (con proyección de la velocidad).
// ──────────────────────────────────────────────

const Sheets = (() => {
    const stack = [];
    const MOBILE = window.matchMedia('(max-width: 640px)');

    function open(id, trigger) {
        const sheet = document.getElementById(id);
        if (!sheet || sheet.classList.contains('is-open')) return;

        // Una hoja a la vez: si hay otra abierta, se reemplaza
        const current = stack[stack.length - 1];
        if (current && current.sheet !== sheet && !sheet.classList.contains('alert-dialog')) {
            close(current.sheet, { restoreFocus: false });
        }

        const panel = sheet.querySelector('.sheet-panel');
        sheet.classList.remove('is-closing');
        sheet.hidden = false;

        // Anclar el origen de la animación al botón que la abrió
        if (trigger && !MOBILE.matches && panel) {
            const t = trigger.getBoundingClientRect();
            const ox = t.left + t.width / 2 - panel.offsetLeft;
            const oy = t.top + t.height / 2 - panel.offsetTop;
            panel.style.transformOrigin = `${ox}px ${oy}px`;
        } else if (panel) {
            panel.style.transformOrigin = '';
        }

        // Forzar el estilo inicial antes de animar
        void sheet.offsetWidth;
        sheet.classList.add('is-open');
        sheet.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        stack.push({ sheet, trigger });

        setupCurrencyInputs(sheet);
        sheet.querySelectorAll('.segmented').forEach(syncSegmented);

        const autofocus = sheet.querySelector('[autofocus]') || panel;
        setTimeout(() => {
            if (autofocus && !MOBILE.matches) autofocus.focus({ preventScroll: true });
            else panel && panel.focus({ preventScroll: true });
        }, 60);
    }

    function close(sheet, { restoreFocus = true, duration } = {}) {
        if (!sheet || !sheet.classList.contains('is-open')) return;
        const panel = sheet.querySelector('.sheet-panel');
        const idx = stack.findIndex(s => s.sheet === sheet);
        const entry = idx >= 0 ? stack.splice(idx, 1)[0] : null;

        if (panel && duration) panel.style.transitionDuration = `${duration}s`;
        sheet.classList.add('is-closing');
        sheet.classList.remove('is-open');
        sheet.setAttribute('aria-hidden', 'true');
        if (panel) panel.style.transform = '';

        const done = () => {
            if (sheet.classList.contains('is-open')) return; // reabierta a mitad del cierre
            sheet.classList.remove('is-closing');
            if (panel) panel.style.transitionDuration = '';
            const form = sheet.querySelector('form[data-reset-on-close]');
            if (form) resetFormToZeros(form);
        };
        setTimeout(done, reduceMotion.matches ? 210 : 440);

        if (!stack.length) document.body.style.overflow = '';
        if (restoreFocus && entry && entry.trigger && document.contains(entry.trigger)) {
            entry.trigger.focus({ preventScroll: true });
        }
    }

    function closeTop() {
        const top = stack[stack.length - 1];
        if (top) close(top.sheet);
    }

    // Arrastre para cerrar (solo móvil)
    function project(velocity, decelerationRate = 0.998) {
        return (velocity / 1000) * decelerationRate / (1 - decelerationRate);
    }
    function rubberband(overshoot, dimension, constant = 0.55) {
        return (overshoot * dimension * constant) / (dimension + constant * Math.abs(overshoot));
    }

    function enableDrag(sheet) {
        const panel = sheet.querySelector('.sheet-panel');
        const handle = sheet.querySelector('.sheet-header');
        if (!panel || !handle) return;

        let startY = 0, dy = 0, samples = [], dragging = false, pointerId = null;

        handle.addEventListener('pointerdown', e => {
            if (!MOBILE.matches || e.button !== 0 || e.target.closest('button, a, input')) return;
            pointerId = e.pointerId;
            startY = e.clientY;
            dy = 0;
            samples = [{ y: e.clientY, t: e.timeStamp }];
            dragging = false;
        });

        handle.addEventListener('pointermove', e => {
            if (e.pointerId !== pointerId) return;
            const delta = e.clientY - startY;
            if (!dragging) {
                if (Math.abs(delta) < 6) return; // histéresis antes de comprometer el gesto
                dragging = true;
                handle.setPointerCapture(pointerId);
                sheet.classList.add('is-dragging');
            }
            dy = delta >= 0 ? delta : rubberband(delta, panel.offsetHeight);
            panel.style.transform = `translateY(${dy}px)`;
            samples.push({ y: e.clientY, t: e.timeStamp });
            if (samples.length > 6) samples.shift();
        });

        const end = e => {
            if (e.pointerId !== pointerId) return;
            pointerId = null;
            if (!dragging) return;
            dragging = false;
            sheet.classList.remove('is-dragging');

            const first = samples[0], last = samples[samples.length - 1];
            const dt = Math.max(1, last.t - first.t);
            const velocity = ((last.y - first.y) / dt) * 1000; // px/s, positivo = hacia abajo
            const height = panel.offsetHeight;
            const projected = dy + project(velocity);

            if (projected > height * 0.45 && velocity > -200) {
                const remaining = Math.max(0, height - dy);
                const duration = velocity > 0 ? Math.min(0.32, Math.max(0.14, remaining / velocity)) : 0.26;
                close(sheet, { duration });
            } else {
                panel.style.transform = '';
            }
        };
        handle.addEventListener('pointerup', end);
        handle.addEventListener('pointercancel', end);
    }

    function init() {
        document.querySelectorAll('.sheet').forEach(sheet => {
            sheet.setAttribute('aria-hidden', 'true');
            enableDrag(sheet);

            const body = sheet.querySelector('.sheet-body');
            const header = sheet.querySelector('.sheet-header');
            if (body && header) {
                body.addEventListener('scroll', () => {
                    header.classList.toggle('is-scrolled', body.scrollTop > 2);
                }, { passive: true });
            }
        });

        document.addEventListener('click', e => {
            const opener = e.target.closest('[data-sheet-open]');
            if (opener) {
                e.preventDefault();
                open(opener.dataset.sheetOpen, opener);
                return;
            }
            const closer = e.target.closest('[data-sheet-close]');
            if (closer) {
                e.preventDefault();
                close(closer.closest('.sheet'));
            }
        });

        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && stack.length) {
                e.preventDefault();
                closeTop();
            }
        });
    }

    return { init, open, close };
})();

// ──────────────────────────────────────────────
// CONTROL SEGMENTADO
// ──────────────────────────────────────────────

function syncSegmented(seg) {
    let thumb = seg.querySelector('.segmented-thumb');
    if (!thumb) {
        thumb = document.createElement('span');
        thumb.className = 'segmented-thumb';
        thumb.setAttribute('aria-hidden', 'true');
        seg.prepend(thumb);
    }
    const checked = seg.querySelector('input:checked');
    const target = checked ? seg.querySelector(`label[for="${checked.id}"]`) : seg.querySelector('a[aria-current="true"]');
    if (!target || !target.offsetWidth) return;
    thumb.style.width = `${target.offsetWidth}px`;
    thumb.style.transform = `translateX(${target.offsetLeft}px)`;
    if (checked) seg.dataset.value = checked.value;
}

function setupSegmented() {
    document.querySelectorAll('.segmented').forEach(seg => {
        // Primera colocación sin animación
        syncSegmented(seg);
        const thumb = seg.querySelector('.segmented-thumb');
        if (thumb) {
            thumb.style.transition = 'none';
            requestAnimationFrame(() => requestAnimationFrame(() => { thumb.style.transition = ''; }));
        }

        seg.addEventListener('change', () => {
            syncSegmented(seg);
            const form = seg.closest('form');
            const tone = form && form.querySelector('.amount-field');
            if (tone && seg.classList.contains('type-switch')) tone.dataset.tone = seg.dataset.value;
        });

        // Enlaces: mover el pulgar al instante, antes de navegar
        seg.querySelectorAll('a').forEach(a => a.addEventListener('pointerdown', () => {
            seg.querySelectorAll('a').forEach(x => x.setAttribute('aria-current', 'false'));
            a.setAttribute('aria-current', 'true');
            syncSegmented(seg);
        }));

        if ('ResizeObserver' in window) new ResizeObserver(() => syncSegmented(seg)).observe(seg);
    });
}

// ──────────────────────────────────────────────
// CAMPOS QUE APARECEN (p.ej. periodicidad)
// ──────────────────────────────────────────────

function setupReveal() {
    document.querySelectorAll('[data-reveal]').forEach(toggle => {
        const target = document.getElementById(toggle.dataset.reveal);
        if (!target) return;
        const sync = () => {
            target.classList.toggle('is-open', toggle.checked);
            target.setAttribute('aria-hidden', toggle.checked ? 'false' : 'true');
            target.querySelectorAll('input, select').forEach(i => { i.tabIndex = toggle.checked ? 0 : -1; });
        };
        toggle.addEventListener('change', sync);
        sync();
    });
}

// ──────────────────────────────────────────────
// CONFIRMACIÓN DE ACCIONES DESTRUCTIVAS
// ──────────────────────────────────────────────

function setupConfirm() {
    const dialog = document.getElementById('confirm-dialog');
    if (!dialog) return;
    const title = dialog.querySelector('[data-confirm-title]');
    const detail = dialog.querySelector('[data-confirm-detail]');
    const accept = dialog.querySelector('[data-confirm-accept]');
    let pending = null;

    document.addEventListener('submit', e => {
        const form = e.target;
        if (!form.matches('form[data-confirm]')) return;
        e.preventDefault();
        pending = form;
        title.textContent = form.dataset.confirm;
        detail.textContent = form.dataset.confirmDetail || 'Esta acción no se puede deshacer.';
        accept.textContent = form.dataset.confirmAction || 'Eliminar';
        Sheets.open('confirm-dialog', e.submitter || form.querySelector('button'));
        setTimeout(() => accept.focus(), 80);
    });

    accept.addEventListener('click', () => {
        if (!pending) return;
        const form = pending;
        pending = null;
        accept.disabled = true;
        form.submit();
    });
}

// ──────────────────────────────────────────────
// NOTIFICACIONES
// ──────────────────────────────────────────────

function dismissToast(toast) {
    if (!toast || toast.classList.contains('is-leaving')) return;
    toast.classList.add('is-leaving');
    toast.addEventListener('animationend', () => toast.remove(), { once: true });
    setTimeout(() => toast.remove(), 400);
}

function setupToasts() {
    document.querySelectorAll('.toast').forEach((toast, i) => {
        toast.addEventListener('click', () => dismissToast(toast));
        setTimeout(() => dismissToast(toast), 4200 + i * 600);
    });
}

// ──────────────────────────────────────────────
// MINI TENDENCIAS (sparklines)
// ──────────────────────────────────────────────

function drawSparklines() {
    document.querySelectorAll('svg.spark[data-values]').forEach(svg => {
        let values;
        try { values = JSON.parse(svg.dataset.values); } catch { return; }
        if (!values || values.length < 2) { svg.remove(); return; }
        const w = 96, h = 28, pad = 4;
        const min = Math.min(...values), max = Math.max(...values);
        const span = max - min || 1;
        const pts = values.map((v, i) => [
            pad + (i / (values.length - 1)) * (w - pad * 2),
            h - pad - ((v - min) / span) * (h - pad * 2),
        ]);
        const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
        const area = `${line} L${pts[pts.length - 1][0].toFixed(1)},${h} L${pts[0][0].toFixed(1)},${h} Z`;
        const [lx, ly] = pts[pts.length - 1];
        svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
        svg.innerHTML = `<path class="area" d="${area}"/><path class="line" d="${line}"/><circle cx="${lx}" cy="${ly}" r="3.5"/>`;
    });
}

// ──────────────────────────────────────────────
// GRÁFICAS: tema compartido para Plotly
// Los colores salen de los tokens CSS, así el modo oscuro tiene sus propios pasos.
// ──────────────────────────────────────────────

const FinCharts = (() => {
    const renderers = [];
    const scheme = window.matchMedia('(prefers-color-scheme: dark)');

    function token(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }

    function theme() {
        return {
            ink: token('--ink'), ink2: token('--ink-2'), ink3: token('--ink-3'),
            surface: token('--surface'), grid: token('--chart-grid'), axis: token('--chart-axis'),
            series: [1, 2, 3, 4, 5, 6].map(i => token(`--series-${i}`)),
            flowIn: token('--flow-in'), flowOut: token('--flow-out'),
            critical: token('--critical'), font: token('--font'),
        };
    }

    function baseLayout(t, extra = {}) {
        const axis = {
            showgrid: false, zeroline: false, showline: false,
            tickfont: { size: 11, color: t.ink3 }, ticks: '', automargin: true,
            fixedrange: true,
        };
        return Object.assign({
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { family: t.font, size: 12, color: t.ink2 },
            separators: ', ',
            margin: { l: 8, r: 12, t: 8, b: 8 },
            showlegend: false,
            hovermode: 'x unified',
            hoverlabel: {
                bgcolor: t.surface, bordercolor: t.axis,
                font: { family: t.font, size: 12, color: t.ink },
                align: 'left',
            },
            xaxis: Object.assign({}, axis, {
                type: 'date', showspikes: true, spikemode: 'across', spikesnap: 'cursor',
                spikethickness: 1, spikecolor: t.axis, spikedash: 'solid',
                hoverformat: '%d %b %Y',
            }),
            yaxis: Object.assign({}, axis, {
                showgrid: true, gridcolor: t.grid, gridwidth: 1,
                tickprefix: '$ ', tickformat: '~s', side: 'right',
            }),
        }, extra);
    }

    const config = { responsive: true, displayModeBar: false, locale: 'es' };

    function register(fn) {
        renderers.push(fn);
        fn(theme());
    }

    function rerender() {
        const t = theme();
        renderers.forEach(fn => fn(t));
    }

    scheme.addEventListener('change', rerender);

    return { register, rerender, theme, baseLayout, config, formatCompact, formatCurrency };
})();

// Plotly en español (meses y días)
if (window.Plotly) {
    Plotly.register({
        moduleType: 'locale',
        name: 'es',
        dictionary: {},
        format: {
            days: ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'],
            shortDays: ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'],
            months: ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'],
            shortMonths: ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'],
            date: '%d/%m/%Y',
            decimal: ',',
            thousands: ' ',
        },
    });
}

// ──────────────────────────────────────────────
// BARRA SUPERIOR (móvil): borde al hacer scroll
// ──────────────────────────────────────────────

function setupTopbar() {
    const bar = document.querySelector('.topbar');
    if (!bar) return;
    const sync = () => bar.classList.toggle('is-scrolled', window.scrollY > 4);
    window.addEventListener('scroll', sync, { passive: true });
    sync();
}

// ──────────────────────────────────────────────
// INICIALIZACIÓN
// ──────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    setupCurrencyInputs();
    Sheets.init();
    setupSegmented();
    setupReveal();
    setupConfirm();
    setupToasts();
    drawSparklines();
    setupTopbar();

    // Abrir una hoja desde la URL (#sheet-id), útil tras redirecciones
    if (location.hash && document.getElementById(location.hash.slice(1))?.classList.contains('sheet')) {
        Sheets.open(location.hash.slice(1));
    }
});
