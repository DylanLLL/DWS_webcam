# webcam_cv_mog2_side.py — measures object height from a side view using frame difference background subtraction.
import cv2
import numpy as np
from collections import deque

# pixel to cm calibration ratio (adjust to your setup)
RATIO = 16 / 253

# minimum contour area in pixels to ignore noise
MIN_AREA = 2000
 
# Camera resolution (width x height) — set to None to use camera default
CAMERA_WIDTH  = 1280
CAMERA_HEIGHT = 720

# Temporal smoothing: number of recent frames to average the bounding box over.
SMOOTH_FRAMES = 8

# Floor line: Y-coordinate (pixels from top) of the surface the object rests on.
# Press 'F' while running to set it interactively.
FLOOR_Y = None

# Rolling buffer of recent axis-aligned bbox params: (x, y, w, h)
_bbox_history = deque(maxlen=SMOOTH_FRAMES)

background = None
                   
def draw_side_bbox(frame, contour, ratio, floor_y):
    bx, by, bw, bh = cv2.boundingRect(contour)

    if floor_y is not None and (by + bh) < floor_y:
        bh = floor_y - by

    _bbox_history.append((bx, by, bw, bh))

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


def main(shared_h=None):

    global background, _bbox_history, FLOOR_Y

    cap = cv2.VideoCapture(2, cv2.CAP_DSHOW)

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

    print("Keep the scene EMPTY, then press B to capture background.")
    print("Controls:  B = capture background   F = set floor line   R = reset   ESC = quit")

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
            FLOOR_Y = None
            print("Reset — remove object and press B to recapture background.")

        if key == ord('f') or key == ord('F'):
            contour_now = segment_largest_object(frame)
            if contour_now is not None:
                _, by_now, _, bh_now = cv2.boundingRect(contour_now)
                FLOOR_Y = by_now + bh_now
                print(f"Floor line set at y={FLOOR_Y} px")
            else:
                print("No object detected — place object on surface first, then press F.")

        if background is None:
            cv2.putText(frame, "Press B to capture background (keep scene empty)",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        else:
            contour = segment_largest_object(frame)

            if contour is not None:
                cv2.drawContours(frame, [contour], -1, (255, 80, 0), 1)
                h_cm = draw_side_bbox(frame, contour, RATIO, FLOOR_Y)

                if shared_h is not None:
                    shared_h["value"] = h_cm
            else:
                if shared_h is not None:
                    shared_h["value"] = 0.0
                cv2.putText(frame, "No object detected  (R to reset background)",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        if FLOOR_Y is not None:
            cv2.line(frame, (0, FLOOR_Y), (frame.shape[1], FLOOR_Y), (0, 165, 255), 1)
            cv2.putText(frame, "floor", (5, FLOOR_Y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)

        cv2.imshow("side camera - height", frame)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main() 