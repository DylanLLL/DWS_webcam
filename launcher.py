# launcher.py
import threading
import time
import keyboard
import pyautogui
import webcam_cv_mog2 as top_cam
import webcam_cv_mog2_side as side_cam


def build_output_string(shared_dims, shared_h):
    L = shared_dims["L"]
    W = shared_dims["W"]
    H = shared_h["value"]
    return f"{L:.2f};{W:.2f};{H:.2f}"


def reset_dimensions(shared_dims, shared_h):
    """Clears current values, moving-average windows, and ready flags
    so the next object starts with a clean slate."""
    shared_dims["L"] = 0.0
    shared_dims["W"] = 0.0
    shared_dims["L_ready"] = False
    shared_dims["W_ready"] = False
    shared_h["value"] = 0.0
    shared_h["ready"] = False

    top_cam._l_avg.window.clear()
    top_cam._w_avg.window.clear()
    side_cam._h_avg.window.clear()


def dashboard_input_listener(shared_dims, shared_h, stop_event):
    """Waits for F7. When pressed, types L/W/H into the dashboard's focused
    field, tabbing between each, then resets values for the next object."""
    while not stop_event.is_set():
        if keyboard.is_pressed('f7'):
            if shared_dims.get("L_ready") and shared_dims.get("W_ready") and shared_h.get("ready"):
                L = f"{shared_dims['L']:.2f}"
                W = f"{shared_dims['W']:.2f}"
                H = f"{shared_h['value']:.2f}"

                pyautogui.typewrite(L, interval=0.01)
                pyautogui.press('tab', presses=2, interval=0.05)
                pyautogui.typewrite(W, interval=0.01)
                pyautogui.press('tab', presses=2, interval=0.05)
                pyautogui.typewrite(H, interval=0.01)

                print(f"Entered into dashboard: L={L} W={W} H={H}")
                reset_dimensions(shared_dims, shared_h)
            else:
                print("F7 pressed but values not yet stable — ignored.")

            # Debounce: wait for key release so one press doesn't fire multiple times
            while keyboard.is_pressed('f7'):
                time.sleep(0.05)

        time.sleep(0.05)


def monitor_output(shared_dims, shared_h, stop_event):
    last_all_ready = False
    while not stop_event.is_set():
        all_ready = (
            shared_dims.get("L_ready", False)
            and shared_dims.get("W_ready", False)
            and shared_h.get("ready", False)
        )
        if all_ready:
            print(build_output_string(shared_dims, shared_h))
        elif last_all_ready and not all_ready:
            print("Object removed or readings destabilized — waiting to restabilize...")
        last_all_ready = all_ready
        time.sleep(0.5)


if __name__ == "__main__":
    shared_h    = {"value": 0.0, "ready": False}
    shared_dims = {"L": 0.0, "W": 0.0,
                   "L_ready": False, "W_ready": False}

    stop_event = threading.Event()

    t_side      = threading.Thread(target=side_cam.main, args=(shared_h,))
    t_top       = threading.Thread(target=top_cam.main,  args=(shared_h, shared_dims))
    t_monitor   = threading.Thread(target=monitor_output, args=(shared_dims, shared_h, stop_event))
    t_dashboard = threading.Thread(target=dashboard_input_listener, args=(shared_dims, shared_h, stop_event))

    t_side.start()
    t_top.start()
    t_monitor.start()
    t_dashboard.start()

    t_side.join()
    t_top.join()

    stop_event.set()
    t_monitor.join()
    t_dashboard.join()