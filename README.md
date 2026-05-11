# 📺 YouTube Ad Skipper

A lightweight desktop tool that **automatically detects and clicks the Skip Ad button** on YouTube — the moment it appears. Built with Python, it runs silently in the background while you watch, using OCR to scan the screen and click Skip without any browser extensions or API access required.

---

## ✨ Features

- 🔍 Continuously scans the screen for the Skip button
- ⚡ Parallel OCR across 5 image versions for fast detection
- 🖱️ Clicks instantly, then moves mouse back to screen center
- ⏱️ 1-second cooldown after each click to avoid double-clicks
- 🎛️ Clean GUI with live stats and activity log
- 🔁 Runs infinitely until you toggle it off

---

## 🖥️ Preview

![Screenshot](screenshot.png)

---

## 🧩 Dependencies

| Dependency        | Purpose                                 |
| ----------------- | --------------------------------------- |
| **Python 3.8+**   | Runtime                                 |
| **Tesseract OCR** | Text detection engine (external binary) |
| `pyautogui`       | Screen capture & mouse control          |
| `pytesseract`     | Python wrapper for Tesseract            |
| `opencv-python`   | Image preprocessing                     |
| `Pillow`          | Image handling                          |
| `numpy`           | Array operations for image data         |

---

## 📦 Installation

### Step 1 — Clone the repository

```bash
git clone https://github.com/your-username/yt-ad-skipper.git
cd yt-ad-skipper
```

### Step 2 — Install Tesseract OCR (required)

Tesseract is an external program that must be installed separately.

**Windows:**

1. Download the installer from the [UB Mannheim builds page](https://github.com/UB-Mannheim/tesseract/wiki)
2. Download `tesseract-ocr-w64-setup-5.x.x.exe`
3. Run the installer — keep all defaults
4. After install, confirm it works by opening a new terminal and running:

```bash
tesseract --version
```

You should see something like `tesseract 5.5.0`.

> If you get "not recognized", add Tesseract to your PATH manually:
> `Win + R` → `rundll32 sysdm.cpl,EditEnvironmentVariables` → System Variables → `Path` → New → paste `C:\Program Files\Tesseract-OCR`

**macOS:**

```bash
brew install tesseract
```

**Linux:**

```bash
sudo apt install tesseract-ocr
```

---

### Step 3 — Install Python dependencies

```bash
pip install pyautogui pytesseract opencv-python pillow numpy
```

---

### Step 4 — Configure Tesseract path (Windows only)

Open `ad_skipper.py` and confirm this line matches your Tesseract install location:

```python
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

If you installed Tesseract to a different folder, update this path accordingly. To find it, run:

```bash
where tesseract
```

---

## ▶️ Running the Program

```bash
python ad_skipper.py
```

The GUI window will open. Click the toggle switch to start — the skipper runs in the background from that point on.

**To stop:** click the toggle again, or close the window.

---

## ⚙️ Configuration

You can tweak these variables at the top of `ad_skipper.py`:

```python
SCAN_INTERVAL        = 0.1   # Seconds between scans (lower = faster)
CONFIDENCE_MIN       = 30    # OCR confidence threshold (0–100)
CLICK_COOLDOWN       = 1.0   # Seconds to wait after a click before next scan
DELAY_BETWEEN_CLICKS = 0.3   # Seconds between multiple simultaneous matches

# Screen zone to scan (bottom-right of screen where Skip button appears)
SEARCH_ZONE_LEFT   = 0.50
SEARCH_ZONE_TOP    = 0.50
SEARCH_ZONE_RIGHT  = 1.00
SEARCH_ZONE_BOTTOM = 1.00
```

---

## 🛡️ How It Works

1. Every `0.1s`, it captures the **bottom-right 50% of your screen** (where YouTube's Skip button always appears)
2. The captured image is preprocessed into **5 versions** (grayscale, inverted, thresholded, sharpened, etc.)
3. All 5 versions are scanned with Tesseract OCR **in parallel** using threads
4. If any version detects a valid Skip button word (`Skip`, `Skip Ad`, `Skip Ads`, `Skip in X`), it clicks immediately
5. After clicking, the mouse moves to the **center of the screen** so it doesn't hover over the video
6. A **1-second cooldown** prevents double-clicking the same button

---

## ❓ Troubleshooting

**Skip button not detected?**

- Lower `CONFIDENCE_MIN` from `30` to `20`
- Make sure your browser zoom is at 100%
- Widen the scan zone by lowering `SEARCH_ZONE_LEFT` and `SEARCH_ZONE_TOP`

**Clicking wrong buttons?**

- Raise `CONFIDENCE_MIN` to `50` or higher
- Narrow the scan zone by raising `SEARCH_ZONE_LEFT` / `SEARCH_ZONE_TOP`

**`TesseractNotFoundError`?**

- Tesseract is not installed or the path in `ad_skipper.py` is wrong
- Run `where tesseract` in your terminal and copy that path into the `tesseract_cmd` line

**Mouse goes to wrong position?**

- Make sure your display scaling is set to 100% in Windows display settings
- If you use multiple monitors, the Skip button must be on the primary display

---
