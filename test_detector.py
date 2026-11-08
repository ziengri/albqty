"""
Albion Online Fishing QTE - Standalone Test & Calibration Tool
Run this script to verify computer vision detection on a screenshot or live game window.
"""

import os
import sys
import cv2
from detector import FishingDetector
from capture import ScreenGrabber

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
TEMPLATE_PATH = os.path.join(ASSETS_DIR, "bobber_head.png")


def test_image(image_path):
    print(f"[*] Testing detection on image: {image_path}")
    if not os.path.exists(image_path):
        print(f"[-] File not found: {image_path}")
        return

    img = cv2.imread(image_path)
    if img is None:
        print(f"[-] Could not decode image: {image_path}")
        return

    templ = TEMPLATE_PATH if os.path.exists(TEMPLATE_PATH) else None
    detector = FishingDetector(templ_path=templ)
    res = detector.detect(img)

    if res and res.get("active"):
        print("[+] SUCCESS! Fishing minigame detected:")
        print(f"    - Bar coordinates (x, y, w, h): {res['bar_rect']}")
        print(f"    - Bobber position: {res['bobber_pct']:.1f}%")
        print(f"    - Detection method: {res['method']}")

        # Save annotated image
        dbg = img.copy()
        bx, by, bw, bh = res["bar_rect"]
        cv2.rectangle(dbg, (bx, by), (bx + bw, by + bh), (0, 255, 0), 2)
        if res.get("bobber_x") is not None:
            abs_bx = int(bx + res["bobber_x"])
            cv2.line(dbg, (abs_bx, by - 10), (abs_bx, by + bh + 10), (0, 0, 255), 2)
            cv2.circle(dbg, (abs_bx, by + bh // 2), 5, (0, 255, 255), -1)

        out_path = "debug_test_result.png"
        cv2.imwrite(out_path, dbg)
        print(f"[+] Annotated debug image saved to: {os.path.abspath(out_path)}")
    else:
        print("[-] Minigame NOT detected in the image.")


def test_live_screen():
    print("[*] Taking live screenshot of center ROI...")
    grabber = ScreenGrabber(roi_width=800, roi_height=600)
    frame = grabber.grab_roi()
    grabber.close()

    temp_path = "live_sample.png"
    cv2.imwrite(temp_path, frame)
    print(f"[+] Grabbed frame saved to {temp_path}. Testing detection...")
    test_image(temp_path)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_image(sys.argv[1])
    else:
        # Check if the user's uploaded sample is present
        user_sample = r"C:\Users\komputer1\.gemini\antigravity\brain\d26f962b-a1a9-44fa-976e-abe09deb3d90\.user_uploaded\media_1794145979910_0e8f7ca1.png"
        if os.path.exists(user_sample):
            test_image(user_sample)
        else:
            test_live_screen()
