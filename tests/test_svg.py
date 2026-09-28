import unittest
from html.parser import HTMLParser

from gitpulse import svg


class TicksTest(unittest.TestCase):
    def test_zero_max(self):
        self.assertEqual(svg.nice_ticks(0), ([0, 1], 1))

    def test_small(self):
        ticks, top = svg.nice_ticks(37)
        self.assertEqual(ticks, [0, 10, 20, 30, 40])
        self.assertEqual(top, 40)

    def test_covers_max_and_starts_at_zero(self):
        for v in (1, 3, 7, 99, 100, 101, 1234, 56789, 1e6):
            ticks, top = svg.nice_ticks(v)
            self.assertEqual(ticks[0], 0)
            self.assertGreaterEqual(top, v)
            self.assertLessEqual(len(ticks), 8)

    def test_even_spacing(self):
        ticks, _ = svg.nice_ticks(1234)
        steps = {b - a for a, b in zip(ticks, ticks[1:])}
        self.assertEqual(len(steps), 1)

    def test_nice_step_values(self):
        self.assertEqual(svg.nice_step(0.7), 1)
        self.assertEqual(svg.nice_step(1.5), 2)
        self.assertEqual(svg.nice_step(3), 5)
        self.assertEqual(svg.nice_step(60), 100)


class ScaleTest(unittest.TestCase):
    def test_linear(self):
        f = svg.scale(0, 10, 100, 0)
        self.assertEqual(f(0), 100)
        self.assertEqual(f(10), 0)
        self.assertEqual(f(5), 50)

    def test_degenerate_domain(self):
        self.assertEqual(svg.scale(3, 3, 7, 9)(3), 7)


class FormatTest(unittest.TestCase):
    def test_fmt_int(self):
        self.assertEqual(svg.fmt_int(1234567), "1,234,567")
        self.assertEqual(svg.fmt_int(0), "0")

    def test_fmt_compact(self):
        self.assertEqual(svg.fmt_compact(950), "950")
        self.assertEqual(svg.fmt_compact(1200), "1.2k")
        self.assertEqual(svg.fmt_compact(20000), "20k")
        self.assertEqual(svg.fmt_compact(1500000), "1.5M")

    def test_truncate_middle(self):
        self.assertEqual(svg.truncate_middle("short", 10), "short")
        out = svg.truncate_middle("a" * 30 + "b" * 30, 21)
        self.assertEqual(len(out), 21)
        self.assertIn("…", out)
        self.assertTrue(out.startswith("a") and out.endswith("b"))

    def test_escape(self):
        self.assertEqual(svg.esc('<a href="x">&'), "&lt;a href=&quot;x&quot;&gt;&amp;")


class _Collect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def parse(markup):
    p = _Collect()
    p.feed(markup)
    return p.tags


class ChartTest(unittest.TestCase):
    def test_column_chart_bar_count_and_heights(self):
        out = svg.column_chart([0, 5, 10], ["a", "b", "c"], {0: "x"}, "y", "lbl")
        rects = [a for t, a in parse(out) if t == "rect"]
        self.assertEqual(len(rects), 3)
        self.assertEqual(float(rects[0]["height"]), 0)
        h5, h10 = float(rects[1]["height"]), float(rects[2]["height"])
        self.assertAlmostEqual(h10 / h5, 2.0, places=1)

    def test_column_chart_escapes_tooltips(self):
        out = svg.column_chart([1], ['<script>"'], {}, "y", "lbl")
        self.assertNotIn("<script>", out)

    def test_diverging_has_both_signs(self):
        out = svg.diverging_chart([5, 0], [0, 3], ["a", "b"], {}, "y", "l",
                                  [("add", "A"), ("del", "D")])
        classes = [a.get("class") for t, a in parse(out) if t == "rect"]
        self.assertIn("add", classes)
        self.assertIn("del", classes)

    def test_heatmap_has_168_cells(self):
        grid = [[d + h for h in range(24)] for d in range(7)]
        out = svg.heatmap(grid, list("ABCDEFG"), lambda d, h, v: "t", "l", ("lo", "hi"))
        cells = [a for t, a in parse(out) if t == "rect" and "data-tip" in a]
        self.assertEqual(len(cells), 168)

    def test_heatmap_opacity_monotonic(self):
        grid = [[0] * 24 for _ in range(7)]
        grid[0][0], grid[0][1], grid[0][2] = 1, 4, 9
        out = svg.heatmap(grid, list("ABCDEFG"), lambda d, h, v: str(v), "l", ("a", "b"))
        ops = {a["data-tip"]: float(a["style"].split(":")[1])
               for t, a in parse(out) if t == "rect" and a.get("class") == "cell" and "data-tip" in a}
        self.assertLess(ops["1"], ops["4"])
        self.assertLess(ops["4"], ops["9"])
        self.assertAlmostEqual(ops["9"], 1.0)

    def test_hbar_widths_proportional(self):
        out = svg.hbar_chart([("a", [(10, "bar")], "10", None), ("b", [(5, "bar")], "5", None)], "l")
        widths = [float(a["width"]) for t, a in parse(out) if t == "rect"]
        self.assertAlmostEqual(widths[0] / widths[1], 2.0, places=1)

    def test_hbar_empty(self):
        self.assertIn("</svg>", svg.hbar_chart([], "l"))


if __name__ == "__main__":
    unittest.main()
