# camera_config.py — opens webcams with identical, locked capture settings.
#
# Every part of the stereo system (calibration AND measurement) opens cameras
# through this module. That is the whole point of it: a calibration is only
# valid for the exact optical configuration it was captured under, so if the
# measurement code opened cameras with different settings than the calibration
# tool did, the calibration would be silently wrong.
#
# Three settings matter more than people expect:
#   * AUTOFOCUS  — a refocus changes the focal length, which invalidates the
#                  intrinsics outright. This is the big one.
#   * EXPOSURE   — must match BETWEEN the two cameras or stereo matching
#                  degrades, and must match between calibration and runtime.
#   * FOURCC     — uncompressed YUY2 at 1280x720x30 is ~55 MB/s per camera.
#                  USB 2.0 delivers ~35-40 MB/s in total, so one raw stream
#                  already exceeds the bus and two will fail or silently drop
#                  frames. MJPEG is not optional here.

import sys
import yaml
import cv2

DEFAULT_PARAMS = "stereo_params.yaml"


def load_params(path=DEFAULT_PARAMS):
    """Reads stereo_params.yaml and returns it as a plain dict."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _backend():
    """DirectShow on Windows (what the warehouse PCs run), default elsewhere
    so the tooling stays runnable on Linux/macOS for development."""
    return cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY


def open_camera(index, params):
    """Opens one camera with the locked settings from stereo_params.yaml.

    Returns an opened cv2.VideoCapture, or None if the device could not be
    opened. Order matters: FOURCC before resolution, or the driver may refuse
    the requested size and quietly fall back to something smaller."""
    cap = cv2.VideoCapture(index, _backend())
    if not cap.isOpened():
        print(f"Error: could not open camera at index {index}.")
        return None

    # MJPEG first — see the note at the top of this file.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  params["frame_width"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, params["frame_height"])

    # Lock the focus. On cameras without autofocus this is a harmless no-op.
    cap.set(cv2.CAP_PROP_AUTOFOCUS, params["autofocus"])

    # 0.25 = manual exposure under DirectShow (0.75 would be auto). The V4L2
    # backend uses 1 = manual instead, hence the platform split.
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25 if sys.platform == "win32" else 1)
    cap.set(cv2.CAP_PROP_EXPOSURE, params["exposure"])

    cap.set(cv2.CAP_PROP_AUTO_WB, params["auto_wb"])

    return cap


def describe_camera(cap, label):
    """Prints what the driver actually gave us, which is often not what was
    asked for. Worth reading before trusting a calibration run."""
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc_val = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc = "".join(chr((fourcc_val >> (8 * i)) & 0xFF) for i in range(4))
    print(f"  {label}: {w}x{h}  fourcc={fourcc!r}  "
          f"exposure={cap.get(cv2.CAP_PROP_EXPOSURE)}")
    return w, h


def check_resolution_match(size_left, size_right):
    """Stereo calibration requires both cameras at the same resolution."""
    if size_left != size_right:
        print(f"Error: cameras are at different resolutions "
              f"({size_left} vs {size_right}). Stereo calibration requires "
              f"both at the same size. Check that both support "
              f"{size_left[0]}x{size_left[1]} over MJPEG.")
        return False
    return True
