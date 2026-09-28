"""Small helpers for generating inline SVG charts (no third-party code).

Colors are never hard-coded here: elements get CSS classes (``bar``, ``add``,
``del``, ``grid``...) and the report stylesheet maps them to theme variables,
so the same SVG works in light and dark mode.
"""

import math
from html import escape

W = 560  # default viewBox width; charts scale with their container


def esc(s):
    return escape(str(s), quote=True)


def fmt_int(n):
    return "{:,}".format(int(round(n)))


def fmt_compact(n):
    """Short axis label: 950, 1.2k, 34k, 1.5M."""
    n = float(n)
    a = abs(n)
    if a >= 1e6:
        v, suf = n / 1e6, "M"
    elif a >= 1e3:
        v, suf = n / 1e3, "k"
    else:
        return str(int(round(n)))
    s = ("%.1f" % v).rstrip("0").rstrip(".") if abs(v) < 10 else "%d" % round(v)
    return s + suf


def nice_step(raw):
    """Round a raw step up to 1, 2, 2.5, 5 or 10 times a power of ten."""
    if raw <= 0:
        return 1.0
    exp = math.floor(math.log10(raw))
    base = 10 ** exp
    frac = raw / base
    for nice in (1, 2, 5, 10):
        if frac <= nice + 1e-9:
            return nice * base
    return 10 * base


def nice_ticks(vmax, target=4):
    """Return ``(ticks, top)``: evenly spaced ticks from 0 covering ``vmax``."""
    if vmax <= 0:
        return [0, 1], 1
    step = nice_step(vmax / target)
    count = int(math.ceil(vmax / step - 1e-9))
    ticks = [i * step for i in range(count + 1)]
    ticks = [int(t) if float(t).is_integer() else t for t in ticks]
    return ticks, ticks[-1]


def scale(d0, d1, r0, r1):
    """Linear scale mapping ``[d0, d1]`` to ``[r0, r1]``."""
    span = d1 - d0

    def f(v):
        if span == 0:
            return r0
        return r0 + (v - d0) * (r1 - r0) / span
    return f


def truncate_middle(s, n):
    if len(s) <= n:
        return s
    keep = n - 1
    head = keep // 2 + keep % 2
    tail = keep // 2
    return s[:head] + "…" + (s[-tail:] if tail else "")


def _n(v):
    """Compact number formatting for SVG coordinates."""
    s = "%.2f" % v
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def svg_open(width, height, label):
    return ('<svg class="chart" viewBox="0 0 %s %s" role="img" aria-label="%s" '
            'preserveAspectRatio="xMidYMin meet">' % (_n(width), _n(height), esc(label)))


def text(x, y, s, cls="tick", anchor="start"):
    return '<text class="%s" x="%s" y="%s" text-anchor="%s">%s</text>' % (
        cls, _n(x), _n(y), anchor, esc(s))


def rect(x, y, w, h, cls, tip=None, style=None):
    extra = ' data-tip="%s"' % esc(tip) if tip else ""
    if style:
        extra += ' style="%s"' % style
    return '<rect class="%s" x="%s" y="%s" width="%s" height="%s"%s/>' % (
        cls, _n(x), _n(y), _n(max(w, 0)), _n(max(h, 0)), extra)


def line(x1, y1, x2, y2, cls="grid"):
    return '<line class="%s" x1="%s" y1="%s" x2="%s" y2="%s"/>' % (
        cls, _n(x1), _n(y1), _n(x2), _n(y2))


def column_chart(values, tips, x_labels, y_title, label, height=190, width=W, cls="bar",
                 left=42, right=6, top=22, bottom=22):
    """Vertical bars. ``x_labels`` maps bar index -> axis label."""
    n = len(values)
    vmax = max(values) if values else 0
    ticks, ymax = nice_ticks(vmax)
    pw = width - left - right
    ph = height - top - bottom
    ys = scale(0, ymax, top + ph, top)
    out = [svg_open(width, height, label), text(0, 12, y_title, "axis-title")]
    for t in ticks:
        y = ys(t)
        out.append(line(left, y, width - right, y, "grid" if t else "axis"))
        out.append(text(left - 6, y + 4, fmt_compact(t), "tick", "end"))
    if n:
        bw = pw / n
        gap = 1 if bw > 4 else 0
        for i, v in enumerate(values):
            h = ys(0) - ys(v)
            if v > 0:
                h = max(h, 1)
            out.append(rect(left + i * bw, ys(0) - h, bw - gap, h, cls, tips[i]))
        for i, lab in sorted(x_labels.items()):
            x = left + i * bw
            anchor = "end" if x > width - 40 else "start"
            out.append(text(x, height - 6, lab, "tick", anchor))
    out.append("</svg>")
    return "".join(out)


def diverging_chart(added, deleted, tips, x_labels, y_title, label, legend,
                    height=230, width=W, left=42, right=6, top=22, bottom=22):
    """Additions above the zero line, deletions below it (shared scale)."""
    n = len(added)
    vmax = max(max(added, default=0), max(deleted, default=0))
    ticks, ymax = nice_ticks(vmax, 3)
    pw = width - left - right
    ph = height - top - bottom
    ys = scale(-ymax, ymax, top + ph, top)
    out = [svg_open(width, height, label), text(0, 12, y_title, "axis-title")]
    lx = width - right
    for cls, name in reversed(legend):
        tw = 14 + sum(12 if ord(ch) > 255 else 7 for ch in name)
        lx -= tw
        out.append(rect(lx, 4, 9, 9, cls))
        out.append(text(lx + 13, 12, name, "axis-title"))
        lx -= 10
    for t in ticks:
        for sign in ((1, -1) if t else (1,)):
            y = ys(sign * t)
            out.append(line(left, y, width - right, y, "grid" if t else "axis"))
            out.append(text(left - 6, y + 4, fmt_compact(t), "tick", "end"))
    if n:
        bw = pw / n
        gap = 1 if bw > 4 else 0
        y0 = ys(0)
        for i in range(n):
            if added[i] > 0:
                h = max(y0 - ys(added[i]), 1)
                out.append(rect(left + i * bw, y0 - h, bw - gap, h, "add", tips[i]))
            if deleted[i] > 0:
                h = max(ys(-deleted[i]) - y0, 1)
                out.append(rect(left + i * bw, y0, bw - gap, h, "del", tips[i]))
        for i, lab in sorted(x_labels.items()):
            x = left + i * bw
            anchor = "end" if x > width - 40 else "start"
            out.append(text(x, height - 6, lab, "tick", anchor))
    out.append("</svg>")
    return "".join(out)


def heatmap(grid, day_labels, tip_fn, label, legend_labels, width=W, left=34, top=6):
    """7 x 24 grid; cell opacity encodes the count (sqrt scale)."""
    vmax = max((max(r) for r in grid), default=0)
    pw = width - left - 4
    cell = pw / 24.0
    gap = 2
    height = top + 7 * cell + 40
    out = [svg_open(width, height, label)]
    for d in range(7):
        y = top + d * cell
        out.append(text(left - 6, y + cell / 2 + 4, day_labels[d], "tick", "end"))
        for h in range(24):
            v = grid[d][h]
            x = left + h * cell
            if v == 0:
                out.append(rect(x, y, cell - gap, cell - gap, "cell0", tip_fn(d, h, v)))
            else:
                op = 0.14 + 0.86 * math.sqrt(v / vmax)
                out.append(rect(x, y, cell - gap, cell - gap, "cell", tip_fn(d, h, v),
                                "fill-opacity:%.2f" % op))
    ybase = top + 7 * cell
    for h in range(0, 24, 3):
        out.append(text(left + h * cell, ybase + 14, "%02d" % h, "tick"))
    # legend
    ly = ybase + 26
    lx = left
    out.append(text(lx, ly + 8, legend_labels[0], "tick"))
    lx += sum(12 if ord(ch) > 255 else 7 for ch in legend_labels[0]) + 8
    for k in range(5):
        op = 0.14 + 0.86 * math.sqrt(k / 4.0) if k else None
        if op is None:
            out.append(rect(lx, ly, 12, 12, "cell0"))
        else:
            out.append(rect(lx, ly, 12, 12, "cell", None, "fill-opacity:%.2f" % op))
        lx += 15
    out.append(text(lx + 3, ly + 9, legend_labels[1], "tick"))
    out.append("</svg>")
    return "".join(out)


def hbar_chart(rows, label, width=460, max_label=52, row_h=36, value_room=None):
    """Horizontal bars with the label above each bar.

    ``rows`` is a list of ``(label, segments, value_text, tip)`` where
    ``segments`` is a list of ``(value, css_class)`` drawn side by side.
    """
    if value_room is None:
        value_room = 8 + 7 * max((len(r[2]) for r in rows), default=8)
    totals = [sum(v for v, _ in r[1]) for r in rows]
    vmax = max(totals, default=0) or 1
    avail = width - value_room
    height = max(len(rows), 1) * row_h + 4
    out = [svg_open(width, height, label)]
    for i, (name, segs, vtext, tip) in enumerate(rows):
        y = i * row_h
        out.append('<g data-tip="%s">' % esc(tip) if tip else "<g>")
        out.append(text(0, y + 13, truncate_middle(name, max_label), "rowlabel"))
        x = 0.0
        for v, cls in segs:
            w = v / vmax * avail
            if v > 0:
                w = max(w, 1.5)
            out.append(rect(x, y + 19, w, 11, cls))
            x += w
        out.append(text(x + 6, y + 29, vtext, "value"))
        out.append("</g>")
    out.append("</svg>")
    return "".join(out)
