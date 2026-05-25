# webcam_cv_mog2_side.py — measures object height from a side view using MOG2 background subtraction.
import cv2
import numpy as np
from collections import deque
import multiprocessing 

# pixel to cm calibration ratio (adjust to your setup)
RATIO = 10 / 142

# minimum contour area in pixels to ignore noise
MIN_AREA = 2000

# Number of frames to silently feed MOG2 before measuring
# (keep the scene empty during this period)
WARMUP_FRAMES = 300

# Camera resolution (width x height) — set to None to use camera default
CAMERA_WIDTH  = 1280
CAMERA_HEIGHT = 720

# Temporal smoothing: number of recent frames to average the bounding box over.
# Higher = smoother but slower to react. Range: 3–15
SMOOTH_FRAMES = 8

# Floor line: Y-coordinate (pixels from top) of the surface the object rests on.
# Press 'F' while running to set it interactively.
# Set to None to use the bottom of the detected bounding box instead.
FLOOR_Y = None


def make_subtractor():
    """Creates a fresh MOG2 background subtractor."""
    return cv2.createBackgroundSubtractorMOG2(
        history=WARMUP_FRAMES, varThreshold=50, detectShadows=True
    )


mog2 = make_subtractor()

# Rolling buffer of recent axis-aligned bbox params: (x, y, w, h)
_bbox_history = deque(maxlen=SMOOTH_FRAMES)


def segment_largest_object(frame, learning_rate=0):
    """
    Uses MOG2 to detect the largest foreground object.
    Returns the largest convex hull contour, or None.
    """
    fg_mask = mog2.apply(frame, learningRate=learning_rate)

    # Keep only definite foreground (255); discard shadows (127)
    _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

    # Morphological cleanup: fill holes, remove speckle noise
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN,  kernel, iterations=1)

    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)

    if cv2.contourArea(largest) < MIN_AREA:
        return None

    return cv2.convexHull(largest)


def draw_side_bbox(frame, contour, ratio, floor_y):
    """
    Fits an axis-aligned bounding box to the contour, smooths it over
    recent frames, draws it, and annotates:
      H — object height  (vertical span, from floor_y if set)
      D — object depth   (horizontal span seen from the side)
    """
    bx, by, bw, bh = cv2.boundingRect(contour)

    # If a floor reference is set, extend the box down to it
    if floor_y is not None and (by + bh) < floor_y:
        bh = floor_y - by

    _bbox_history.append((bx, by, bw, bh))

    # Average over the rolling window for a stable readout
    arr = np.array(_bbox_history)
    sx, sy, sw, sh = arr.mean(axis=0)
    sx, sy, sw, sh = int(sx), int(sy), int(sw), int(sh)

    cv2.rectangle(frame, (sx, sy), (sx + sw, sy + sh), (0, 255, 0), 2)

    h_cm = sh * ratio
    d_cm = sw * ratio

    cx = sx + sw // 2
    cy = sy + sh // 2
    cv2.putText(frame, f"H: {h_cm:.2f} cm", (cx - 70, cy - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"D: {d_cm:.2f} cm", (cx - 70, cy + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    return h_cm

# NEW: main() wraps everything so launcher.py can pass in shared_h
def main(shared_h=None):                      

    global mog2, _bbox_history, FLOOR_Y

    cap = cv2.VideoCapture(2)

    if not cap.isOpened():
        print("Error: could not open camera.")
        exit(1)

    if CAMERA_WIDTH and CAMERA_HEIGHT:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Camera resolution: {actual_w}x{actual_h}"
            f"  (requested {CAMERA_WIDTH}x{CAMERA_HEIGHT})")

    print("Keep the scene EMPTY while the background model warms up.")
    print("Controls:  F = set floor line   R = reset background model   ESC = quit")

    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: failed to read frame.")
            break

        key = cv2.waitKey(1)
        if key == 27:  # ESC
            break
        if key == ord('r') or key == ord('R'):
            mog2 = make_subtractor()
            _bbox_history.clear()
            frame_count = 0
            print("Background model reset — keep scene empty during warmup.")
        if key == ord('f') or key == ord('F'):
            contour_now = segment_largest_object(frame, learning_rate=0)
            if contour_now is not None:
                _, by_now, _, bh_now = cv2.boundingRect(contour_now)
                FLOOR_Y = by_now + bh_now
                print(f"Floor line set at y={FLOOR_Y} px")
            else:
                print("No object detected — place object on surface first, then press F.")

        frame_count += 1

        if frame_count <= WARMUP_FRAMES:
            mog2.apply(frame, learningRate=-1)
            remaining = WARMUP_FRAMES - frame_count
            cv2.putText(frame, f"Learning background... ({remaining} frames left)",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
        else:
            contour = segment_largest_object(frame, learning_rate=0)

            if contour is not None:
                cv2.drawContours(frame, [contour], -1, (255, 80, 0), 1)
                draw_side_bbox(frame, contour, RATIO, FLOOR_Y)
            else:
                cv2.putText(frame, "No object detected  (R to reset background)",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        if FLOOR_Y is not None:
            cv2.line(frame, (0, FLOOR_Y), (frame.shape[1], FLOOR_Y), (0, 165, 255), 1)
            cv2.putText(frame, "floor", (5, FLOOR_Y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)

        cv2.imshow("side camera - height", frame)

    cap.release()
    cv2.destroyAllWindows()

# NEW: allows running this file standalone (shared_h defaults to None)
if __name__ == "__main__":
    main()
