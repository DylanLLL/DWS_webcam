# launcher.py
import multiprocessing
import webcam_cv_mog2 as top_cam
import webcam_cv_mog2_side as side_cam

if __name__ == "__main__":
    # Shared float: side camera writes H here, top camera reads it
    shared_h = multiprocessing.Value('d', 0.0)

    p_side = multiprocessing.Process(target=side_cam.main, args=(shared_h,))
    p_top  = multiprocessing.Process(target=top_cam.main,  args=(shared_h,))

    p_side.start()
    p_top.start()

    p_side.join()
    p_top.join()