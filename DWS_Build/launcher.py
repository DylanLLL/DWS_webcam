# launcher.py
import os          # NEW: needed for os._exit()
import threading
import time
import yaml
import keyboard
import pyautogui
import pyperclip
import re
import webcam_cv_mog2_top_FINAL as top_cam
import webcam_cv_mog2_side_FINAL as side_cam


def parse_weight_from_clipboard():
    raw = pyperclip.paste()
    try:
        cleaned = re.sub(r'[^0-9.]+', '', raw)
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def load_config(path="params.yaml"):
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    return config


def build_output_string(shared_dims, shared_h):
    L = shared_dims["L"]
    W = shared_dims["W"]
    H = shared_h["value"]
    return f"{L:.2f};{W:.2f};{H:.2f}"


def reset_dimensions(shared_dims, shared_h):
    shared_dims["L"] = 0.0
    shared_dims["W"] = 0.0
    shared_dims["L_ready"] = False
    shared_dims["W_ready"] = False
    shared_h["value"] = 0.0
    shared_h["ready"] = False

    top_cam._l_avg.window.clear()
    top_cam._w_avg.window.clear()
    side_cam._h_avg.window.clear()


def dashboard_input_listener(shared_dims, shared_h, stop_event, hotkey):
    while not stop_event.is_set():
        if keyboard.is_pressed(hotkey):
            if shared_dims.get("L_ready") and shared_dims.get("W_ready") and shared_h.get("ready"):
                L = f"{shared_dims['L']:.2f}"
                W = f"{shared_dims['W']:.2f}"
                H = f"{shared_h['value']:.2f}"

                weight = parse_weight_from_clipboard()
                if weight is None:
                    print("Could not read a valid weight from clipboard — aborting paste.")
                    pyautogui.typewrite(L, interval=0.01)
                    pyautogui.press('tab', presses=2, interval=0.05)
                    pyautogui.typewrite(W, interval=0.01)
                    pyautogui.press('tab', presses=2, interval=0.05)
                    pyautogui.typewrite(H, interval=0.01)
                    reset_dimensions(shared_dims, shared_h)
                else:
                    Wt = f"{weight:.2f}"

                    pyautogui.typewrite(L, interval=0.01)
                    pyautogui.press('tab', presses=2, interval=0.05)
                    pyautogui.typewrite(W, interval=0.01)
                    pyautogui.press('tab', presses=2, interval=0.05)
                    pyautogui.typewrite(H, interval=0.01)
                    pyautogui.press('tab', presses=2, interval=0.05)
                    pyautogui.typewrite(Wt, interval=0.01)

                    print(f"Entered into dashboard: L={L} W={W} H={H} Weight={Wt}")
                    reset_dimensions(shared_dims, shared_h)
            else:
                print(f"{hotkey.upper()} pressed but values not yet stable — ignored.")

            while keyboard.is_pressed(hotkey):
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


# NEW: force-kills the entire process immediately, bypassing graceful
# thread shutdown (which is what hangs due to cv2's cross-thread GUI issue).
def kill_switch_listener(kill_hotkey, stop_event):
    while not stop_event.is_set():
        if keyboard.is_pressed(kill_hotkey):
            print(f"{kill_hotkey.upper()} pressed — force closing everything.")
            os._exit(0)
        time.sleep(0.05)


if __name__ == "__main__":
    config = load_config()
    dashboard_key = config["dashboard_hotkey"]
    kill_key = config["kill_hotkey"]   # NEW

    shared_h    = {"value": 0.0, "ready": False, "offset": 0.0} #added offset
    shared_dims = {"L": 0.0, "W": 0.0,
                   "L_ready": False, "W_ready": False}

    stop_event = threading.Event()

    t_side      = threading.Thread(target=side_cam.main, args=(shared_h,))
    t_top       = threading.Thread(target=top_cam.main,  args=(shared_h, shared_dims))
    t_monitor   = threading.Thread(target=monitor_output, args=(shared_dims, shared_h, stop_event), daemon=True)
    t_dashboard = threading.Thread(target=dashboard_input_listener, args=(shared_dims, shared_h, stop_event, dashboard_key), daemon=True)
    t_kill      = threading.Thread(target=kill_switch_listener, args=(kill_key, stop_event), daemon=True)

    t_side.start()
    t_top.start()
    t_monitor.start()
    t_dashboard.start()
    t_kill.start()   # NEW

    print(f"System running. Press {dashboard_key.upper()} to paste measurements, "
          f"{kill_key.upper()} to force-quit everything.")   # NEW: helpful startup message

    t_side.join()
    t_top.join()

    stop_event.set()
    t_monitor.join()
    t_dashboard.join()

def reset_dimensions(shared_dims, shared_h):
    shared_dims["L"] = 0.0
    shared_dims["W"] = 0.0
    shared_dims["L_ready"] = False
    shared_dims["W_ready"] = False
    shared_h["value"] = 0.0
    shared_h["ready"] = False
    shared_h["offset"] = 0.0   # NEW

    top_cam._l_avg.window.clear()
    top_cam._w_avg.window.clear()
    side_cam._h_avg.window.clear()