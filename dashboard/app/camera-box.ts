/**
 * Geometry for the floating camera window.
 *
 * Kept out of the component so it can be tested directly: the clamping and
 * edge snapping are the parts most likely to strand the window off screen or
 * park it a few pixels away from an edge.
 */
export type CamBox = {
  x: number;
  y: number;
  width: number;
  height: number;
  hidden: boolean;
};

export type Viewport = { width: number; height: number };

export const CAM_STORAGE_KEY = "autopa-camera-box";
export const CAM_MIN_W = 180;
export const CAM_MIN_H = 120;
/**
 * Within this distance of a viewport edge the window snaps flush against it,
 * so it parks cleanly instead of sitting a few pixels off.
 */
export const CAM_SNAP_PX = 28;
export const CAM_MARGIN = 12;

/**
 * A viewport this small is not a real one - a browser can report zero while
 * the page is still laying out, and a hidden or freshly created tab does the
 * same. Clamping against it pins the window to the corner at minimum size,
 * and because the box is persisted that wrong value would survive every
 * later reload.
 */
export function isMeasurableViewport(view: Viewport): boolean {
  return view.width >= CAM_MIN_W * 2 && view.height >= CAM_MIN_H * 2;
}

/** Keep the window inside the viewport and above its minimum size. */
export function clampCamBox(box: CamBox, view: Viewport): CamBox {
  if (!isMeasurableViewport(view)) return box;
  const width = Math.max(CAM_MIN_W, Math.min(box.width, view.width - 8));
  const height = Math.max(CAM_MIN_H, Math.min(box.height, view.height - 8));
  return {
    ...box,
    width,
    height,
    x: Math.max(0, Math.min(box.x, view.width - width)),
    y: Math.max(0, Math.min(box.y, view.height - height)),
  };
}

/**
 * Snap to whichever edges are close. The axes are handled independently, so
 * a corner drag parks in the corner while an edge drag keeps its other
 * coordinate where the user put it.
 */
export function snapCamBox(box: CamBox, view: Viewport): CamBox {
  if (!isMeasurableViewport(view)) return box;
  const right = view.width - (box.x + box.width);
  const bottom = view.height - (box.y + box.height);
  let { x, y } = box;
  if (box.x <= CAM_SNAP_PX) x = CAM_MARGIN;
  else if (right <= CAM_SNAP_PX) x = view.width - box.width - CAM_MARGIN;
  if (box.y <= CAM_SNAP_PX) y = CAM_MARGIN;
  else if (bottom <= CAM_SNAP_PX) y = view.height - box.height - CAM_MARGIN;
  return clampCamBox({ ...box, x, y }, view);
}

/** Default placement: bottom right, out of the way of the cards. */
export function defaultCamBox(view: Viewport): CamBox {
  return clampCamBox(
    {
      x: view.width - 320 - CAM_MARGIN,
      y: view.height - 200 - CAM_MARGIN,
      width: 320,
      height: 200,
      hidden: false,
    },
    view,
  );
}
