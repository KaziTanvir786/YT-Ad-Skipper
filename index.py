import tkinter as tk
import threading
import pyautogui
import pytesseract
import numpy as np
import cv2
import re
import time
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────
#  CONFIGURATION & UTILS
# ─────────────────────────────────────────────
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

SCAN_INTERVAL        = 0.1
CONFIDENCE_MIN       = 30
DELAY_BETWEEN_CLICKS = 0.3
CLICK_COOLDOWN       = 1.0   # Wait 1s after any click before next click

SEARCH_ZONE_LEFT   = 0.50
SEARCH_ZONE_TOP    = 0.50
SEARCH_ZONE_RIGHT  = 1.00
SEARCH_ZONE_BOTTOM = 1.00

VALID_SKIP_WORDS = ["skip", "skip ad", "skip ads", "skip in"]

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ─────────────────────────────────────────────
#  CORE LOGIC
# ─────────────────────────────────────────────
def get_zone_coords():
    sw, sh = pyautogui.size()
    left   = int(sw * SEARCH_ZONE_LEFT)
    top    = int(sh * SEARCH_ZONE_TOP)
    width  = int(sw * (SEARCH_ZONE_RIGHT  - SEARCH_ZONE_LEFT))
    height = int(sh * (SEARCH_ZONE_BOTTOM - SEARCH_ZONE_TOP))
    return left, top, width, height

def capture_zone():
    left, top, width, height = get_zone_coords()
    screenshot = pyautogui.screenshot(region=(left, top, width, height))
    return screenshot, left, top

def preprocess(pil_image):
    img     = np.array(pil_image)
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    gray    = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    scaled  = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
    return [
        ("upscaled",   scaled),
        ("inverted",   cv2.bitwise_not(scaled)),
        ("thresh",     cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
        ("thresh_inv", cv2.threshold(cv2.bitwise_not(scaled), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
        ("sharpened",  cv2.filter2D(scaled, -1, np.array([[0,-1,0],[-1,5,-1],[0,-1,0]]))),
    ]

def is_valid_skip(text):
    cleaned = text.strip().lower()
    if not cleaned.startswith("skip"):
        return False
    for v in VALID_SKIP_WORDS:
        if cleaned == v:
            return True
    if re.match(r"^skip\s*(ad|ads)?(\s+in)?\s*\d*$", cleaned):
        return True
    if cleaned.startswith("skip ad"):
        return True
    return False

def _add_unique(matches, cx, cy, text, conf, threshold=40):
    for (ex, ey, _, _) in matches:
        if abs(cx - ex) < threshold and abs(cy - ey) < threshold:
            return
    matches.append((cx, cy, text, conf))

def _extract_matches(words, ox, oy):
    matches = []
    for i, w in enumerate(words):
        if is_valid_skip(w['text']):
            cx = ox + w['left'] + w['w'] // 2
            cy = oy + w['top']  + w['h'] // 2
            _add_unique(matches, cx, cy, w['text'], w['conf'])
            continue
        if i + 1 < len(words):
            two = w['text'] + " " + words[i+1]['text']
            if is_valid_skip(two):
                l = min(w['left'], words[i+1]['left'])
                r = max(w['left']+w['w'], words[i+1]['left']+words[i+1]['w'])
                t = min(w['top'],  words[i+1]['top'])
                b = max(w['top']+w['h'], words[i+1]['top']+words[i+1]['h'])
                _add_unique(matches, ox+(l+r)//2, oy+(t+b)//2, two,
                            (w['conf']+words[i+1]['conf'])//2)
        if i + 2 < len(words):
            three = w['text']+" "+words[i+1]['text']+" "+words[i+2]['text']
            if is_valid_skip(three):
                l = min(w['left'], words[i+2]['left'])
                r = max(w['left']+w['w'], words[i+2]['left']+words[i+2]['w'])
                t = min(w['top'], words[i+2]['top'])
                b = max(w['top']+w['h'], words[i+2]['top']+words[i+2]['h'])
                _add_unique(matches, ox+(l+r)//2, oy+(t+b)//2, three,
                            (w['conf']+words[i+1]['conf']+words[i+2]['conf'])//3)
    return matches

def ocr_single_version(args):
    name, cv_img, ox, oy = args
    sf = 2.5
    try:
        data = pytesseract.image_to_data(
            cv_img, config=r"--oem 3 --psm 11",
            output_type=pytesseract.Output.DICT
        )
        words = []
        for i in range(len(data['text'])):
            word = data['text'][i].strip()
            conf = int(data['conf'][i])
            if word == "" or conf < CONFIDENCE_MIN:
                continue
            words.append({
                "text": word, "conf": conf,
                "left": int(data['left'][i]/sf),  "top": int(data['top'][i]/sf),
                "w":    int(data['width'][i]/sf),  "h":   int(data['height'][i]/sf),
            })
        return _extract_matches(words, ox, oy)
    except Exception:
        return []

def find_skip_buttons(pil_image, ox, oy):
    versions    = preprocess(pil_image)
    all_matches = []
    tasks = [(name, cv_img, ox, oy) for name, cv_img in versions]
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(ocr_single_version, t): t[0] for t in tasks}
        for future in as_completed(futures):
            result = future.result()
            if result:
                for m in result:
                    _add_unique(all_matches, m[0], m[1], m[2], m[3])
                for f in futures:
                    f.cancel()
                break
    return all_matches

def get_screen_center():
    sw, sh = pyautogui.size()
    return sw // 2, sh // 2

def do_click(x, y):
    """Click the target, then immediately move mouse to screen center."""
    pyautogui.moveTo(x, y, duration=0.05)
    pyautogui.click()
    # Move to center right after clicking so mouse doesn't block video
    cx, cy = get_screen_center()
    pyautogui.moveTo(cx, cy, duration=0.1)

# ─────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────
class AdSkipperApp:
    BG         = "#0f0f0f"
    CARD       = "#1a1a1a"
    BORDER     = "#2a2a2a"
    RED        = "#ff0000"
    RED_DIM    = "#cc0000"
    WHITE      = "#ffffff"
    GRAY       = "#888888"
    GRAY_LIGHT = "#bbbbbb"
    GREEN      = "#00c853"

    def __init__(self, root):
        self.root            = root
        self.running         = False
        self.skip_count      = 0
        self.scan_count      = 0
        self.stop_event      = threading.Event()
        self.worker          = None
        self._last_click_at  = 0.0   # Timestamp of last click for cooldown

        self._build_window()
        self._build_ui()

    def _build_window(self):
        self.root.title("YT Ad Skipper")
        self.root.geometry("380x520")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)
        try:
            self.root.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth()  - 380) // 2
        y = (self.root.winfo_screenheight() - 520) // 2
        self.root.geometry(f"380x520+{x}+{y}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # ── Header ──
        top = tk.Frame(self.root, bg=self.BG)
        top.pack(fill="x", padx=24, pady=(28, 0))
        logo = tk.Canvas(top, width=36, height=26, bg=self.BG, highlightthickness=0)
        logo.pack(side="left")
        logo.create_rectangle(0, 0, 36, 26, fill=self.RED, outline="")
        logo.create_polygon(14, 7, 14, 19, 26, 13, fill=self.WHITE, outline="")
        tf = tk.Frame(top, bg=self.BG)
        tf.pack(side="left", padx=(10, 0))
        tk.Label(tf, text="Ad Skipper", font=("Helvetica Neue", 17, "bold"),
                 fg=self.WHITE, bg=self.BG).pack(anchor="w")
        tk.Label(tf, text="YouTube · Automatic", font=("Helvetica Neue", 9),
                 fg=self.GRAY, bg=self.BG).pack(anchor="w")
        badge = tk.Label(top, text="⚡ Fast Mode", font=("Helvetica Neue", 9, "bold"),
                         fg="#ffcc00", bg="#2a2000", padx=8, pady=3)
        badge.pack(side="right")

        tk.Frame(self.root, bg=self.BORDER, height=1).pack(fill="x", padx=24, pady=(20, 0))

        # ── Toggle card ──
        card = tk.Frame(self.root, bg=self.CARD,
                        highlightbackground=self.BORDER, highlightthickness=1)
        card.pack(fill="x", padx=24, pady=20)
        row = tk.Frame(card, bg=self.CARD)
        row.pack(fill="x", padx=18, pady=18)
        lc = tk.Frame(row, bg=self.CARD)
        lc.pack(side="left")
        tk.Label(lc, text="Auto Skip Ads", font=("Helvetica Neue", 13, "bold"),
                 fg=self.WHITE, bg=self.CARD).pack(anchor="w")
        self.status_label = tk.Label(lc, text="● Inactive",
                                     font=("Helvetica Neue", 10),
                                     fg=self.GRAY, bg=self.CARD)
        self.status_label.pack(anchor="w", pady=(3, 0))
        self.toggle_canvas = tk.Canvas(row, width=52, height=28,
                                       bg=self.CARD, highlightthickness=0,
                                       cursor="hand2")
        self.toggle_canvas.pack(side="right")
        self._draw_toggle(False)
        self.toggle_canvas.bind("<Button-1>", lambda e: self._toggle())

        # ── Stats ──
        stats = tk.Frame(self.root, bg=self.BG)
        stats.pack(fill="x", padx=24)
        self._stat_box(stats, "ADS SKIPPED", "skip_val", "0")
        tk.Frame(stats, bg=self.BORDER, width=1).pack(side="left", fill="y", pady=4)
        self._stat_box(stats, "SCANS DONE",  "scan_val", "0")

        tk.Frame(self.root, bg=self.BORDER, height=1).pack(fill="x", padx=24, pady=(20, 0))

        # ── Log ──
        lh = tk.Frame(self.root, bg=self.BG)
        lh.pack(fill="x", padx=24, pady=(14, 6))
        tk.Label(lh, text="ACTIVITY LOG", font=("Helvetica Neue", 9, "bold"),
                 fg=self.GRAY, bg=self.BG).pack(side="left")
        cb = tk.Label(lh, text="Clear", font=("Helvetica Neue", 9),
                      fg=self.RED_DIM, bg=self.BG, cursor="hand2")
        cb.pack(side="right")
        cb.bind("<Button-1>", lambda e: self._clear_log())

        lf = tk.Frame(self.root, bg=self.CARD,
                      highlightbackground=self.BORDER, highlightthickness=1)
        lf.pack(fill="both", expand=True, padx=24, pady=(0, 24))
        self.log_text = tk.Text(
            lf, bg=self.CARD, fg=self.GRAY_LIGHT,
            font=("Courier New", 9), relief="flat", bd=0,
            padx=12, pady=10, state="disabled", wrap="word",
            selectbackground=self.RED_DIM,
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_config("green",  foreground=self.GREEN)
        self.log_text.tag_config("red",    foreground=self.RED)
        self.log_text.tag_config("gray",   foreground=self.GRAY)
        self.log_text.tag_config("yellow", foreground="#ffcc00")
        self.log_text.tag_config("white",  foreground=self.WHITE)
        self.log_text.tag_config("ts",     foreground="#444444")

        self._log("Ready. Toggle the switch to start.", "gray")

    def _stat_box(self, parent, label, attr, initial):
        box = tk.Frame(parent, bg=self.CARD,
                       highlightbackground=self.BORDER, highlightthickness=1)
        box.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(box, bg=self.CARD)
        inner.pack(padx=16, pady=12)
        val = tk.Label(inner, text=initial,
                       font=("Helvetica Neue", 28, "bold"),
                       fg=self.WHITE, bg=self.CARD)
        val.pack()
        tk.Label(inner, text=label, font=("Helvetica Neue", 8),
                 fg=self.GRAY, bg=self.CARD).pack()
        setattr(self, attr, val)

    def _draw_toggle(self, on):
        c = self.toggle_canvas
        c.delete("all")
        color   = self.RED if on else self.BORDER
        thumb_x = 38       if on else 14
        c.create_rectangle(0, 4, 52, 24, fill=color, outline="")
        c.create_oval(0,  4, 16, 24, fill=color, outline="")
        c.create_oval(36, 4, 52, 24, fill=color, outline="")
        c.create_oval(thumb_x-12, 2, thumb_x+12, 26, fill=self.WHITE, outline="")

    def _toggle(self):
        if self.running: self._stop()
        else:            self._start()

    def _start(self):
        self.running        = True
        self._last_click_at = 0.0
        self.stop_event.clear()
        self._draw_toggle(True)
        self.status_label.config(text="● Active", fg=self.GREEN)
        self._log("Skipper started — fast mode active.", "green")
        self.worker = threading.Thread(target=self._scan_loop, daemon=True)
        self.worker.start()

    def _stop(self):
        self.running = False
        self.stop_event.set()
        self._draw_toggle(False)
        self.status_label.config(text="● Inactive", fg=self.GRAY)
        self._log("Skipper stopped.", "gray")

    # ── Scan loop ─────────────────────────────
    def _scan_loop(self):
        while not self.stop_event.is_set():
            try:
                t_start = time.time()

                # ── Cooldown check: skip scan if within 1s of last click ──
                since_last_click = t_start - self._last_click_at
                if since_last_click < CLICK_COOLDOWN:
                    remaining = CLICK_COOLDOWN - since_last_click
                    self.stop_event.wait(remaining)
                    continue

                zone_img, zx, zy = capture_zone()
                matches = find_skip_buttons(zone_img, zx, zy)
                self.scan_count += 1
                self.root.after(0, self._update_scan_count)

                if matches:
                    elapsed = round((time.time() - t_start) * 1000)

                    for i, (x, y, text, conf) in enumerate(matches):
                        if self.stop_event.is_set():
                            break

                        # Click the skip button
                        do_click(x, y)
                        self._last_click_at = time.time()   # Record click time
                        self.skip_count += 1

                        msg = f'Skipped "{text}" (conf:{conf}%) [{elapsed}ms]'
                        self.root.after(0, lambda m=msg: (
                            self._log(m, "green"),
                            self._update_skip_count()
                        ))

                        # If multiple matches, wait between each click
                        if i < len(matches) - 1:
                            time.sleep(DELAY_BETWEEN_CLICKS)
                            self._last_click_at = time.time()

                    # After all clicks done, wait out the remaining cooldown
                    # before resuming scans so we don't re-click same ad
                    elapsed_since_click = time.time() - self._last_click_at
                    if elapsed_since_click < CLICK_COOLDOWN:
                        self.stop_event.wait(CLICK_COOLDOWN - elapsed_since_click)

                else:
                    self.stop_event.wait(SCAN_INTERVAL)

            except Exception as e:
                self.root.after(0, lambda err=str(e):
                    self._log(f"Error: {err}", "red"))
                self.stop_event.wait(1)

    def _update_skip_count(self):
        self.skip_val.config(text=str(self.skip_count))

    def _update_scan_count(self):
        self.scan_val.config(text=str(self.scan_count))

    def _log(self, message, tag="white"):
        ts = time.strftime("%H:%M:%S")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"[{ts}] ", "ts")
        self.log_text.insert("end", message + "\n", tag)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _on_close(self):
        self.stop_event.set()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app  = AdSkipperApp(root)
    root.mainloop()