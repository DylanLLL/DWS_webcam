# stereo_depth.py — turns a rectified stereo pair into 3D points, and fits
# planes to regions of them.
#
# This module is deliberately shared between the diagnostic tool
# (stereo_check.py) and the eventual measurement pipeline, so that validating
# the diagnostics validates the thing that actually measures packages. If the
# two had separate depth code, a passing test would prove nothing about
# production.
#
# Coordinate frame: the rectified LEFT camera. X right, Y down, Z away from
# the camera along its optical axis. Because the calibration board was
# measured in centimetres, every value here is in centimetres too.

import os
import numpy as np
import cv2

CALIB_DIR = "calib"


def _round_to_16(v):
    """SGBM requires numDisparities to be a positive multiple of 16."""
    return max(16, int(np.ceil(v / 16.0)) * 16)


class StereoDepth:
    """Rectifies a stereo pair and computes a 3D point per pixel."""

    def __init__(self, params, calib_path=None):
        path = calib_path or os.path.join(CALIB_DIR, "stereo_calib.npz")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{path} not found — run 'py calibrate.py stereo' first.")

        cal = np.load(path)
        self.image_size = tuple(int(v) for v in cal["image_size"])
        self.Q = cal["Q"]
        self.baseline_cm = float(cal["baseline_cm"])
        self.focal_px = float(cal["P2"][0, 0])
        self.rms = float(cal["rms"])

        self.map1x, self.map1y = cv2.initUndistortRectifyMap(
            cal["K1"], cal["d1"], cal["R1"], cal["P1"],
            self.image_size, cv2.CV_16SC2)
        self.map2x, self.map2y = cv2.initUndistortRectifyMap(
            cal["K2"], cal["d2"], cal["R2"], cal["P2"],
            self.image_size, cv2.CV_16SC2)

        self._build_matcher(params)

    # -- disparity search range -------------------------------------------
    #
    # Derived from the rig geometry rather than guessed. Disparity and depth
    # are reciprocal (d = f*B/Z), so the floor — the farthest surface — gives
    # the smallest disparity, and the top of the tallest parcel gives the
    # largest. Searching outside that band only costs time and invites
    # mismatches.

    def _build_matcher(self, params):
        height = float(params["nominal_height_cm"])
        max_parcel = float(params["max_parcel_height_cm"])
        fb = self.focal_px * self.baseline_cm

        z_far = height                      # conveyor surface
        z_near = max(height - max_parcel, 5.0)   # top of the tallest parcel

        d_min = fb / z_far
        d_max = fb / z_near

        # Pad both ends by 10% so a slightly-off nominal height, or a parcel
        # a little taller than expected, does not fall outside the search.
        span = d_max - d_min
        d_min = max(0.0, d_min - 0.1 * span)
        d_max = d_max + 0.1 * span

        self.min_disparity = int(np.floor(d_min / 16.0) * 16)
        self.num_disparities = _round_to_16(d_max - self.min_disparity)

        block = int(params["sgbm_block_size"])
        if block % 2 == 0:
            block += 1

        self.matcher = cv2.StereoSGBM_create(
            minDisparity=self.min_disparity,
            numDisparities=self.num_disparities,
            blockSize=block,
            # P1/P2 penalise disparity changes between neighbouring pixels.
            # The standard scaling keeps them proportional to block area.
            P1=8 * 3 * block * block,
            P2=32 * 3 * block * block,
            disp12MaxDiff=1,
            uniquenessRatio=int(params["sgbm_uniqueness"]),
            speckleWindowSize=int(params["sgbm_speckle_window"]),
            speckleRange=int(params["sgbm_speckle_range"]),
            mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
        )

    def describe(self):
        return (f"calib rms={self.rms:.3f} px  baseline={self.baseline_cm:.2f} cm  "
                f"f={self.focal_px:.1f} px\n"
                f"disparity search: {self.min_disparity} .. "
                f"{self.min_disparity + self.num_disparities} px  "
                f"(depth {self.disparity_to_depth(self.min_disparity + self.num_disparities):.1f}"
                f" .. {self.disparity_to_depth(self.min_disparity):.1f} cm)")

    def disparity_to_depth(self, d):
        if d <= 0:
            return float("inf")
        return self.focal_px * self.baseline_cm / d

    # -- per-frame ---------------------------------------------------------

    def rectify(self, frame_left, frame_right):
        return (cv2.remap(frame_left, self.map1x, self.map1y, cv2.INTER_LINEAR),
                cv2.remap(frame_right, self.map2x, self.map2y, cv2.INTER_LINEAR))

    def disparity(self, rect_left, rect_right):
        """Returns float32 disparity in pixels, with invalid pixels as NaN.

        SGBM returns fixed-point values scaled by 16, and marks pixels it
        could not match with a value below minDisparity."""
        gray_l = cv2.cvtColor(rect_left, cv2.COLOR_BGR2GRAY)
        gray_r = cv2.cvtColor(rect_right, cv2.COLOR_BGR2GRAY)
        raw = self.matcher.compute(gray_l, gray_r).astype(np.float32) / 16.0
        raw[raw < self.min_disparity + 0.5] = np.nan
        return raw

    def points_3d(self, disparity):
        """Reprojects disparity to a HxWx3 array of 3D points, in cm.
        Unmatched pixels come back as NaN."""
        safe = np.nan_to_num(disparity, nan=self.min_disparity - 1.0)
        pts = cv2.reprojectImageTo3D(safe, self.Q)
        pts[np.isnan(disparity)] = np.nan
        return pts

    @staticmethod
    def density(disparity):
        """Fraction of pixels that got a valid match. This is the single most
        useful diagnostic on cardboard: a low number means the surface has too
        little texture for block matching, not that the calibration is bad."""
        return float(np.count_nonzero(~np.isnan(disparity))) / disparity.size


# ---------------------------------------------------------------------------
# Plane fitting
# ---------------------------------------------------------------------------

def fit_plane(points):
    """Least-squares plane through an Nx3 array of points.

    Returns (centroid, unit_normal, rms_residual_cm), or None if there are too
    few valid points. The RMS residual is how flat the fit actually came out —
    on a genuinely flat surface it is a direct read on the rig's depth noise.
    """
    pts = points.reshape(-1, 3)
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(pts) < 50:
        return None

    # Discard gross outliers before fitting: a few badly mismatched pixels
    # would otherwise tilt the plane and inflate the residual.
    z = pts[:, 2]
    lo, hi = np.percentile(z, [2, 98])
    pts = pts[(z >= lo) & (z <= hi)]
    if len(pts) < 50:
        return None

    centroid = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - centroid, full_matrices=False)
    normal = vt[2]
    if normal[2] < 0:            # keep the normal pointing back at the camera
        normal = -normal

    residuals = (pts - centroid) @ normal
    return centroid, normal, float(np.sqrt((residuals ** 2).mean()))


def height_above(reference, centroid):
    """Perpendicular distance from a reference plane to a point, in cm.

    Measured along the reference plane's own normal rather than along the
    camera axis, so a conveyor that is not exactly perpendicular to the
    cameras does not bias the height."""
    ref_centroid, ref_normal, _ = reference
    return abs(float((centroid - ref_centroid) @ ref_normal))


def tilt_degrees(normal):
    """Angle between a plane normal and the camera's optical axis."""
    axis = np.array([0.0, 0.0, 1.0])
    cos = abs(float(normal @ axis)) / (np.linalg.norm(normal) + 1e-12)
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))
