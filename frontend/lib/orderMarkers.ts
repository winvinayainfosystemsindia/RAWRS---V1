// Blocks whose tops are this close (in screen px) share one marker row.
const ORDER_ROW_TOLERANCE_PX = 6;
const ORDER_MARKER_HEIGHT_PX = 13;

/** Reading-order markers laid out in the page's left gutter: one marker per
 *  line of the page, labelled with the positions of every block starting on
 *  that line ("30–32" for a table row, "1, 20" for two columns side by side).
 *  Outside the page, so a marker can never sit on top of a word. */
export function orderMarkerRows(
  blocks: { bbox_y0: number }[],
  zoom: number
): { top: number; label: string }[] {
  const rows: { top: number; positions: number[] }[] = [];
  blocks.forEach((block, index) => {
    const top = block.bbox_y0 * zoom;
    const row = rows.find((r) => Math.abs(r.top - top) <= ORDER_ROW_TOLERANCE_PX);
    if (row) row.positions.push(index + 1);
    else rows.push({ top, positions: [index + 1] });
  });
  // Stack rows at least one marker-height apart so tight table rows never
  // draw their markers on top of each other.
  let floor = -Infinity;
  return rows
    .sort((a, b) => a.top - b.top)
    .map((row) => {
      const top = Math.max(row.top, floor);
      floor = top + ORDER_MARKER_HEIGHT_PX;
      return { top, label: compactRanges(row.positions) };
    });
}

function compactRanges(positions: number[]): string {
  const sorted = [...positions].sort((a, b) => a - b);
  const parts: string[] = [];
  let start = sorted[0];
  let previous = sorted[0];
  for (const position of [...sorted.slice(1), Number.NaN]) {
    if (position === previous + 1) {
      previous = position;
      continue;
    }
    parts.push(start === previous ? `${start}` : `${start}–${previous}`);
    start = previous = position;
  }
  return parts.join(", ");
}
