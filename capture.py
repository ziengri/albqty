"""
Albion Online Fishing QTE - Screen Capture Engine
High-FPS screen grabber using MSS with automatic desktop station attachment.
"""

import ctypes
import mss
import numpy as np


class ScreenGrabber:
    def __init__(self, roi_width=800, roi_height=600):
        self._ensure_desktop_access()
        self.sct = mss.MSS()
        self.monitor = self.sct.monitors[1]
        self.screen_width = self.monitor["width"]
        self.screen_height = self.monitor["height"]
        self.roi_width = min(roi_width, self.screen_width)
        self.roi_height = min(roi_height, self.screen_height)
        self.roi = self._calc_roi()

    def _ensure_desktop_access(self):
        """Attaches thread to input desktop if needed on Windows."""
        try:
            user32 = ctypes.windll.user32
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass

    def _calc_roi(self):
        """Calculates centered Region of Interest."""
        left = max(0, (self.screen_width - self.roi_width) // 2)
        top = max(0, (self.screen_height - self.roi_height) // 2)
        return {
            "left": left,
            "top": top,
            "width": self.roi_width,
            "height": self.roi_height
        }

    def set_roi_size(self, width, height):
        self.roi_width = min(width, self.screen_width)
        self.roi_height = min(height, self.screen_height)
        self.roi = self._calc_roi()

    def grab_roi(self):
        """
        Grabs central screen ROI as BGR numpy array.
        Returns:
            np.ndarray (H, W, 3) in BGR format
        """
        raw = self.sct.grab(self.roi)
        img = np.array(raw)
        # Convert BGRA to BGR
        return img[:, :, :3]

    def grab_full(self):
        """Grabs entire primary monitor."""
        raw = self.sct.grab(self.monitor)
        img = np.array(raw)
        return img[:, :, :3]

    def close(self):
        try:
            self.sct.close()
        except Exception:
            pass
