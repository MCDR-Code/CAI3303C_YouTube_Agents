"""Small inline-SVG bar charts for the dashboard and the weekly report (no JS libraries).

Colors follow the data's job:
- profit per video is diverging (gain vs loss): blue for profit, red for loss,
  around a zero baseline;
- cost per agent is a magnitude: one hue (blue).
Each bar carries data-tip text for the hover tooltip, and every chart has a
table next to it, so color is never the only way to read a value.
"""
from __future__ import annotations

from html import escape

ROW_H = 30
BAR_H = 18


def _money(v: float, digits: int = 2) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.{digits}f}"


def diverging_bars(rows: list[dict], label_key: str, value_key: str, tip_fn, width: int = 760,
                   label_w: int = 80) -> str:
    """Horizontal bars around a zero line (profit/loss)."""
    if not rows:
        return "<p class='muted'>No data yet.</p>"
    vals = [r[value_key] for r in rows]
    lo, hi = min(0.0, min(vals)), max(0.0, max(vals))
    span = (hi - lo) or 1.0
    plot_x, plot_w = label_w + 10, width - label_w - 90
    x0 = plot_x + (0 - lo) / span * plot_w
    h = len(rows) * ROW_H + 30
    parts = [f'<svg class="chart" viewBox="0 0 {width} {h}" width="100%" role="img" '
             f'aria-label="Profit per video bar chart">']
    for i, r in enumerate(rows):
        y = 10 + i * ROW_H
        v = r[value_key]
        x1 = plot_x + (v - lo) / span * plot_w
        left, w = (min(x0, x1), max(2.0, abs(x1 - x0)))
        cls = "pos" if v >= 0 else "neg"
        label = escape(str(r[label_key]))
        parts.append(f'<text class="lbl" x="{label_w}" y="{y + BAR_H - 4}" text-anchor="end">{label}</text>')
        parts.append(f'<rect class="bar {cls}" x="{left:.1f}" y="{y}" width="{w:.1f}" height="{BAR_H}" rx="4" '
                     f'data-tip="{escape(tip_fn(r))}"/>')
        # value label sits on the open side of the zero line, so it never hits the row label
        tx, anchor = (x1 + 6, "start") if v >= 0 else (x0 + 6, "start")
        parts.append(f'<text class="val" x="{tx:.1f}" y="{y + BAR_H - 4}" text-anchor="{anchor}">{_money(v)}</text>')
    parts.append(f'<line class="zero" x1="{x0:.1f}" x2="{x0:.1f}" y1="4" y2="{h - 20}"/>')
    parts.append(f'<text class="axis" x="{x0:.1f}" y="{h - 4}" text-anchor="middle">$0</text>')
    parts.append("</svg>")
    return "".join(parts)


def magnitude_bars(rows: list[dict], label_key: str, value_key: str, tip_fn, width: int = 520,
                   label_w: int = 120, digits: int = 4) -> str:
    """Horizontal bars from zero, one hue (cost)."""
    if not rows:
        return "<p class='muted'>No data yet.</p>"
    mx = max(r[value_key] for r in rows) or 1.0
    plot_x, plot_w = label_w + 10, width - label_w - 100
    h = len(rows) * ROW_H + 30
    parts = [f'<svg class="chart" viewBox="0 0 {width} {h}" width="100%" role="img" '
             f'aria-label="Cost per agent bar chart">']
    for i, r in enumerate(rows):
        y = 10 + i * ROW_H
        v = r[value_key]
        w = max(2.0, v / mx * plot_w)
        parts.append(f'<text class="lbl" x="{label_w}" y="{y + BAR_H - 4}" text-anchor="end">'
                     f'{escape(str(r[label_key]))}</text>')
        parts.append(f'<rect class="bar mag" x="{plot_x}" y="{y}" width="{w:.1f}" height="{BAR_H}" rx="4" '
                     f'data-tip="{escape(tip_fn(r))}"/>')
        parts.append(f'<text class="val" x="{plot_x + w + 6:.1f}" y="{y + BAR_H - 4}">{_money(v, digits)}</text>')
    parts.append(f'<line class="zero" x1="{plot_x}" x2="{plot_x}" y1="4" y2="{h - 20}"/>')
    parts.append("</svg>")
    return "".join(parts)


CHART_CSS = """
.viz-root{color-scheme:light;--surface-1:#fcfcfb;--text-primary:#0b0b0b;--text-secondary:#52514e;
 --muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--pos:#2a78d6;--neg:#e34948;--mag:#2a78d6}
@media (prefers-color-scheme: dark){.viz-root{color-scheme:dark;--surface-1:#1a1a19;--text-primary:#f0efec;
 --text-secondary:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--pos:#3987e5;--neg:#e66767;--mag:#3987e5}}
.chart text{font:13px system-ui,-apple-system,"Segoe UI",sans-serif;fill:var(--text-secondary)}
.chart text.val{fill:var(--text-primary);font-variant-numeric:tabular-nums}
.chart text.axis{fill:var(--muted);font-size:11px}
.chart .zero{stroke:var(--axis);stroke-width:1.5}
.chart .bar{stroke:var(--surface-1);stroke-width:2}
.chart .bar.pos{fill:var(--pos)} .chart .bar.neg{fill:var(--neg)} .chart .bar.mag{fill:var(--mag)}
.chart .bar:hover{opacity:.8}
#tip{position:fixed;pointer-events:none;background:var(--text-primary);color:var(--surface-1);padding:6px 9px;
 border-radius:6px;font:12px system-ui,sans-serif;white-space:pre;display:none;z-index:9}
"""

TOOLTIP_JS = """
<div id="tip"></div>
<script>
(function(){const t=document.getElementById('tip');
document.querySelectorAll('[data-tip]').forEach(el=>{
 el.addEventListener('mousemove',e=>{t.textContent=el.dataset.tip;t.style.display='block';
   t.style.left=(e.clientX+14)+'px';t.style.top=(e.clientY+10)+'px';});
 el.addEventListener('mouseleave',()=>{t.style.display='none';});});})();
</script>
"""
