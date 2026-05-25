import cv2
import math
import numpy as np
from ultralytics import YOLO

# ── Config ────────────────────────────────────────────────────────────────────
RATIO = 21 / 211  # cm per pixel (your existing calibration)
MODEL_PATH = "yolov8n-seg.pt"  # downloads automatically on first run
# ─────────────────────────────────────────────────────────────────────────────

model = YOLO(MODEL_PATH)

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

# ── Camera resolution ─────────────────────────────────────────────────────────
# CAMERA_WIDTH  = 1280
# CAMERA_HEIGHT = 720
# if CAMERA_WIDTH and CAMERA_HEIGHT:
#     cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
#     cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
# ─────────────────────────────────────────────────────────────────────────────

def get_axes(rect):
    """Return endpoints of the major and minor axes of a rotated rect."""
    center, size, angle = rect
    cx, cy = center
    w, h = size
    angle_rad = math.radians(angle)

    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # Half-lengths along each axis
    hw = w / 2  # major
    hh = h / 2  # minor

    major_end1 = (int(cx - cos_a * hw), int(cy - sin_a * hw))
    major_end2 = (int(cx + cos_a * hw), int(cy + sin_a * hw))
    minor_end1 = (int(cx + sin_a * hh), int(cy - cos_a * hh))
    minor_end2 = (int(cx - sin_a * hh), int(cy + cos_a * hh))

    return major_end1, major_end2, minor_end1, minor_end2


while True:
    ret, frame = cap.read()
    if not ret:
        break

    # ── Run YOLO segmentation ─────────────────────────────────────────────────
    results = model(frame, verbose=False)

    for result in results:
        if result.masks is None:
            continue

        for segment_xy in result.masks.xy:          # each detected object
            if len(segment_xy) < 5:
                continue

            segment = segment_xy.astype(np.int32)

            # ── Oriented bounding box ─────────────────────────────────────────
            rect = cv2.minAreaRect(segment)
            box = cv2.boxPoints(rect)
            box = np.int32(box)

            center, size, angle = rect
            cx, cy = int(center[0]), int(center[1])

            # ── Convert px → cm ──────────────────────────────────────────────
            size_w_cm = round(size[0] * RATIO, 2)
            size_h_cm = round(size[1] * RATIO, 2)

            # Make sure the larger dimension is always "width"
            dim1_cm = max(size_w_cm, size_h_cm)
            dim2_cm = min(size_w_cm, size_h_cm)

            # ── Draw rotated bounding box ─────────────────────────────────────
            cv2.drawContours(frame, [box], 0, (0, 255, 0), 2)

            # ── Draw major / minor axes ───────────────────────────────────────
            maj1, maj2, min1, min2 = get_axes(rect)
            cv2.line(frame, maj1, maj2, (25, 15, 215), 2)   # major — blue
            cv2.line(frame, min1, min2, (215, 15, 25), 2)   # minor — red

            # ── Label at center ───────────────────────────────────────────────
            label = f"{dim1_cm} x {dim2_cm} cm"
            cv2.putText(frame, label, (cx - 60, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    cv2.imshow("Frame", frame)
    if cv2.waitKey(1) == 27:   # ESC to quit
        break

cap.release()
cv2.destroyAllWindows()