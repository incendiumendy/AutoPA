import assert from "node:assert/strict";
import test from "node:test";

// The component cannot be imported here, so the geometry lives in its own
// module. Clamping and snapping are the parts that can strand the window off
// screen or park it a few pixels away from an edge.
const {
  CAM_MARGIN,
  CAM_MIN_H,
  CAM_MIN_W,
  clampCamBox,
  defaultCamBox,
  snapCamBox,
} = await import("../app/camera-box.ts");

const VIEW = { width: 1280, height: 800 };
const box = (x, y, width = 320, height = 200) => ({
  x,
  y,
  width,
  height,
  hidden: false,
});

test("snaps to a near edge and leaves the other axis alone", () => {
  // Close to the right edge only: x snaps, y stays where it was put.
  const snapped = snapCamBox(box(950, 300), VIEW);
  assert.equal(snapped.x, VIEW.width - 320 - CAM_MARGIN);
  assert.equal(snapped.y, 300);
});

test("snaps into a corner when both edges are near", () => {
  const topLeft = snapCamBox(box(9, 6), VIEW);
  assert.deepEqual([topLeft.x, topLeft.y], [CAM_MARGIN, CAM_MARGIN]);

  const bottomRight = snapCamBox(box(950, 590), VIEW);
  assert.deepEqual(
    [bottomRight.x, bottomRight.y],
    [VIEW.width - 320 - CAM_MARGIN, VIEW.height - 200 - CAM_MARGIN],
  );
});

test("leaves a window in the middle untouched", () => {
  const free = snapCamBox(box(500, 300), VIEW);
  assert.deepEqual([free.x, free.y], [500, 300]);
});

test("pulls a window dragged off screen back into view", () => {
  const rescued = snapCamBox(box(4000, 4000), VIEW);
  assert.ok(rescued.x + rescued.width <= VIEW.width);
  assert.ok(rescued.y + rescued.height <= VIEW.height);
  assert.ok(rescued.x >= 0 && rescued.y >= 0);
});

test("enforces a minimum size", () => {
  const tiny = clampCamBox(box(500, 300, 40, 20), VIEW);
  assert.equal(tiny.width, CAM_MIN_W);
  assert.equal(tiny.height, CAM_MIN_H);
});

test("never lets a stored box outlive a smaller viewport", () => {
  // A window parked bottom-right on a desktop, reopened on a small screen.
  const small = { width: 400, height: 300 };
  const restored = clampCamBox(box(948, 588), small);
  assert.ok(restored.x + restored.width <= small.width);
  assert.ok(restored.y + restored.height <= small.height);
});

test("the default box sits inside the viewport", () => {
  const fitted = defaultCamBox(VIEW);
  assert.ok(fitted.x + fitted.width <= VIEW.width);
  assert.ok(fitted.y + fitted.height <= VIEW.height);
  assert.equal(fitted.hidden, false);
});

test("a viewport that is not measurable yet changes nothing", async () => {
  // A browser can report zero while the page lays out, and a hidden tab does
  // the same. Clamping against that pins the window into the corner at
  // minimum size - and because the box is persisted, the wrong value would
  // survive every later reload.
  const { isMeasurableViewport } = await import("../app/camera-box.ts");
  const parked = box(948, 508);
  for (const view of [
    { width: 0, height: 0 },
    { width: 300, height: 0 },
    { width: 200, height: 150 },
  ]) {
    assert.equal(isMeasurableViewport(view), false);
    assert.deepEqual(clampCamBox(parked, view), parked);
    assert.deepEqual(snapCamBox(parked, view), parked);
  }
  assert.equal(isMeasurableViewport(VIEW), true);
});
