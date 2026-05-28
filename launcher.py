# launcher.py
import threading
import webcam_cv_mog2 as top_cam
import webcam_cv_mog2_side_framediff as side_cam

if __name__ == "__main__":
    shared_h = {"value": 0.0}                  # plain dict, not multiprocessing.Value

    t_side = threading.Thread(target=side_cam.main, args=(shared_h,))
    t_top  = threading.Thread(target=top_cam.main,  args=(shared_h,))

    t_side.start()
    t_top.start()

    t_side.join()
    t_top.join() 