import { orderMarkerRows } from "@/lib/orderMarkers";

// Reading-order markers live in the page gutter; these rules keep them from
// ever covering text or each other.
test("blocks starting on the same line share one marker with a compact label", () => {
  const rows = orderMarkerRows([{ bbox_y0: 100 }, { bbox_y0: 101 }, { bbox_y0: 102 }, { bbox_y0: 200 }], 1);
  expect(rows).toEqual([
    { top: 100, label: "1–3" },
    { top: 200, label: "4" },
  ]);
});

test("two columns side by side read as separate positions on one line", () => {
  const rows = orderMarkerRows([{ bbox_y0: 50 }, { bbox_y0: 300 }, { bbox_y0: 51 }], 1);
  expect(rows[0]).toEqual({ top: 50, label: "1, 3" });
});

test("tight rows are pushed apart so markers never overlap", () => {
  const rows = orderMarkerRows([{ bbox_y0: 100 }, { bbox_y0: 108 }, { bbox_y0: 116 }], 1);
  const tops = rows.map((r) => r.top);
  expect(tops[1] - tops[0]).toBeGreaterThanOrEqual(13);
  expect(tops[2] - tops[1]).toBeGreaterThanOrEqual(13);
});

test("zoom scales positions", () => {
  expect(orderMarkerRows([{ bbox_y0: 100 }], 1.5)[0].top).toBe(150);
});
