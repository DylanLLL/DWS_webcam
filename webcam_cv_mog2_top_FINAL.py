# webcam_cv_mog2_top_FINAL.py - PRESS B TO CAPTURE BACKGROUND, THEN PLACE OBJECT (updated method)
import cv2
import numpy as np
from collections import deque
from smoothing import MovingAverage
from params_utils import load_ratio, load_camera_index

# real-world cm per pixel at the calibration distance, loaded from params.yaml
RATIO = load_ratio("ratio_top")

# NEW: camera index loaded from params.yaml
CAMERA_INDEX = load_camera_index("camera_index_top")

D_FLOOR_TOP = 100

MIN_AREA = 2000

CAMERA_WIDTH  = 1280
CAMERA_HEIGHT = 720

SMOOTH_FRAMES = 8

background = None  # replaces MOG2 — same approach as side camera

_bbox_history: deque = deque(maxlen=SMOOTH_FRAMES)

_l_avg = MovingAverage(maxlen=15)
_w_avg = MovingAverage(maxlen=15)

def segment_largest_object(frame):
    if background is None:
        return None

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray_bg    = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)

    gray_frame = cv2.GaussianBlur(gray_frame, (5, 5), 0)
    gray_bg    = cv2.GaussianBlur(gray_bg,    (5, 5), 0)

    diff = cv2.absdiff(gray_bg, gray_frame)

    _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

    kernel = np.ones((5, 5), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN,  kernel)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    thresh = cv2.dilate(thresh, kernel, iterations=2)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)

    if cv2.contourArea(largest) < MIN_AREA:
        return None

    return cv2.convexHull(largest)

def draw_oriented_bbox(frame, contour, ratio, shared_dims=None):
    rect = cv2.minAreaRect(contour)
    cx_raw, cy_raw = rect[0]
    w_raw, l_raw   = rect[1]
    angle_raw      = rect[2] 

    if w_raw < l_raw:
        w_raw, l_raw = l_raw, w_raw
        angle_raw = (angle_raw + 90) % 180

    _bbox_history.append((cx_raw, cy_raw, w_raw, l_raw, angle_raw))

    arr = np.array(_bbox_history)
    cx, cy, w_px, l_px, angle = arr.mean(axis=0)

    smooth_rect = ((cx, cy), (w_px, l_px), angle)
    box = cv2.boxPoints(smooth_rect)
    box = np.intp(box)

    cv2.drawContours(frame, [box], 0, (0, 255, 0), 2)

    w_cm_raw = w_px * ratio
    l_cm_raw = l_px * ratio

    w_cm = _w_avg.update(w_cm_raw)
    l_cm = _l_avg.update(l_cm_raw)

    cv2.putText(frame, f"W: {w_cm:.2f} cm", (int(cx) - 70, int(cy) - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"L: {l_cm:.2f} cm", (int(cx) - 70, int(cy) + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    if shared_dims is not None:
        shared_dims["L"] = l_cm
        shared_dims["W"] = w_cm
        shared_dims["L_ready"] = _l_avg.ready()
        shared_dims["W_ready"] = _w_avg.ready()

def main(shared_h=None, shared_dims=None):

    global background, _bbox_history

    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)   # CHANGED: was hardcoded 0

    if not cap.isOpened():
        print(f"Error: could not open camera at index {CAMERA_INDEX}.")
        return

    if CAMERA_WIDTH and CAMERA_HEIGHT:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Camera resolution: {actual_w}x{actual_h}"
              f"  (requested {CAMERA_WIDTH}x{CAMERA_HEIGHT})")

    print("Keep the scene EMPTY, then press B to capture background.")
    print("Controls:  B = capture background   R = reset   ESC = quit")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: failed to read frame.")
            break

        key = cv2.waitKey(1)

        if key == 27:  # ESC
            break

        if key == ord('b') or key == ord('B'):
            background = frame.copy()
            _bbox_history.clear()
            print("Background captured — now place your object.")

        if key == ord('r') or key == ord('R'):
            background = None
            _bbox_history.clear()
            print("Reset — remove object and press B to recapture background.")

        if background is None:
            cv2.putText(frame, "Press B to capture background (keep scene empty)",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        else:
            l_object = shared_h["value"] if shared_h is not None else 0.0
            ratio_corrected = RATIO * (1.0 - l_object / D_FLOOR_TOP)

            contour = segment_largest_object(frame)

            if contour is not None:
                cv2.drawContours(frame, [contour], -1, (255, 80, 0), 1)
                draw_oriented_bbox(frame, contour, ratio_corrected, shared_dims)
                cv2.putText(frame, f"obj H: {l_object:.2f} cm",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                cv2.putText(frame, f"ratio: {ratio_corrected:.5f}",
                            (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            else:
                if shared_dims is not None:
                    shared_dims["L_ready"] = False
                    shared_dims["W_ready"] = False
                cv2.putText(frame, "No object detected  (R to reset background)",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        cv2.imshow("frame", frame)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()