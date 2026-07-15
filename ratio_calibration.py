import cv2
import math

points = []

# RATIO = 7.5 / 93 # real-world cm per pixel at the calibration distance (20 cm / 190 px)

def draw_circle(event, x, y, flags, param):
    global points
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(points) == 2:
            points = []
        points.append((x, y))

# Ask which camera index to use
print("Enter the camera index to calibrate.")
print("Not sure which index to use? Run the camera enumeration check first.")
camera_input = input("Camera index (default 0): ").strip()

if camera_input == "":
    camera_index = 0
else:
    try:
        camera_index = int(camera_input)
    except ValueError:
        print(f"'{camera_input}' is not a valid number — defaulting to index 0.")
        camera_index = 0

window_title = f"Frame - camera index {camera_index}"

cv2.namedWindow(window_title)
cv2.setMouseCallback(window_title, draw_circle)

cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)   # CHANGED: uses entered index

if not cap.isOpened():
    print(f"Error: could not open camera at index {camera_index}.")
    print("Try a different index, or run the camera enumeration check to see what's available.")
else:
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

            cv2.putText(frame, fr"{int(distance_px)} px", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        cv2.imshow(window_title, frame)
        key = cv2.waitKey(1)

        if key == 27:  # ESC key to exit
            break

    cap.release()
    cv2.destroyAllWindows()