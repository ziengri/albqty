"""
Albion Online Fishing QTE Engine
High-performance computer vision detector for fishing minigame bar and bobber.
"""

import cv2
import numpy as np


class FishingDetector:
    def __init__(self, templ_path=None):
        self.templ = None
        if templ_path:
            self.templ = cv2.imread(templ_path)

    def detect(self, img_bgr):
        """
        Analyzes image/ROI for Albion fishing minigame.
        Returns:
            dict with:
                active: bool
                bar_rect: (x, y, w, h)
                bobber_x: float (relative to bar x)
                bobber_pct: float (0.0 to 100.0)
                method: str
            or None if minigame not found.
        """
        if img_bgr is None or img_bgr.size == 0:
            return None

        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

        # 1. Detect blue progress bar (the anchor of the minigame)
        # Blue bar HSV range in Albion: H in [95, 120], S in [110, 240], V in [90, 210]
        blue_mask = cv2.inRange(hsv, (95, 110, 90), (120, 240, 210))
        blue_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 3))
        blue_closed = cv2.morphologyEx(blue_mask, cv2.MORPH_CLOSE, blue_kernel)
        contours, _ = cv2.findContours(blue_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        minigame_anchor = None
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            aspect = w / max(h, 1)
            # Albion blue bar has high aspect ratio (> 4.5) and significant width (> 60px)
            if w >= 60 and aspect >= 4.0:
                minigame_anchor = (x, y, w, h)
                break

        if not minigame_anchor:
            # Fallback: check if green bar alone is visible
            green_mask = cv2.inRange(hsv, (38, 90, 50), (65, 255, 160))
            g_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 4))
            g_closed = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, g_kernel)
            g_contours, _ = cv2.findContours(g_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in g_contours:
                x, y, w, h = cv2.boundingRect(c)
                aspect = w / max(h, 1)
                if w >= 60 and aspect >= 3.0:
                    minigame_anchor = (x, y + int(h * 1.1), w, int(h * 0.75))
                    break

        if not minigame_anchor:
            return None

        bx, by, bw, bh = minigame_anchor

        # 2. Extract top tension bar slice
        top_y = max(0, by - int(bh * 1.55))
        top_h = int(bh * 1.45)
        if top_y + top_h > img_bgr.shape[0] or bx + bw > img_bgr.shape[1]:
            return None

        top_bar = img_bgr[top_y:top_y + top_h, bx:bx + bw]
        if top_bar.size == 0 or top_bar.shape[0] < 5 or top_bar.shape[1] < 30:
            return None

        # Verify green presence in top bar to avoid false positives
        tb_hsv = cv2.cvtColor(top_bar, cv2.COLOR_BGR2HSV)
        green_pixels = cv2.inRange(tb_hsv, (38, 70, 40), (65, 255, 180))
        if cv2.countNonZero(green_pixels) < 100:
            return None

        # 3. Locate Bobber inside/above the bar
        # Method A: White bulb of bobber
        white_mask = (tb_hsv[:, :, 1] < 80) & (tb_hsv[:, :, 2] > 175)
        ys, xs = np.where(white_mask)
        bobber_x = None
        method = "none"

        if len(xs) >= 6:
            bobber_x = float(np.mean(xs))
            method = "white_bulb"
        else:
            # Method B: Orange feathers above top bar
            feather_top = max(0, top_y - int(bh * 1.6))
            feather_h = top_y - feather_top
            if feather_h > 5:
                above_bar = img_bgr[feather_top:top_y, bx:bx + bw]
                ab_hsv = cv2.cvtColor(above_bar, cv2.COLOR_BGR2HSV)
                feathers = (ab_hsv[:, :, 0] >= 10) & (ab_hsv[:, :, 0] <= 32) & \
                           (ab_hsv[:, :, 1] >= 110) & (ab_hsv[:, :, 2] >= 90)
                fys, fxs = np.where(feathers)
                if len(fxs) >= 15:
                    bobber_x = float(np.median(fxs))
                    method = "feathers"

        if bobber_x is None and self.templ is not None:
            # Method C: Template match
            res = cv2.matchTemplate(top_bar, self.templ, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val > 0.55:
                bobber_x = float(max_loc[0] + self.templ.shape[1] / 2)
                method = f"template_{max_val:.2f}"

        if bobber_x is None:
            # Fallback: estimate bobber from lack of green or center
            return {
                "active": True,
                "bar_rect": (bx, top_y, bw, top_h + bh),
                "bobber_x": None,
                "bobber_pct": None,
                "method": "bar_only"
            }

        bobber_pct = max(0.0, min(100.0, (bobber_x / max(1, bw)) * 100.0))

        return {
            "active": True,
            "bar_rect": (bx, top_y, bw, top_h + bh),
            "bobber_x": bobber_x,
            "bobber_pct": bobber_pct,
            "method": method
        }
