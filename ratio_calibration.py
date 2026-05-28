import cv2
import math 
points = []

# RATIO = 23 / 370 # real-world cm per pixel at the calibration distance (20 cm / 190 px)

def draw_circle(event, x, y, flags, param):
    global points
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(points) == 2:
            points = []
        points.append((x, y))

cv2.namedWindow("Frame")
cv2.setMouseCallback("Frame", draw_circle)

cap = cv2.VideoCapture(2,cv2.CAP_DSHOW)

CAMERA_WIDTH  = 1280
CAMERA_HEIGHT = 720
if CAMERA_WIDTH and CAMERA_HEIGHT:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

while True: 
    _, frame = cap.read()
    if not _:
        break

    for pt in points:
        cv2.circle(frame, pt, 5, (0, 0, 255), -1)

    # Measure distance between 2 points 
    if len(points) == 2:
        pt1 = points[0]
        pt2 = points[1]
        distance_px = math.hypot(pt2[0] - pt1[0], pt2[1] - pt1[1]) 

        # distance to cm 
        # distance_cm = RATIO * distance_px

        cv2.putText(frame,fr"{int(distance_px)} px", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    cv2.imshow("Frame", frame)
    key = cv2.waitKey(1) 

    if key == 27: # ESC key to exit
        break

cap.release()  
cv2.destroyAllWindows()