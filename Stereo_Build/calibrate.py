# calibrate.py — calibration tool for the dual top-mounted stereoscopic DWS.
#
# Replaces ratio_calibration.py. The old tool produced a single cm-per-pixel
# scalar by clicking two points; that scalar cannot represent lens distortion
# and cannot represent the fact that scale changes with distance, which is why
# the original system needed a hand-tuned parallax fudge factor on top of it.
#
# This tool instead recovers, for each camera, the full pinhole model
# (focal lengths, principal point, distortion coefficients) and then the rigid
# transform between the two cameras. From those, any image point can be turned
# into a real 3D ray, and a matched pair of rays gives a real 3D point.
#
# Sub-commands, in the order you run them:
#
#   py calibrate.py board        Generate a printable chessboard PNG.
#   py calibrate.py probe        Identify which device index is which camera.
#   py calibrate.py intrinsics left     Calibrate ONE camera's lens.
#   py calibrate.py intrinsics right    Same for the other.
#   py calibrate.py stereo       Recover the geometry between the two.
#   py calibrate.py verify       Check the result on a live rectified view.
#
# Intrinsics are per physical unit, not per model: two copies of the same
# webcam differ enough in focus and manufacturing tolerance that each needs
# its own pass. Run "intrinsics" once per camera, then "stereo" once, and
# redo everything from "stereo" onward if the rig is ever bumped or moved.

import os
import sys
import glob

import cv2
import numpy as np

from camera_config import (
    load_params, open_camera, describe_camera, check_resolution_match,
)

CALIB_DIR = "calib"

# Detection flags for findChessboardCornersSB. EXHAUSTIVE + ACCURACY is slower
# per frame but finds the board at steeper tilts, which is exactly where the
# views that constrain the distortion coefficients come from.
SB_FLAGS = cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY | cv2.CALIB_CB_NORMALIZE_IMAGE

# Coverage grid resolution for the on-screen "have I covered the frame?" hint.
COVER_COLS, COVER_ROWS = 8, 6


# ---------------------------------------------------------------------------
# Board geometry
# ---------------------------------------------------------------------------

def board_size(params):
    """(cols, rows) of INNER corners — one less than the square counts."""
    return (int(params["board_cols"]), int(params["board_rows"]))


def object_points(params):
    """The board's corners in its own coordinate frame, in cm, z=0.

    Because square_size_cm is in centimetres, every distance this system
    recovers later (baseline, depth, package dimensions) is also in
    centimetres. This single number sets the absolute scale of the whole
    system — see the warning in stereo_params.yaml."""
    cols, rows = board_size(params)
    square = float(params["square_size_cm"])
    objp = np.zeros((cols * rows, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    return objp * square


def find_board(gray, size):
    """Returns sub-pixel corners, or None. Falls back to the classic detector
    if the newer SB detector is unavailable or comes up empty."""
    ok, corners = cv2.findChessboardCornersSB(gray, size, SB_FLAGS)
    if ok:
        return corners

    ok, corners = cv2.findChessboardCorners(
        gray, size,
        cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
    )
    if not ok:
        return None
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    return cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)


# ---------------------------------------------------------------------------
# On-screen coverage hint
# ---------------------------------------------------------------------------

def mark_coverage(coverage, corners, shape):
    """Records which regions of the frame a captured board fell in."""
    h, w = shape[:2]
    for pt in corners.reshape(-1, 2):
        c = min(int(pt[0] / w * COVER_COLS), COVER_COLS - 1)
        r = min(int(pt[1] / h * COVER_ROWS), COVER_ROWS - 1)
        coverage[r, c] += 1


def draw_coverage(frame, coverage):
    """Draws the coverage grid so you can see which parts of the frame still
    have no board samples. Distortion coefficients are only constrained where
    you actually put the board, so a calibration built entirely from
    centre-of-frame views will be wrong at the edges — which is exactly where
    a package sitting off to one side gets measured."""
    h, w = frame.shape[:2]
    cell_w, cell_h = w // COVER_COLS, h // COVER_ROWS
    overlay = frame.copy()
    for r in range(COVER_ROWS):
        for c in range(COVER_COLS):
            x0, y0 = c * cell_w, r * cell_h
            colour = (0, 160, 0) if coverage[r, c] else (40, 40, 40)
            cv2.rectangle(overlay, (x0, y0), (x0 + cell_w, y0 + cell_h),
                          colour, -1)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
    for r in range(1, COVER_ROWS):
        cv2.line(frame, (0, r * cell_h), (w, r * cell_h), (70, 70, 70), 1)
    for c in range(1, COVER_COLS):
        cv2.line(frame, (c * cell_w, 0), (c * cell_w, h), (70, 70, 70), 1)


def coverage_fraction(coverage):
    return float((coverage > 0).sum()) / coverage.size


def put_lines(frame, lines, origin=(10, 28), colour=(0, 255, 255)):
    for i, text in enumerate(lines):
        cv2.putText(frame, text, (origin[0], origin[1] + i * 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)


# ---------------------------------------------------------------------------
# board — generate a printable target
# ---------------------------------------------------------------------------

def cmd_board(params):
    cols, rows = board_size(params)
    square_cm = float(params["square_size_cm"])
    dpi = 300
    px = int(round(square_cm / 2.54 * dpi))

    # A chessboard with NxM inner corners needs (N+1)x(M+1) squares.
    sq_cols, sq_rows = cols + 1, rows + 1
    board = np.zeros((sq_rows * px, sq_cols * px), np.uint8)
    for r in range(sq_rows):
        for c in range(sq_cols):
            if (r + c) % 2 == 0:
                board[r * px:(r + 1) * px, c * px:(c + 1) * px] = 255

    margin = px // 2
    sheet = np.full((board.shape[0] + 2 * margin,
                     board.shape[1] + 2 * margin), 255, np.uint8)
    sheet[margin:margin + board.shape[0], margin:margin + board.shape[1]] = board

    os.makedirs(CALIB_DIR, exist_ok=True)
    out = os.path.join(CALIB_DIR, f"chessboard_{cols}x{rows}_{square_cm}cm.png")
    cv2.imwrite(out, sheet)

    w_cm = sq_cols * square_cm
    h_cm = sq_rows * square_cm
    print(f"Wrote {out}")
    print(f"  {sq_cols}x{sq_rows} squares  ->  {cols}x{rows} inner corners")
    print(f"  Nominal printed size: {w_cm:.1f} x {h_cm:.1f} cm at {dpi} DPI")
    print()
    print("PRINT AT 100% SCALE. Turn off 'fit to page' / 'shrink to fit' —")
    print("it rescales by a few percent and that error propagates into every")
    print("measurement the system ever makes.")
    print()
    print("Then MEASURE the printed squares with calipers (span several and")
    print("divide) and put the measured value in stereo_params.yaml as")
    print("square_size_cm. Do not assume it printed exactly.")
    print()
    print("Glue the sheet to something rigid and flat — foam board or MDF.")
    print("A curled or hand-held sheet is not a plane, and the calibration")
    print("assumes it is one.")


# ---------------------------------------------------------------------------
# probe — identify camera indices
# ---------------------------------------------------------------------------

def cmd_probe(params):
    print("Opening camera indices 0-5. Watch the windows to see which is")
    print("which, note the indices, then set camera_index_left/right in")
    print("stereo_params.yaml.  ESC to quit.")

    caps = []
    for idx in range(6):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            caps.append((idx, cap))
            print(f"  index {idx}: opened")
        else:
            cap.release()

    if not caps:
        print("No cameras found.")
        return

    while True:
        for idx, cap in caps:
            ok, frame = cap.read()
            if ok:
                put_lines(frame, [f"index {idx}"])
                cv2.imshow(f"camera index {idx}", frame)
        if cv2.waitKey(1) == 27:
            break

    for _, cap in caps:
        cap.release()
    cv2.destroyAllWindows()


# ---------------------------------------------------------------------------
# intrinsics — calibrate one camera's lens
# ---------------------------------------------------------------------------

def cmd_intrinsics(params, side):
    if side not in ("left", "right"):
        print("Usage: py calibrate.py intrinsics <left|right>")
        return

    index = int(params[f"camera_index_{side}"])
    size = board_size(params)
    objp = object_points(params)
    min_views = int(params["min_views_intrinsics"])

    cap = open_camera(index, params)
    if cap is None:
        return
    print(f"Camera '{side}' at index {index}:")
    img_size = describe_camera(cap, side)

    print()
    print("Hold the board in view and press SPACE to capture each pose.")
    print("Aim for the whole coverage grid to turn green, and include steep")
    print("tilts — flat, centred views alone leave the distortion")
    print("coefficients unconstrained at the frame edges.")
    print(f"Controls:  SPACE = capture   U = undo last   "
          f"C = calibrate (>= {min_views} views)   ESC = quit")

    obj_list, img_list = [], []
    coverage = np.zeros((COVER_ROWS, COVER_COLS), np.int32)

    while True:
        ok, frame = cap.read()
        if not ok:
            print("Error: failed to read frame.")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners = find_board(gray, size)

        view = frame.copy()
        draw_coverage(view, coverage)
        if corners is not None:
            cv2.drawChessboardCorners(view, size, corners, True)

        put_lines(view, [
            f"[{side}] views: {len(img_list)}/{min_views}   "
            f"coverage: {coverage_fraction(coverage) * 100:.0f}%",
            "board FOUND — SPACE to capture" if corners is not None
            else "no board detected",
        ], colour=(0, 255, 0) if corners is not None else (0, 0, 255))
        cv2.imshow(f"intrinsics [{side}]", view)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        if key == ord(' ') and corners is not None:
            obj_list.append(objp.copy())
            img_list.append(corners)
            mark_coverage(coverage, corners, frame.shape)
            print(f"  captured view {len(img_list)}")
        if key in (ord('u'), ord('U')) and img_list:
            obj_list.pop()
            img_list.pop()
            # Rebuild coverage from scratch — cheap, and keeps it honest.
            coverage[:] = 0
            for c in img_list:
                mark_coverage(coverage, c, frame.shape)
            print(f"  undid last view ({len(img_list)} remain)")
        if key in (ord('c'), ord('C')):
            if len(img_list) < min_views:
                print(f"  need at least {min_views} views, have {len(img_list)}")
                continue
            _finish_intrinsics(params, side, obj_list, img_list, img_size,
                               coverage)
            break

    cap.release()
    cv2.destroyAllWindows()


def _finish_intrinsics(params, side, obj_list, img_list, img_size, coverage):
    print(f"\nCalibrating '{side}' from {len(img_list)} views...")
    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        obj_list, img_list, img_size, None, None)

    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    print(f"  RMS reprojection error: {rms:.4f} px")
    print(f"  fx={fx:.1f}  fy={fy:.1f}  cx={cx:.1f}  cy={cy:.1f}")
    print(f"  distortion: {np.ravel(dist)}")

    max_rms = float(params["max_rms_px"])
    if rms > max_rms:
        print(f"  WARNING: RMS above {max_rms} px. Recapture with sharper,")
        print("  better-lit, more varied views before trusting this.")
    if coverage_fraction(coverage) < 0.6:
        print("  WARNING: less than 60% frame coverage. The distortion model")
        print("  is extrapolating in the regions you never sampled.")
    if abs(fx - fy) / max(fx, fy) > 0.05:
        print("  WARNING: fx and fy differ by >5%. Usually means the driver")
        print("  is delivering a stretched or cropped frame.")

    os.makedirs(CALIB_DIR, exist_ok=True)
    out = os.path.join(CALIB_DIR, f"intrinsics_{side}.npz")
    np.savez(out, K=K, dist=dist, image_size=np.array(img_size), rms=rms)
    print(f"  saved {out}")


# ---------------------------------------------------------------------------
# stereo — recover the geometry between the two cameras
# ---------------------------------------------------------------------------

def _load_intrinsics(side):
    path = os.path.join(CALIB_DIR, f"intrinsics_{side}.npz")
    if not os.path.exists(path):
        print(f"Missing {path} — run 'py calibrate.py intrinsics {side}' first.")
        return None
    return np.load(path)


def cmd_stereo(params):
    left_cal, right_cal = _load_intrinsics("left"), _load_intrinsics("right")
    if left_cal is None or right_cal is None:
        return

    size = board_size(params)
    objp = object_points(params)
    min_views = int(params["min_views_stereo"])

    cap_l = open_camera(int(params["camera_index_left"]), params)
    cap_r = open_camera(int(params["camera_index_right"]), params)
    if cap_l is None or cap_r is None:
        return

    print("Cameras:")
    size_l = describe_camera(cap_l, "left")
    size_r = describe_camera(cap_r, "right")
    if not check_resolution_match(size_l, size_r):
        cap_l.release(); cap_r.release()
        return

    print()
    print("The rig must already be in its FINAL mounted position — these")
    print("extrinsics describe where the two cameras are relative to each")
    print("other, so moving or bumping either one invalidates them.")
    print()
    print("Hold the board where BOTH cameras see it. Capture is only allowed")
    print("when both detect it. Vary depth and tilt; cover the shared field.")
    print(f"Controls:  SPACE = capture   U = undo last   "
          f"C = calibrate (>= {min_views} views)   ESC = quit")

    obj_list, img_l, img_r = [], [], []

    while True:
        ok_l, frame_l = cap_l.read()
        ok_r, frame_r = cap_r.read()
        if not (ok_l and ok_r):
            print("Error: failed to read from both cameras.")
            break

        gray_l = cv2.cvtColor(frame_l, cv2.COLOR_BGR2GRAY)
        gray_r = cv2.cvtColor(frame_r, cv2.COLOR_BGR2GRAY)
        corners_l = find_board(gray_l, size)
        corners_r = find_board(gray_r, size)
        both = corners_l is not None and corners_r is not None

        view_l, view_r = frame_l.copy(), frame_r.copy()
        if corners_l is not None:
            cv2.drawChessboardCorners(view_l, size, corners_l, True)
        if corners_r is not None:
            cv2.drawChessboardCorners(view_r, size, corners_r, True)

        pair = np.hstack([view_l, view_r])
        scale = 1280.0 / pair.shape[1]
        pair = cv2.resize(pair, None, fx=scale, fy=scale)
        put_lines(pair, [
            f"pairs: {len(obj_list)}/{min_views}",
            "BOTH cameras see the board — SPACE to capture" if both
            else f"left:{'ok' if corners_l is not None else 'no'}  "
                 f"right:{'ok' if corners_r is not None else 'no'}",
        ], colour=(0, 255, 0) if both else (0, 0, 255))
        cv2.imshow("stereo capture  [left | right]", pair)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        if key == ord(' ') and both:
            obj_list.append(objp.copy())
            img_l.append(corners_l)
            img_r.append(corners_r)
            print(f"  captured pair {len(obj_list)}")
        if key in (ord('u'), ord('U')) and obj_list:
            obj_list.pop(); img_l.pop(); img_r.pop()
            print(f"  undid last pair ({len(obj_list)} remain)")
        if key in (ord('c'), ord('C')):
            if len(obj_list) < min_views:
                print(f"  need at least {min_views} pairs, have {len(obj_list)}")
                continue
            _finish_stereo(params, left_cal, right_cal,
                           obj_list, img_l, img_r, size_l)
            break

    cap_l.release(); cap_r.release()
    cv2.destroyAllWindows()


def _finish_stereo(params, left_cal, right_cal, obj_list, img_l, img_r, img_size):
    print(f"\nStereo calibrating from {len(obj_list)} pairs...")

    # CALIB_FIX_INTRINSIC: trust the per-camera passes and solve only for the
    # rigid transform between them. Re-solving intrinsics here from a smaller,
    # less varied set of views than the dedicated passes used would make them
    # worse, not better.
    result = cv2.stereoCalibrate(
        obj_list, img_l, img_r,
        left_cal["K"],  left_cal["dist"],
        right_cal["K"], right_cal["dist"],
        img_size,
        flags=cv2.CALIB_FIX_INTRINSIC,
        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-5),
    )
    rms, K1, d1, K2, d2, R, T = result[:7]

    baseline = float(np.linalg.norm(T))
    nominal = float(params["nominal_baseline_cm"])
    print(f"  RMS reprojection error: {rms:.4f} px")
    print(f"  recovered baseline: {baseline:.2f} cm  (nominal {nominal:.1f} cm)")
    print(f"  translation T = {np.ravel(T)}")

    max_rms = float(params["max_rms_px"])
    if rms > max_rms:
        print(f"  WARNING: RMS above {max_rms} px — recapture before trusting.")

    # The baseline check is really a check on square_size_cm. Scale enters the
    # system in exactly one place (the board square size), so if the recovered
    # baseline is off by 10%, square_size_cm is almost certainly off by 10%,
    # and so is every dimension this system will report.
    if nominal > 0 and abs(baseline - nominal) / nominal > 0.10:
        print("  WARNING: recovered baseline is >10% from nominal. Either the")
        print("  cameras are not where you think, or — far more likely —")
        print("  square_size_cm is wrong. Re-measure the printed board.")

    f1, f2 = K1[0, 0], K2[0, 0]
    if abs(f1 - f2) / max(f1, f2) > 0.05:
        print(f"  WARNING: focal lengths differ by >5% ({f1:.0f} vs {f2:.0f} px).")
        print("  These do not look like matched camera units. Rectification")
        print("  will resample both to a common focal length and you will")
        print("  lose effective resolution from the sharper one.")

    R1, R2, P1, P2, Q, roi1, roi2 = cv2.stereoRectify(
        K1, d1, K2, d2, img_size, R, T,
        flags=cv2.CALIB_ZERO_DISPARITY, alpha=0,
    )

    os.makedirs(CALIB_DIR, exist_ok=True)
    out = os.path.join(CALIB_DIR, "stereo_calib.npz")
    np.savez(out, K1=K1, d1=d1, K2=K2, d2=d2, R=R, T=T,
             R1=R1, R2=R2, P1=P1, P2=P2, Q=Q,
             roi1=np.array(roi1), roi2=np.array(roi2),
             image_size=np.array(img_size), rms=rms, baseline_cm=baseline)
    print(f"  saved {out}")

    _report_working_envelope(params, P2, baseline, img_size)


def _report_working_envelope(params, P2, baseline, img_size):
    """Prints the disparity range and usable footprint implied by this rig,
    so the numbers used to size the matcher come from the real calibration
    rather than from nominal figures."""
    f = float(P2[0, 0])
    w, h = img_size
    height = float(params["nominal_height_cm"])

    print()
    print("  Working envelope implied by this calibration:")
    print(f"    focal length (rectified): {f:.1f} px")
    print(f"    disparity = {f * baseline:.0f} / Z_cm")
    print()
    print("    parcel   camera-to-top    disparity    max footprint in overlap")
    for parcel_h in (0, 20, 40, 60):
        z = height - parcel_h
        if z <= 5:
            continue
        disp = f * baseline / z
        usable_w = 2 * z * (w / 2) / f - baseline
        usable_h = 2 * z * (h / 2) / f
        print(f"    {parcel_h:>3} cm      {z:>6.0f} cm      "
              f"{disp:>6.0f} px     {usable_w:>5.1f} x {usable_h:.1f} cm")
    print()
    print("  Check the right-hand column against your actual parcel sizes. If")
    print("  your largest packages do not fit, raise the rig and recalibrate")
    print("  from the 'stereo' step.")


# ---------------------------------------------------------------------------
# verify — live rectified view
# ---------------------------------------------------------------------------

def cmd_verify(params):
    path = os.path.join(CALIB_DIR, "stereo_calib.npz")
    if not os.path.exists(path):
        print(f"Missing {path} — run 'py calibrate.py stereo' first.")
        return
    cal = np.load(path)
    img_size = tuple(int(v) for v in cal["image_size"])

    map1x, map1y = cv2.initUndistortRectifyMap(
        cal["K1"], cal["d1"], cal["R1"], cal["P1"], img_size, cv2.CV_16SC2)
    map2x, map2y = cv2.initUndistortRectifyMap(
        cal["K2"], cal["d2"], cal["R2"], cal["P2"], img_size, cv2.CV_16SC2)

    cap_l = open_camera(int(params["camera_index_left"]), params)
    cap_r = open_camera(int(params["camera_index_right"]), params)
    if cap_l is None or cap_r is None:
        return

    print(f"Calibration RMS: {float(cal['rms']):.4f} px   "
          f"baseline: {float(cal['baseline_cm']):.2f} cm")
    print()
    print("Horizontal lines are drawn across both rectified views. A feature")
    print("must sit on the SAME line in both images — that is what makes the")
    print("disparity search one-dimensional. If features drift vertically")
    print("between the views, the calibration is bad; redo it.")
    print("Controls:  R = toggle rectification   ESC = quit")

    rectified = True
    while True:
        ok_l, frame_l = cap_l.read()
        ok_r, frame_r = cap_r.read()
        if not (ok_l and ok_r):
            print("Error: failed to read from both cameras.")
            break

        if rectified:
            frame_l = cv2.remap(frame_l, map1x, map1y, cv2.INTER_LINEAR)
            frame_r = cv2.remap(frame_r, map2x, map2y, cv2.INTER_LINEAR)

        pair = np.hstack([frame_l, frame_r])
        scale = 1280.0 / pair.shape[1]
        pair = cv2.resize(pair, None, fx=scale, fy=scale)

        if rectified:
            for y in range(0, pair.shape[0], 32):
                cv2.line(pair, (0, y), (pair.shape[1], y), (0, 200, 0), 1)

        put_lines(pair, [
            "RECTIFIED — features must share a horizontal line" if rectified
            else "RAW (rectification off)",
        ], colour=(0, 255, 0) if rectified else (0, 165, 255))
        cv2.imshow("verify  [left | right]", pair)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        if key in (ord('r'), ord('R')):
            rectified = not rectified

    cap_l.release(); cap_r.release()
    cv2.destroyAllWindows()


# ---------------------------------------------------------------------------

COMMANDS = {
    "board":      lambda p, a: cmd_board(p),
    "probe":      lambda p, a: cmd_probe(p),
    "intrinsics": lambda p, a: cmd_intrinsics(p, a[0] if a else ""),
    "stereo":     lambda p, a: cmd_stereo(p),
    "verify":     lambda p, a: cmd_verify(p),
}


def main(argv):
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print("Usage: py calibrate.py <command> [args]")
        print()
        print("  board                    generate a printable chessboard")
        print("  probe                    identify camera device indices")
        print("  intrinsics <left|right>  calibrate one camera's lens")
        print("  stereo                   recover geometry between cameras")
        print("  verify                   live rectified view")
        return 1

    params = load_params()
    COMMANDS[argv[1]](params, argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
