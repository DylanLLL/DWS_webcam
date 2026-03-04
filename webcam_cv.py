import cv2
import numpy as np

# pixel to cm calibration ratio (adjust to your setup)
RATIO = 10 / 142

# minimum contour area in pixels to ignore noise
MIN_AREA = 2000

# how sensitive the difference detection is (lower = more sensitive)
DIFF_THRESHOLD = 65

background = None


def capture_background(frame):
    """Stores a blurred grayscale snapshot of the empty scene."""
    global background
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    background = cv2.GaussianBlur(gray, (7, 7), 0)


def segment_largest_object(frame):
    """
    Detects the largest object that differs from the captured background.
    Returns the largest contour, or None if nothing significant is found.
    """
    if background is None:
        return None

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)

    # Pixels that changed significantly from the empty background
    diff = cv2.absdiff(background, blur)
    _, thresh = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)

    # Morphological cleanup: fill holes inside the object, remove noise
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=3)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN,  kernel, iterations=1)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)

    if cv2.contourArea(largest) < MIN_AREA:
        return None

    # Convex hull removes shadow dents and noise protrusions from the contour
    return cv2.convexHull(largest)


def draw_oriented_bbox(frame, contour, ratio):
    """
    Fits an oriented bounding box to the contour, draws it,
    and annotates width and height in cm.
    """
    # minAreaRect returns ((cx,cy), (w,h), angle)
    rect = cv2.minAreaRect(contour)
    box  = cv2.boxPoints(rect)
    box  = np.intp(box)

    cv2.drawContours(frame, [box], 0, (0, 255, 0), 2)

    w_px, h_px = rect[1]

    # Ensure the longer axis is always "width"
    if w_px < h_px:
        w_px, h_px = h_px, w_px

    w_cm = w_px * ratio
    h_cm = h_px * ratio

    cx, cy = int(rect[0][0]), int(rect[0][1])
    cv2.putText(frame, f"W: {w_cm:.2f} cm", (cx - 70, cy - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"H: {h_cm:.2f} cm", (cx - 70, cy + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)


cap = cv2.VideoCapture(2)

if not cap.isOpened():
    print("Error: could not open camera.")
    exit(1)

print("Controls:  B = capture background   ESC = quit")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Error: failed to read frame.")
        break

    key = cv2.waitKey(1)
    if key == 27:   # ESC
        break
    if key == ord('b') or key == ord('B'):
        capture_background(frame)
        print("Background captured.")

    if background is None:
        cv2.putText(frame, "Press B to capture empty background",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
    else:
        contour = segment_largest_object(frame)

        if contour is not None:
            cv2.drawContours(frame, [contour], -1, (255, 80, 0), 1)
            draw_oriented_bbox(frame, contour, RATIO)
        else:
            cv2.putText(frame, "No object detected  (B to recapture background)",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    cv2.imshow("frame", frame)

cap.release()
cv2.destroyAllWindows()
