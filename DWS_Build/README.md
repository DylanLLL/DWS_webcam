# DWS — Dimension and Weight Measuring System

## Description

DWS is a Python/OpenCV-based system that automatically measures the **length**, **width**, and **height** of a package using two webcams, then pastes all three dimensions — along with a weight value read from a separate scale application (VIKT) — directly into a warehouse dashboard with a single hotkey press.

The system uses two cameras:
- A **top camera** that measures length and width by detecting the package's outline from above.
- A **side camera** that measures height by detecting the package's outline from the side.

Both cameras use static background-frame differencing (capture an empty background once, then detect whatever changes when a package is placed) rather than continuous background modeling, since packages are placed and removed intermittently rather than moving continuously through frame.

The top camera's length/width readings are automatically corrected based on the live height reading from the side camera, since a taller object sits closer to the top camera's lens and appears larger in the frame than its true footprint — a parallax correction is applied to account for this.

All three dimensions are smoothed using a rolling moving average to reduce noise from lighting changes or minor detection jitter, and are only considered "ready" to output once the averaging window is fully populated with stable readings.

Once length, width, and height are stable, and a valid weight is available from VIKT's clipboard output, a single hotkey pastes all four values into the warehouse dashboard's input fields automatically, then resets the system for the next package.

## Files

| File | Purpose |
|---|---|
| `launcher.py` | Main entry point. Starts both camera windows, monitors when readings are stable, listens for the dashboard hotkey (to paste L/W/H/Weight) and the kill hotkey (to force-quit everything), and reads weight from the clipboard. |
| `webcam_cv_mog2_top_FINAL.py` | Top camera. Detects the package outline from above, computes length and width in cm, applies the height-based parallax correction, and smooths the result with a moving average. |
| `webcam_cv_mog2_side_FINAL.py` | Side camera. Detects the package's height from the side view using a manually-set floor line, and smooths the result with a moving average. |
| `smoothing.py` | Defines the `MovingAverage` class used by both camera files to stabilize raw pixel-to-cm readings over a rolling window of frames. |
| `params_utils.py` | Helper functions (`load_ratio`, `load_camera_index`) that read calibration ratios and camera indices from `params.yaml`. |
| `params.yaml` | External, user-editable configuration file — hotkeys, pixel-to-cm calibration ratios, and camera device indices. Lets warehouse staff adjust settings without touching any code. |
| `ratio_calibration.py` | Standalone calibration tool. Lets you click two points on a pre-measured object in either camera's view and reads out the pixel distance between them, which you then divide by the object's known real-world length to get the calibration ratio for `params.yaml`. |

## Requirements

Install the required Python packages:

```
pip install opencv-python numpy pyyaml keyboard pyautogui pyperclip
```

You'll also need two USB webcams connected to the machine — one mounted overhead (top camera) and one mounted to the side (side camera).

## Setup

### 1. Determine camera indices

The camera indices can vary between systems and even between restarts/reboots. Test the camera indices by typing either 0 or 1 when `DWS_Calibration.exe` is started. Note which index corresponds to the top camera and which to the side camera (you can tell by observing the live feed if needed).

Note: if not starting, use this command in Terminal: py .\ratio_calibration.py

### 2. Calibrate each camera

Run `DWS_Calibration.exe`. It will prompt you for a camera index — enter the index of the camera you want to calibrate first.

- Place the flat piece of paper in view of the camera.
- Click two points in the video window corresponding to the two edges of the known measurement.
- The on-screen text will show the pixel distance between the two points.
- Divide the known real-world length (in cm) by the pixel distance to get your ratio, or simply note both numbers to enter as a fraction. (cm/px) 

Repeat this process for both the top and side cameras (closing and rerunning the tool, entering the other camera's index each time).

### 3. Fill in `params.yaml`

Open `params.yaml` in any text editor (NOTEPAD) and fill in the values found above:

```yaml
# params.yaml
dashboard_hotkey: f11      # hotkey that pastes L/W/H/Weight into the dashboard
kill_hotkey: f12           # hotkey that force-closes the whole program

# Pixel-to-cm calibration ratios, written as "numerator / denominator"
ratio_top: "7.5 / 93"  # KEEP THE QUOTATION MARKS ""
ratio_side: "23 / 192"  # KEEP THE QUOTATION MARKS ""

# Camera device indices, determined in step 1
camera_index_top: 0
camera_index_side: 1
```

You can edit any of these values at any time and simply relaunch the program --> NO NEED to change code or rebuild.

### 4. Run the system

Click the .exe
`DWS_Launcher.exe`

Two camera windows will open. For each camera:
- Keep the scene **empty**, then press **B** to capture the background.
- Place the package in view — the system will begin detecting and measuring it.
- Press **R** at any time to reset and recapture the background.
- On the side camera specifically, press **F** once an object is in place to set the floor line (the reference point height is measured from). (NOT NECESSARY UNLESS TRULY NEEDED)

Once length, width, and height readings have stabilized (their moving-average windows are fully populated), and a valid weight has been copied to the clipboard by VIKT, press the **dashboard hotkey** (default `F11`) to paste all four values into the currently focused dashboard field. The system will then reset itself automatically, ready for the next package.

Press the **kill hotkey** (default `F12`) at any time to immediately close the entire program, including both camera windows.

## Notes

- The weight value is read from the system clipboard, which VIKT (the separate Java scale application) automatically populates whenever a stable weight reading is detected. Both programs must be running at the same time for the weight paste to work, but they run entirely independently. There is no direct communication between them beyond the clipboard.
- If a package is removed mid-measurement, or if any of the three dimensions destabilizes, the system will not allow a hotkey paste until all readings are stable again.
- Calibration ratios are stored as fraction strings (e.g. `"7.5 / 93"`) rather than pre-computed decimals, so they can be edited directly without needing to do the division by hand.