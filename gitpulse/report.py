"""Render the statistics dict as a single self-contained HTML file."""

import datetime as _dt
import math

from . import __version__, svg
from .i18n import get
from .svg import esc, fmt_int

CSS = """
:root{--bg:#fff;--fg:#1f2328;--muted:#59636e;--line:#d1d9e0;--soft:#f3f5f7;--a:#0072b2;--add:#0072b2;--del:#c25400}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--muted:#9aa4af;--line:#30363d;--soft:#161b22;--a:#56b4e9;--add:#56b4e9;--del:#e69f00}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC","Microsoft JhengHei",sans-serif}
main{max-width:860px;margin:0 auto;padding:28px 16px 48px}
h1{font-size:26px;line-height:1.25;margin:0 0 4px;overflow-wrap:anywhere}
h2{font-size:19px;line-height:1.3;margin:0 0 6px}
.meta{color:var(--muted);font-size:14px;margin:0 0 4px}
.note{border-left:3px solid var(--del);padding:2px 0 2px 12px;margin:14px 0;font-size:15px}
section{margin-top:40px;padding-top:20px;border-top:1px solid var(--line)}
.insight{margin:0 0 12px}
.sub{color:var(--muted);font-size:14px;margin:8px 0 0}
h3{font-size:15px;margin:22px 0 4px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin:22px 0 0;border:1px solid var(--line);background:var(--line)}
.stat{padding:12px 14px;min-width:0;background:var(--bg)}
.stat .k{color:var(--muted);font-size:13px}
.stat .v{font-size:24px;line-height:1.3;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.stat .v.sm{font-size:17px}
.stat .s{color:var(--muted);font-size:13px;overflow-wrap:anywhere}
.chart+.chart{margin-top:18px}
.chart{display:block;width:100%;height:auto;font-family:inherit}
.bar{fill:var(--a)}.add{fill:var(--add)}.del{fill:var(--del)}
.grid{stroke:var(--line);stroke-width:1}.axis{stroke:var(--muted);stroke-width:1}
.tick,.axis-title,.value{fill:var(--muted);font-size:12px}
.rowlabel{fill:var(--fg);font-size:13px}
.cell{fill:var(--a)}.cell0{fill:var(--soft);stroke:var(--line);stroke-width:.5}
[data-tip]:hover{opacity:.75}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}
th,td{padding:6px 10px 6px 0;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--muted);font-weight:600;font-size:13px}
th.num,td.num{text-align:right;padding-right:14px}
table.sortable th{cursor:pointer}
table.sortable th:hover{color:var(--fg)}
td.wrap{white-space:normal;overflow-wrap:anywhere;min-width:110px}
.mini{display:inline-block;height:8px;background:var(--a);vertical-align:middle;margin-right:6px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:0 32px}
#tip{position:fixed;display:none;z-index:9;pointer-events:none;background:var(--fg);color:var(--bg);font-size:13px;padding:4px 8px;border-radius:3px;max-width:80vw}
footer{margin-top:44px;color:var(--muted);font-size:13px}
@media (max-width:640px){
 .stats{grid-template-columns:repeat(2,1fr)}
 .pair{grid-template-columns:1fr}
 h1{font-size:22px}
}
"""

JS = """
(function(){
var t=document.getElementById('tip');
function show(e){var n=e.target.closest&&e.target.closest('[data-tip]');
 if(!n){t.style.display='none';return}
 t.textContent=n.getAttribute('data-tip');t.style.display='block';
 var x=e.clientX+12,y=e.clientY+16,w=t.offsetWidth;
 if(x+w>window.innerWidth-4)x=window.innerWidth-w-4;
 if(x<4)x=4;t.style.left=x+'px';t.style.top=y+'px'}
document.addEventListener('mousemove',show);
document.addEventListener('click',show);
document.addEventListener('scroll',function(){t.style.display='none'},true);
var ths=document.querySelectorAll('table.sortable th');
Array.prototype.forEach.call(ths,function(th){
 function sort(){var i=th.cellIndex,table=th.closest('table'),tb=table.tBodies[0];
  var rows=Array.prototype.slice.call(tb.rows);
  var asc=th.getAttribute('aria-sort')!=='ascending';
  Array.prototype.forEach.call(table.querySelectorAll('th'),function(o){o.removeAttribute('aria-sort')});
  th.setAttribute('aria-sort',asc?'ascending':'descending');
  rows.sort(function(a,b){var x=a.cells[i].getAttribute('data-v'),y=b.cells[i].getAttribute('data-v');
   var nx=parseFloat(x),ny=parseFloat(y);
   var c=(isNaN(nx)||isNaN(ny))?x.localeCompare(y):nx-ny;return asc?c:-c});
  rows.forEach(function(r){tb.appendChild(r)})}
 th.setAttribute('tabindex','0');
 th.addEventListener('click',sort);
 th.addEventListener('keydown',function(e){if(e.key==='Enter')sort()});
});
})();
"""


# --------------------------------------------------------------------------
# helpers (also unit-tested)
# --------------------------------------------------------------------------

def pct(part, whole, digits=0):
    if not whole:
        return 0
    v = 100.0 * part / whole
    return round(v, digits) if digits else int(round(v))


def week_labels(weeks, target=6):
    """Pick evenly spaced x-axis labels for a list of week-start dates."""
    n = len(weeks)
    if n == 0:
        return {}
    step = max(1, math.ceil(n / float(target)))
    cut = 7 if n > 26 else None
    out = {}
    for i in range(0, n, step):
        w = weeks[i]
        out[i] = w[:7] if cut else w[5:]
    return out


def language_rows(languages, limit=10):
    """Keep the ``limit`` biggest languages; fold the rest into ``Other``."""
    if len(languages) <= limit:
        return list(languages)
    head = list(languages[:limit - 1])
    rest = languages[limit - 1:]
    lines = sum(r["lines"] for r in rest)
    files = sum(r["files"] for r in rest)
    percent = sum(r["percent"] for r in rest)
    other = next((r for r in head if r["name"] == "Other"), None)
    if other:
        head.remove(other)
        lines += other["lines"]
        files += other["files"]
        percent += other["percent"]
    head.append({"name": "Other", "lines": lines, "files": files, "percent": percent})
    return head


def heat_summary(grid):
    """Return ``(weekday, hour, count, weekend_pct, night_pct)`` for the busiest slot."""
    total = sum(sum(r) for r in grid)
    best = (0, 0, -1)
    for d, row in enumerate(grid):
        for h, v in enumerate(row):
            if v > best[2]:
                best = (d, h, v)
    weekend = sum(grid[5]) + sum(grid[6])
    night = sum(row[h] for row in grid for h in (22, 23, 0, 1, 2, 3, 4))
    return best[0], best[1], best[2], pct(weekend, total), pct(night, total)


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

class _Ctx:
    def __init__(self, data, lang):
        self.d = data
        self.lang = lang
        self.t = get(lang)

    def s(self, key, **kw):
        return self.t[key].format(**kw) if kw else self.t[key]


def _section(title, insight, chart, sub=None):
    parts = ["<section><h2>%s</h2>" % esc(title)]
    if insight:
        parts.append('<p class="insight">%s</p>' % esc(insight))
    parts.append(chart)
    if sub:
        parts.append('<p class="sub">%s</p>' % esc(sub))
    parts.append("</section>")
    return "".join(parts)


def _stat(k, v, sub=None, small=False):
    return '<div class="stat"><div class="k">%s</div><div class="v%s">%s</div>%s</div>' % (
        esc(k), " sm" if small else "", esc(v),
        '<div class="s">%s</div>' % esc(sub) if sub else "")


def _overview(c):
    o = c.d["overview"]
    cells = [
        _stat(c.s("ov_commits"), fmt_int(o["commits"]),
              c.s("ov_merges", n=fmt_int(o["merges"])) if o["merges"] else None),
        _stat(c.s("ov_authors"), fmt_int(o["authors"])),
        _stat(c.s("ov_days"), fmt_int(o["active_days"])),
        _stat(c.s("ov_added") + " / " + c.s("ov_deleted"),
              "+%s / -%s" % (fmt_int(o["added"]), fmt_int(o["deleted"])), small=True),
        _stat(c.s("ov_first"), o["first"]["date"], c.s("by", a=o["first"]["author"]), small=True),
        _stat(c.s("ov_last"), o["last"]["date"], c.s("by", a=o["last"]["author"]), small=True),
    ]
    return '<div class="stats">%s</div>' % "".join(cells)


def _weekly(c):
    weeks = c.d["weekly"]
    names = [w["week"] for w in weeks]
    labels = week_labels(names)
    commits = [w["commits"] for w in weeks]
    tips = [c.s("wk_fmt", w=w["week"], c=fmt_int(w["commits"]), a=fmt_int(w["added"]),
                d=fmt_int(w["deleted"])) for w in weeks]
    best = max(weeks, key=lambda w: (w["commits"], w["week"]))
    avg = c.d["overview"]["commits"] / float(len(weeks))
    insight = c.s("in_wk", w=best["week"], c=fmt_int(best["commits"]), avg="%.1f" % avg)
    insight += " " + c.s("in_lines", a=fmt_int(c.d["overview"]["added"]),
                         d=fmt_int(c.d["overview"]["deleted"]),
                         net=fmt_int(c.d["overview"]["added"] - c.d["overview"]["deleted"]))
    top = svg.column_chart(commits, tips, labels, c.s("y_commits"),
                           c.s("s_weekly") + " - " + c.s("y_commits"))
    bottom = svg.diverging_chart(
        [w["added"] for w in weeks], [w["deleted"] for w in weeks], tips, labels,
        c.s("y_lines"), c.s("s_weekly") + " - " + c.s("y_lines"),
        [("add", c.s("added")), ("del", c.s("deleted"))])
    return _section(c.s("s_weekly"), insight, top + bottom, c.s("s_weekly_sub"))


def _heat(c):
    grid = c.d["heatmap"]
    days = c.t["days"]
    d, h, n, we, night = heat_summary(grid)
    insight = c.s("in_heat", d=days[d], h=h, n=fmt_int(n), we=we, night=night)
    vmax = max(max(r) for r in grid)
    chart = svg.heatmap(
        grid, days, lambda dd, hh, v: c.s("hm_tip", d=days[dd], h=hh, n=fmt_int(v)),
        c.s("s_heat"), (c.s("less"), c.s("more", n=fmt_int(vmax))))
    return _section(c.s("s_heat"), insight, chart, c.s("s_heat_sub"))


def _table(headers, rows, sortable=True):
    """``headers``: list of (text, numeric). ``rows``: list of lists of (display, sortkey, cls)."""
    out = ['<div class="tablewrap"><table%s><thead><tr>' % (' class="sortable"' if sortable else "")]
    for text, num in headers:
        out.append('<th%s>%s</th>' % (' class="num"' if num else "", esc(text)))
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for cell in row:
            html, key, cls = cell
            out.append('<td class="%s" data-v="%s">%s</td>' % (cls, esc(key), html))
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _authors(c, limit=30):
    authors = c.d["authors"]
    total = c.d["overview"]["commits"]
    top = authors[0]
    p3 = pct(sum(a["commits"] for a in authors[:3]), total)
    insight = c.s("in_authors", n=fmt_int(len(authors)), top=top["name"],
                  c=fmt_int(top["commits"]), p=pct(top["commits"], total), p3=p3)
    headers = [(c.s("col_rank"), True), (c.s("col_author"), False), (c.s("col_commits"), True),
               (c.s("col_added"), True), (c.s("col_deleted"), True),
               (c.s("col_first"), False), (c.s("col_last"), False)]
    rows = []
    for i, a in enumerate(authors[:limit], 1):
        rows.append([
            (str(i), i, "num"),
            (esc(a["name"]), a["name"].lower(), "wrap"),
            (fmt_int(a["commits"]), a["commits"], "num"),
            ("+" + fmt_int(a["added"]), a["added"], "num"),
            ("-" + fmt_int(a["deleted"]), a["deleted"], "num"),
            (esc(a["first"]), a["first"], ""),
            (esc(a["last"]), a["last"], ""),
        ])
    return _section(c.s("s_authors"), insight, _table(headers, rows), c.s("s_authors_sub"))


def _files(c):
    touch = c.d["hot_files_by_touches"]
    churn = c.d["hot_files_by_churn"]
    if not touch:
        return _section(c.s("s_files"), None, '<p class="sub">%s</p>' % esc(c.s("no_data")))
    a, b = touch[0], churn[0]
    insight = c.s("in_files", a=a["path"], ta=fmt_int(a["touches"]), b=b["path"],
                  cb=fmt_int(b["churn"]))
    rows1 = [(f["path"], [(f["touches"], "bar")], c.s("times", n=fmt_int(f["touches"])),
              "%s: +%s / -%s" % (f["path"], fmt_int(f["added"]), fmt_int(f["deleted"])))
             for f in touch[:10]]
    rows2 = [(f["path"], [(f["added"], "add"), (f["deleted"], "del")],
              c.s("lines", n=fmt_int(f["churn"])),
              "%s: +%s / -%s" % (f["path"], fmt_int(f["added"]), fmt_int(f["deleted"])))
             for f in churn[:10]]
    body = ("<h3>%s</h3>%s<h3>%s</h3>%s" % (
        esc(c.s("files_touch")), svg.hbar_chart(rows1, c.s("files_touch")),
        esc(c.s("files_churn")), svg.hbar_chart(rows2, c.s("files_churn"))))
    return _section(c.s("s_files"), insight, body)


def _dirname(c, name):
    return c.s("root_dir") if name == "(root)" else name


def _dirs(c):
    dirs = c.d["dirs"][:12]
    if not dirs:
        return ""
    total = sum(d["churn"] for d in c.d["dirs"]) or 1
    insight = c.s("in_dirs", d=_dirname(c, dirs[0]["path"]), p=pct(dirs[0]["churn"], total))
    rows = [(_dirname(c, d["path"]), [(d["added"], "add"), (d["deleted"], "del")],
             "+%s / -%s" % (fmt_int(d["added"]), fmt_int(d["deleted"])),
             "%s: %s" % (d["path"], c.s("lines", n=fmt_int(d["churn"])))) for d in dirs]
    return _section(c.s("s_dirs"), insight, svg.hbar_chart(rows, c.s("s_dirs")), c.s("s_dirs_sub"))


def _langs(c):
    langs = c.d["languages"]
    if not langs:
        return _section(c.s("s_langs"), None, '<p class="sub">%s</p>' % esc(c.s("no_data")))
    top = langs[0]
    insight = c.s("in_langs", l=top["name"], p="%.1f" % top["percent"], n=fmt_int(top["lines"]),
                  k=len(langs))
    rows = [(r["name"], [(r["lines"], "bar")],
             "%s · %.1f%%" % (fmt_int(r["lines"]), r["percent"]),
             "%s: %s, %s files" % (r["name"], c.s("lines", n=fmt_int(r["lines"])),
                                   fmt_int(r["files"])))
            for r in language_rows(langs)]
    return _section(c.s("s_langs"), insight, svg.hbar_chart(rows, c.s("s_langs")), c.s("s_langs_sub"))


def _bus(c):
    bf = c.d["bus_factor"]
    dirs = bf["dirs"]
    if not dirs:
        return ""
    single = sum(1 for d in dirs if d["bus_factor"] == 1)
    insight = c.s("in_bus", n=bf["overall"], k=single)
    headers = [(c.s("col_dir"), False), (c.s("col_churn"), True), (c.s("col_nauthors"), True),
               (c.s("col_bus"), True), (c.s("col_top"), False), (c.s("col_share"), False)]
    rows = []
    for d in dirs:
        share = d["top_share"] * 100
        bar = '<span class="mini" style="width:%dpx"></span>%d%%' % (round(share * 0.6), round(share))
        rows.append([
            (esc(_dirname(c, d["path"])), d["path"].lower(), "wrap"),
            (fmt_int(d["churn"]), d["churn"], "num"),
            (fmt_int(d["authors"]), d["authors"], "num"),
            (str(d["bus_factor"]), d["bus_factor"], "num"),
            (esc(d["top_author"]), d["top_author"].lower(), "wrap"),
            (bar, "%.1f" % share, ""),
        ])
    return _section(c.s("s_bus"), insight, _table(headers, rows), c.s("s_bus_sub"))


def _msgs(c):
    m = c.d["messages"]
    if not m["count"]:
        return ""
    cc = pct(m["conventional"], m["count"])
    t = ""
    if m["types"]:
        t = c.s("in_msgs_t", t=m["types"][0][0], n=fmt_int(m["types"][0][1]))
    insight = c.s("in_msgs", avg="%.0f" % m["avg_length"], cc=cc, t=t)
    parts = []
    if m["types"]:
        rows = [(k, [(v, "bar")], c.s("commits_n", n=fmt_int(v)), None) for k, v in m["types"]]
        parts.append("<div><h3>%s</h3>%s</div>" % (
            esc(c.s("msg_types")), svg.hbar_chart(rows, c.s("msg_types"), row_h=34)))
    rows = [(k, [(v, "bar")], c.s("commits_n", n=fmt_int(v)), None) for k, v in m["first_words"]]
    parts.append("<div><h3>%s</h3>%s</div>" % (
        esc(c.s("msg_words")), svg.hbar_chart(rows, c.s("msg_words"), row_h=34)))
    body = '<div class="pair">%s</div>' % "".join(parts)
    return _section(c.s("s_msgs"), insight, body, c.s("s_msgs_sub"))


def render(data, lang="zh", generated=None):
    """Return the full HTML document for ``data``."""
    c = _Ctx(data, lang)
    t = c.t
    gen = generated or _dt.date.today().isoformat()
    rng = ""
    if data.get("since"):
        rng += t["range_since"].format(v=data["since"])
    if data.get("until"):
        rng += t["range_until"].format(v=data["until"])
    meta = t["meta"].format(ref=data["ref"], range=rng, ver=__version__, gen=gen)
    body = ['<h1>%s</h1><p class="meta">%s</p>' % (esc(data["repo"]), esc(meta))]
    if data.get("excludes"):
        body.append('<p class="meta">%s</p>' % esc(t["excluded"].format(v=", ".join(data["excludes"]))))
    if data.get("shallow"):
        body.append('<p class="note">%s</p>' % esc(t["shallow"]))
    if data.get("empty") or not data["overview"]["commits"]:
        body.append('<p class="note">%s</p>' % esc(t["empty"]))
    else:
        body += [_overview(c), _weekly(c), _heat(c), _authors(c), _files(c), _dirs(c),
                 _langs(c), _bus(c), _msgs(c)]
    body.append("<footer>%s</footer>" % esc(t["footer"].format(ver=__version__)))
    return (
        "<!doctype html>\n<html lang=\"%s\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"color-scheme\" content=\"light dark\">"
        "<title>%s</title><style>%s</style></head><body><main>%s</main>"
        "<div id=\"tip\"></div><script>%s</script></body></html>\n"
        % (t["html_lang"], esc(t["title"].format(repo=data["repo"])), CSS, "".join(body), JS))
