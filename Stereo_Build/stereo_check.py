# stereo_check.py — diagnostic for the stereo rig, before any measurement
# pipeline exists.
#
# Answers the three questions that decide whether this approach will work in
# your warehouse, in order of how likely they are to kill it:
#
#   1. Does the conveyor surface match at all? Plain cardboard and bare
#      conveyor have very little texture, and block matching needs
#      distinctive patches to correspond. The DENSITY figure is the answer.
#      This is the most likely failure, and no amount of calibration fixes
#      it — it needs light or a projected pattern.
#
#   2. Is the depth metrically right? Drag a box over the bare conveyor and
#      the reported distance should match the tape measure. If it is off by
#      a consistent percentage, square_size_cm is wrong.
#
#   3. How noisy is it? The plane RMS over a flat surface is the rig's depth
#      noise, read directly. That number is your height precision floor.
#
# Usage:  py stereo_check.py
#
#   Drag a box with the mouse to fit a plane to that region.
#   F  set the current region as the floor reference
#   S  save a snapshot (raw pair + disparity) into calib/snapshots/
#   D  cycle display: disparity / depth / rectified left
#   ESC quit

import os
import sys
import time

import cv2
import numpy as np

from camera_config import load_params, open_camera, describe_camera, check_resolution_match
from stereo_depth import StereoDepth, fit_plane, height_above, tilt_degrees

SNAP_DIR = os.path.join("calib", "snapshots")

_drag = {"start": None, "end": None, "active": False, "roi": None}


def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        _drag["start"] = (x, y)
        _drag["end"] = (x, y)
        _drag["active"] = True
    elif event == cv2.EVENT_MOUSEMOVE and _drag["active"]:
        _drag["end"] = (x, y)
    elif event == cv2.EVENT_LBUTTONUP and _drag["active"]:
        _drag["end"] = (x, y)
        _drag["active"] = False
        x0, y0 = _drag["start"]
        x1, y1 = _drag["end"]
        if abs(x1 - x0) > 8 and abs(y1 - y0) > 8:
            _drag["roi"] = (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))


def colorize_disparity(disp, min_d, max_d):
    norm = np.zeros(disp.shape, np.uint8)
    valid = ~np.isnan(disp)
    if valid.any():
        scaled = (disp[valid] - min_d) / max(max_d - min_d, 1e-6)
        norm[valid] = np.clip(scaled * 255, 0, 255).astype(np.uint8)
    img = cv2.applyColorMap(norm, cv2.COLORMAP_TURBO)
    img[~valid] = (0, 0, 0)     # unmatched pixels stay black, and should stand out
    return img


def colorize_depth(pts, near, far):
    z = pts[:, :, 2]
    valid = np.isfinite(z)
    norm = np.zeros(z.shape, np.uint8)
    if valid.any():
        scaled = (far - z[valid]) / max(far - near, 1e-6)
        norm[valid] = np.clip(scaled * 255, 0, 255).astype(np.uint8)
    img = cv2.applyColorMap(norm, cv2.COLORMAP_TURBO)
    img[~valid] = (0, 0, 0)
    return img


def put_lines(img, lines, origin=(10, 26), colour=(255, 255, 255)):
    for i, text in enumerate(lines):
        y = origin[1] + i * 24
        cv2.putText(img, text, (origin[0], y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.58, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, text, (origin[0], y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.58, colour, 1, cv2.LINE_AA)


def main():
    params = load_params()

    try:
        depth = StereoDepth(params)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    print(depth.describe())
    if depth.num_disparities > 256:
        print(f"NOTE: disparity range is {depth.num_disparities} px, which is "
              f"wide and therefore slow. That is expected for this rig and "
              f"fine — measurement runs one pass per package, not per frame.")

    cap_l = open_camera(int(params["camera_index_left"]), params)
    cap_r = open_camera(int(params["camera_index_right"]), params)
    if cap_l is None or cap_r is None:
        return 1

    print("\nCameras:")
    size_l = describe_camera(cap_l, "left")
    size_r = describe_camera(cap_r, "right")
    if not check_resolution_match(size_l, size_r):
        cap_l.release(); cap_r.release()
        return 1
    if size_l != depth.image_size:
        print(f"Error: cameras are running at {size_l} but the calibration was "
              f"captured at {depth.image_size}. Rectification would be wrong. "
              f"Fix frame_width/frame_height, or recalibrate.")
        cap_l.release(); cap_r.release()
        return 1

    print("\nDrag a box to fit a plane to that region.")
    print("F = set that region as the floor reference   S = snapshot   "
          "D = display mode   ESC = quit")

    window = "stereo check"
    cv2.namedWindow(window)
    cv2.setMouseCallback(window, on_mouse)

    floor_ref = None
    last_fit = None
    mode = 0
    modes = ("disparity", "depth", "rectified left")
    near = depth.disparity_to_depth(depth.min_disparity + depth.num_disparities)
    far = depth.disparity_to_depth(depth.min_disparity)

    while True:
        ok_l, frame_l = cap_l.read()
        ok_r, frame_r = cap_r.read()
        if not (ok_l and ok_r):
            print("Error: failed to read from both cameras.")
            break

        t0 = time.time()
        rect_l, rect_r = depth.rectify(frame_l, frame_r)
        disp = depth.disparity(rect_l, rect_r)
        pts = depth.points_3d(disp)
        elapsed = (time.time() - t0) * 1000.0
        density = depth.density(disp)

        if mode == 0:
            view = colorize_disparity(
                disp, depth.min_disparity,
                depth.min_disparity + depth.num_disparities)
            view = cv2.addWeighted(view, 0.75, rect_l, 0.25, 0)
        elif mode == 1:
            view = colorize_depth(pts, near, far)
            view = cv2.addWeighted(view, 0.75, rect_l, 0.25, 0)
        else:
            view = rect_l.copy()

        if _drag["roi"] is not None:
            x, y, w, h = _drag["roi"]
            roi_pts = pts[y:y + h, x:x + w]
            last_fit = fit_plane(roi_pts)
            roi_density = depth.density(disp[y:y + h, x:x + w])
            _drag["roi"] = None
            if last_fit is None:
                print("  region has too few matched pixels to fit a plane")
                last_fit = None
            else:
                centroid, normal, rms = last_fit
                msg = (f"  plane: distance {centroid[2]:.2f} cm   "
                       f"flatness RMS {rms:.3f} cm   "
                       f"tilt {tilt_degrees(normal):.1f} deg   "
                       f"matched {roi_density * 100:.0f}%")
                if floor_ref is not None:
                    msg += f"   height above floor {height_above(floor_ref, centroid):.2f} cm"
                print(msg)
                _drag["last_box"] = (x, y, w, h)

        if _drag["active"] and _drag["start"] and _drag["end"]:
            cv2.rectangle(view, _drag["start"], _drag["end"], (0, 255, 255), 2)
        if _drag.get("last_box"):
            x, y, w, h = _drag["last_box"]
            cv2.rectangle(view, (x, y), (x + w, y + h), (0, 255, 0), 2)

        lines = [
            f"view: {modes[mode]}   {elapsed:.0f} ms/frame",
            f"DENSITY {density * 100:.1f}%  <- matched pixels; low means too "
            f"little texture",
        ]
        if last_fit is not None:
            centroid, normal, rms = last_fit
            lines.append(f"region: {centroid[2]:.2f} cm   flatness {rms:.3f} cm   "
                         f"tilt {tilt_degrees(normal):.1f} deg")
            if floor_ref is not None:
                lines.append(f"HEIGHT above floor: "
                             f"{height_above(floor_ref, centroid):.2f} cm")
        if floor_ref is not None:
            lines.append(f"floor reference set at {floor_ref[0][2]:.2f} cm")
        else:
            lines.append("no floor reference — drag over bare conveyor, press F")

        put_lines(view, lines)
        cv2.imshow(window, view)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        if key in (ord('d'), ord('D')):
            mode = (mode + 1) % len(modes)
        if key in (ord('f'), ord('F')):
            if last_fit is None:
                print("  fit a region first (drag a box over bare conveyor)")
            else:
                floor_ref = last_fit
                print(f"  floor reference set: distance {floor_ref[0][2]:.2f} cm, "
                      f"flatness RMS {floor_ref[2]:.3f} cm")
                print(f"  -> that RMS is this rig's depth noise, and therefore "
                      f"your height precision floor")
        if key in (ord('s'), ord('S')):
            os.makedirs(SNAP_DIR, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            cv2.imwrite(os.path.join(SNAP_DIR, f"{stamp}_left.png"), frame_l)
            cv2.imwrite(os.path.join(SNAP_DIR, f"{stamp}_right.png"), frame_r)
            np.save(os.path.join(SNAP_DIR, f"{stamp}_disparity.npy"), disp)
            print(f"  saved snapshot {stamp} to {SNAP_DIR}/")

    cap_l.release(); cap_r.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
