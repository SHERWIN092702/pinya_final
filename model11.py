import argparse
import lap
import cv2 as cv
import numpy as np
from mss import mss
from ultralytics import YOLO
import skfuzzy as fuzz
import skfuzzy.control as ctrl
import time, json, sys, torch
from pathlib import Path
from pywinauto import Desktop
import ctypes

ctypes.windll.user32.SetProcessDPIAware()

# -------------------- 1. Setup Arguments -----------------------
parser = argparse.ArgumentParser()
parser.add_argument("--source", choices=["scrcpy", "RTMP"], required=True)
parser.add_argument("--model", default=r"C:\Users\Acer\Desktop\Thesis\yolo_model\yolo_v8\best.pt")
parser.add_argument("--counts", default=r"C:\Users\Acer\Desktop\Thesis\detectioncount\detection_counts.json")
args = parser.parse_args()

# -------------------- 2. Capture Setup -----------------------
if args.source == "scrcpy":

    def auto_detect_scrcpy():
        windows = Desktop(backend="uia").windows()
        for win in windows:
            try:
                class_name = (win.element_info.class_name or "").lower()
                if class_name == "sdl_app":
                    rect = win.rectangle()
                    if rect.width() > 200 and rect.height() > 200:
                        return {
                            "left": int(rect.left),
                            "top": int(rect.top),
                            "width": int(rect.width()),
                            "height": int(rect.height())
                        }
            except:
                continue
        return None

    bounding_box = None
    while bounding_box is None:
        bounding_box = auto_detect_scrcpy()
        time.sleep(0.5)

    sct = mss()
    last_bbox_update = time.time()
    BBOX_REFRESH_SEC = 2.0

elif args.source == "RTMP":
    rtmp_url = "rtmp://localhost/live/test"
    cap = cv.VideoCapture(rtmp_url, cv.CAP_FFMPEG)
    cap.set(cv.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv.CAP_PROP_FPS, 10)
    if not cap.isOpened():
        sys.exit(1)

# -------------------- 3. Load YOLO -----------------------
device = "cuda" if torch.cuda.is_available() else "cpu"
model = YOLO(args.model)
model.to(device)

# -------------------- 4. Window ------------------------
cv.namedWindow("Pineapple Detection", cv.WINDOW_NORMAL)
cv.resizeWindow("Pineapple Detection", 960, 540)

# -------------------- 5. Counters --------------------
counts_file = Path(args.counts)
counts_file.parent.mkdir(parents=True, exist_ok=True)

counts = {"ripe": 0, "unripe": 0, "overripe": 0}
counts_file.write_text(json.dumps(counts))

already_counted_ids = set()

# -------------------- 6. FUZZY LOGIC --------------------
# Tuned exclusively on Tagaytay pineapple data.
#
# Observed ranges:
#   Overripe: Y=0.021-0.062, B=0.132-0.174
#   Ripe:     Y=0.010-0.104, B=0.009-0.203
#   Unripe:   Y=0.052-0.065, B=0.173-0.185
#
# Key separable patterns:
#   - LOW B (< 0.115) + any Y  → almost always RIPE  (IDs 85, 86, 102)
#   - MEDIUM B (0.130-0.174) + LOW Y (< 0.065) → OVERRIPE core
#   - HIGH B (> 0.170) + LOW Y (0.052-0.065)   → UNRIPE or RIPE (overlap)
#   - HIGH Y (> 0.070) + LOW B                 → RIPE
#
# Limitation: Tagaytay unripe (B=0.173-0.185, Y=0.052-0.065) and
# ripe high-B cases (B=0.167-0.203, Y=0.027-0.060) are nearly
# identical in color — some misclassification between these is
# unavoidable with color-only features.

yellow = ctrl.Antecedent(np.arange(0, 1.01, 0.01), 'yellow')
green  = ctrl.Antecedent(np.arange(0, 1.01, 0.01), 'green')
brown  = ctrl.Antecedent(np.arange(0, 1.01, 0.01), 'brown')
ripeness = ctrl.Consequent(np.arange(0, 2.01, 0.01), 'ripeness')

# --- Yellow membership ---
# low:    All Tagaytay stages (Y = 0.010-0.065)
# medium: Tagaytay ripe high-Y cases (Y = 0.060-0.110)
# high:   Strong yellow signal (Y > 0.100)
yellow['low']    = fuzz.trapmf(yellow.universe, [0,    0,    0.05, 0.07])
yellow['medium'] = fuzz.trimf(yellow.universe,  [0.06, 0.09, 0.13])
yellow['high']   = fuzz.trapmf(yellow.universe, [0.10, 0.14, 1.0,  1.0 ])

# --- Green membership ---
# Almost always 0.000 in Tagaytay; kept as safety net only.
green['low']    = fuzz.trapmf(green.universe, [0,    0,    0.05, 0.15])
green['medium'] = fuzz.trimf(green.universe,  [0.10, 0.25, 0.45])
green['high']   = fuzz.trapmf(green.universe, [0.35, 0.55, 1.0,  1.0 ])

# --- Brown membership ---
# low:    Ripe low-B zone        (B = 0.000-0.115)  → IDs 85, 86, 102
# medium: Overripe core zone     (B = 0.125-0.175)  → overripe cluster
# high:   Ripe/Unripe high-B     (B > 0.170)        → overlap zone
brown['low']    = fuzz.trapmf(brown.universe, [0,    0,    0.09, 0.12])
brown['medium'] = fuzz.trimf(brown.universe,  [0.11, 0.14, 0.17])
brown['high']   = fuzz.trapmf(brown.universe, [0.16, 0.19, 1.0,  1.0 ])

# --- Ripeness output ---
# 0.00 - 0.75  → Unripe
# 0.75 - 1.35  → Ripe
# 1.35 - 2.00  → Overripe
ripeness['unripe']   = fuzz.trimf(ripeness.universe, [0,   0,   0.9])
ripeness['ripe']     = fuzz.trimf(ripeness.universe, [0.6, 1.0, 1.4])
ripeness['overripe'] = fuzz.trimf(ripeness.universe, [1.1, 2.0, 2.0])

# --- Fuzzy Rules ---
# Based strictly on Tagaytay observed patterns.
rules = [
    # UNRIPE
    # Tagaytay unripe: low Y, high B (> 0.170) — distinguished from
    # overripe by higher B and from ripe by absence of medium/high Y
    ctrl.Rule(yellow['low']    & brown['high'],                  ripeness['unripe']),

    # Green dominant safety net
    ctrl.Rule(green['high'],                                     ripeness['unripe']),

    # RIPE
    # Low B ripe: cleanly separable (IDs 85, 86, 102)
    ctrl.Rule(brown['low']     & green['low'],                   ripeness['ripe']),

    # Medium-high Y ripe (ID 85: Y=0.104, ID 102: Y=0.074)
    ctrl.Rule(yellow['high']   & brown['low'],                   ripeness['ripe']),
    ctrl.Rule(yellow['medium'] & brown['low'],                   ripeness['ripe']),
    ctrl.Rule(yellow['high']   & brown['medium'],                ripeness['ripe']),

    # OVERRIPE
    # Overripe core: low Y + medium B (B=0.132-0.174, Y=0.021-0.062)
    ctrl.Rule(yellow['low']    & brown['medium'],                ripeness['overripe']),

    # Catch-all fallback → unripe if no signal
    ctrl.Rule(yellow['low']    & brown['low']   & green['low'],  ripeness['unripe']),
]

ripeness_ctrl = ctrl.ControlSystem(rules)

# -------------------- 7. MAIN LOOP --------------------
while True:

    if args.source == "scrcpy":

        if time.time() - last_bbox_update > BBOX_REFRESH_SEC:
            bb = auto_detect_scrcpy()
            if bb:
                bounding_box = bb
                last_bbox_update = time.time()

        scr_img = np.array(sct.grab(bounding_box))[:, :, :3]

    else:
        cap.grab()
        ret, scr_img = cap.retrieve()
        if not ret:
            continue

    resized = cv.resize(scr_img, (960, 540))

    # CLAHE lighting normalization
    lab = cv.cvtColor(resized, cv.COLOR_BGR2LAB)
    l, a, b = cv.split(lab)
    clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    l = clahe.apply(l)
    lab = cv.merge((l, a, b))
    preprocessed = cv.cvtColor(lab, cv.COLOR_LAB2BGR)

    results = model.track(preprocessed, persist=True, verbose=False)
    annotated = resized.copy()

    if not results or results[0].boxes is None:
        cv.imshow("Pineapple Detection", annotated)
        if cv.waitKey(1) & 0xFF == ord('q'):
            break
        continue

    for box in results[0].boxes:

        if box.id is None:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])
        crop = preprocessed[y1:y2, x1:x2]

        if crop.size == 0:
            continue

        track_id = int(box.id[0])

        if track_id in already_counted_ids:
            continue

        crop_small = cv.resize(crop, (64, 64))
        hsv = cv.cvtColor(crop_small, cv.COLOR_BGR2HSV)

        h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        total_pixels = h.size

        # Brown mask widened (hue 5-25) to better capture
        # Tagaytay's darker brown-orange tones.
        yellow_mask = (20 <= h) & (h <= 38) & (s >= 50) & (v >= 70)
        green_mask  = (45 <= h) & (h <= 70) & (s >= 80) & (v >= 70)
        brown_mask  = (5  <= h) & (h <= 25) & (s >= 40) & (v <= 130)

        yellow_pct_val = np.sum(yellow_mask) / total_pixels
        green_pct_val  = np.sum(green_mask)  / total_pixels
        brown_pct_val  = np.sum(brown_mask)  / total_pixels

        # ---------------- DECISION ----------------
        # Hard overrides only for clearly separable cases.
        # Fuzzy handles the ambiguous middle ground.

        # ID 85 pattern: high Y + very low B → clearly ripe
        if yellow_pct_val > 0.09 and brown_pct_val < 0.05:
            label = "Ripe"
            counts["ripe"] += 1

        # Fuzzy logic handles everything else
        else:
            try:
                sim = ctrl.ControlSystemSimulation(ripeness_ctrl)
                sim.input['yellow'] = yellow_pct_val
                sim.input['green']  = green_pct_val
                sim.input['brown']  = brown_pct_val
                sim.compute()
                level = sim.output['ripeness']
            except KeyError:
                level = 0.0

            if level < 0.75:
                label = "Unripe"
                counts["unripe"] += 1
            elif level < 1.35:
                label = "Ripe"
                counts["ripe"] += 1
            else:
                label = "Overripe"
                counts["overripe"] += 1

        already_counted_ids.add(track_id)

        cv.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

        text = f"{label} | Y:{yellow_pct_val:.2f} G:{green_pct_val:.2f} B:{brown_pct_val:.2f}"

        cv.putText(
            annotated,
            text,
            (x1, y1 - 10),
            cv.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            2
        )

        print(
            f"ID {track_id}: "
            f"Y={yellow_pct_val:.3f}, "
            f"G={green_pct_val:.3f}, "
            f"B={brown_pct_val:.3f}, "
            f"Label={label}"
        )

    counts_file.write_text(json.dumps(counts))
    cv.imshow("Pineapple Detection", annotated)

    if cv.waitKey(1) & 0xFF == ord('q'):
        break

cv.destroyAllWindows()

if args.source == "RTMP":
    cap.release()