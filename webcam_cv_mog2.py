#webcam_cv_mog2.py — detects and measures the largest object in the webcam feed using MOG2 background subtraction.
import cv2
import numpy as np
from collections import deque
import multiprocessing

RATIO = 21.1 / 299

# physical distance from top camera lens to table surface, in cm.
# Measure this once with a ruler.
D_FLOOR_TOP = 100   

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


def make_subtractor():
    """Creates a fresh MOG2 background subtractor."""
    # detectShadows=True marks shadow pixels as 127 (we exclude them)
    return cv2.createBackgroundSubtractorMOG2(
        history=WARMUP_FRAMES, varThreshold=50, detectShadows=True
    )


mog2 = make_subtractor()

# Rolling buffer of recent bounding box params: (cx, cy, w_px, h_px, angle)
_bbox_history: deque = deque(maxlen=SMOOTH_FRAMES)


def segment_largest_object(frame, learning_rate=0):
    """
    Uses MOG2 to detect the largest foreground object.
    Works in full color — hue differences are captured even at similar brightness.

    learning_rate=0 freezes the background model once warmup is done,
    preventing a static object from being absorbed into the background.
    Returns the largest convex hull contour, or None.
    """
    # apply() returns: 255 = foreground, 127 = shadow, 0 = background
    fg_mask = mog2.apply(frame, learningRate=learning_rate)

    # Discard shadow pixels (127), keep only definite foreground (255)
    _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

    # Morphological cleanup: fill holes, remove noise
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


def draw_oriented_bbox(frame, contour, ratio):
    """
    Fits an oriented bounding box to the contour, smooths it over recent
    frames via _bbox_history, draws it, and annotates width/height in cm.
    """
    rect = cv2.minAreaRect(contour)
    cx_raw, cy_raw = rect[0]
    w_raw, h_raw   = rect[1]
    angle_raw      = rect[2]

    # Normalize so the longer axis is always "width"
    if w_raw < h_raw:
        w_raw, h_raw = h_raw, w_raw
        angle_raw = (angle_raw + 90) % 180

    _bbox_history.append((cx_raw, cy_raw, w_raw, h_raw, angle_raw))

    # Average over the rolling window
    arr  = np.array(_bbox_history)
    cx, cy, w_px, h_px, angle = arr.mean(axis=0)

    # Reconstruct a smoothed rect and draw it
    smooth_rect = ((cx, cy), (w_px, h_px), angle)
    box = cv2.boxPoints(smooth_rect)
    box = np.intp(box)

    cv2.drawContours(frame, [box], 0, (0, 255, 0), 2)

    w_cm = w_px * ratio
    h_cm = h_px * ratio

    cv2.putText(frame, f"W: {w_cm:.2f} cm", (int(cx) - 70, int(cy) - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"H: {h_cm:.2f} cm", (int(cx) - 70, int(cy) + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
# main() wraps everything so launcher.py can pass in shared_h
def main(shared_h=None):

    global mog2, _bbox_history

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print("Error: could not open camera.")
        return

    if CAMERA_WIDTH and CAMERA_HEIGHT:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Camera resolution: {actual_w}x{actual_h}"
            f"  (requested {CAMERA_WIDTH}x{CAMERA_HEIGHT})")

    print("Keep the scene EMPTY while the background model warms up.")
    print("Controls:  R = reset background model   ESC = quit")

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

        frame_count += 1

        if frame_count <= WARMUP_FRAMES:
            # Train MOG2 on the empty background (learning rate -1 = auto)
            mog2.apply(frame, learningRate=-1)
            remaining = WARMUP_FRAMES - frame_count
            cv2.putText(frame, f"Learning background... ({remaining} frames left)",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
        else:
            # NEW: read H from side camera; default to 0.0 if unavailable
            h_object = shared_h["value"] if shared_h is not None else 0.0

            # NEW: compute corrected ratio based on object height
            ratio_corrected = RATIO * (1.0 - h_object / D_FLOOR_TOP)     

            contour = segment_largest_object(frame, learning_rate=0)

            if contour is not None:
                cv2.drawContours(frame, [contour], -1, (255, 80, 0), 1)
                draw_oriented_bbox(frame, contour, ratio_corrected)
                # NEW: show the live H and corrected ratio on screen for debugging
                cv2.putText(frame, f"obj H: {h_object:.2f} cm",           
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX,           
                            0.6, (255, 255, 0), 2)                        
                cv2.putText(frame, f"ratio: {ratio_corrected:.5f}",       
                            (10, 58), cv2.FONT_HERSHEY_SIMPLEX,           
                            0.6, (255, 255, 0), 2)                        
            else:
                cv2.putText(frame, "No object detected  (R to reset background)",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        cv2.imshow("frame", frame)

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":                     
    main()
# This code uses MOG2 background subtraction to detect the largest moving object in the webcam feed,
