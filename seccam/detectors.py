"""Camera reader, motion detector, person detector (TFLite) and face ID (OpenCV YuNet + SFace)."""
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

try:
    from tflite_runtime.interpreter import Interpreter
except ImportError:  # PC fallback
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        import tensorflow as tf
        Interpreter = tf.lite.Interpreter


class Camera:
    """Reads frames on a background thread so processing always gets the newest one."""

    def __init__(self, index=0, width=640, height=480, fps=30):
        backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(index, backend)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        if not self.cap.isOpened():
            raise RuntimeError(f"camera {index} could not be opened (check /dev/video*)")
        self._frame, self._seq, self._last = None, 0, 0
        self._cond = threading.Condition()
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        fails = 0
        while self._running:
            ok, f = self.cap.read()
            if not ok:
                fails += 1
                if fails > 50:
                    print("[camera] read keeps failing", flush=True)
                    fails = 0
                time.sleep(0.02)
                continue
            fails = 0
            with self._cond:
                self._frame, self._seq = f, self._seq + 1
                self._cond.notify_all()

    def read(self, timeout=2.0):
        """Block until a frame newer than the last one returned is available."""
        with self._cond:
            if not self._cond.wait_for(lambda: self._seq != self._last, timeout):
                return None
            self._last = self._seq
            return self._frame.copy()

    def release(self):
        self._running = False
        self.cap.release()


class MotionDetector:
    def __init__(self, min_area_ratio=0.01):
        self.bg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25, detectShadows=False)
        self.min_ratio = min_area_ratio
        self.kernel = np.ones((3, 3), np.uint8)

    def __call__(self, frame):
        small = cv2.resize(frame, (160, 120))
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        mask = cv2.morphologyEx(self.bg.apply(gray), cv2.MORPH_OPEN, self.kernel)
        ratio = cv2.countNonZero(mask) / mask.size
        return ratio >= self.min_ratio, ratio


class PersonDetector:
    """TFLite detector with built-in NMS (TFLite_Detection_PostProcess), e.g. COCO SSD-MobileNet v1.
    Output class 0 = person."""

    PERSON = 0

    def __init__(self, model_path, score=0.5, threads=4):
        self.it = Interpreter(model_path=str(model_path), num_threads=threads)
        self.it.allocate_tensors()
        self.inp = self.it.get_input_details()[0]
        self.h, self.w = self.inp["shape"][1:3]
        self.outs = self.it.get_output_details()
        self.score = score

    def _outputs(self):
        boxes, vecs = None, []
        for o in self.outs:
            t = self.it.get_tensor(o["index"])[0]
            if t.ndim == 2 and t.shape[-1] == 4:
                boxes = t
            elif t.ndim == 1 and t.size > 1:
                vecs.append(t)
        # classes are whole numbers, scores are fractions; fall back to the standard order
        classes, scores = vecs[0], vecs[1]
        if np.all(np.mod(scores, 1) == 0) and not np.all(np.mod(classes, 1) == 0):
            classes, scores = scores, classes
        return boxes, classes, scores

    def __call__(self, frame):
        H, W = frame.shape[:2]
        img = cv2.cvtColor(cv2.resize(frame, (int(self.w), int(self.h))), cv2.COLOR_BGR2RGB)
        if self.inp["dtype"] == np.uint8:
            x = img[None]
        else:
            x = (img.astype(np.float32) / 127.5 - 1.0)[None]
        self.it.set_tensor(self.inp["index"], x)
        self.it.invoke()
        boxes, classes, scores = self._outputs()
        out = []
        for b, c, s in zip(boxes, classes, scores):
            if int(round(c)) == self.PERSON and s >= self.score:
                y1, x1, y2, x2 = np.clip(b, 0, 1)
                out.append((int(x1 * W), int(y1 * H), int(x2 * W), int(y2 * H), float(s)))
        return out


IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class FaceID:
    def __init__(self, det_path, rec_path, det_score=0.8, match_threshold=0.363, min_face_px=40):
        self.det = cv2.FaceDetectorYN.create(str(det_path), "", (320, 320), det_score, 0.3, 50)
        self.rec = cv2.FaceRecognizerSF.create(str(rec_path), "")
        self.thr = match_threshold
        self.min_px = min_face_px
        self.db = {}  # name -> (n, 128) normalized features

    def detect(self, img):
        h, w = img.shape[:2]
        self.det.setInputSize((w, h))
        _, faces = self.det.detect(img)
        return faces if faces is not None else np.empty((0, 15), np.float32)

    def embed(self, img, face):
        f = self.rec.feature(self.rec.alignCrop(img, face)).flatten()
        return f / (np.linalg.norm(f) + 1e-9)

    def enroll(self, known_dir):
        """known/<이름>/*.jpg -> feature DB. Returns {name: number_of_photos_used}."""
        self.db, report = {}, {}
        known_dir = Path(known_dir)
        if not known_dir.is_dir():
            return report
        for person in sorted(p for p in known_dir.iterdir() if p.is_dir()):
            feats = []
            for f in sorted(person.iterdir()):
                if f.suffix.lower() not in IMG_EXT:
                    continue
                img = cv2.imdecode(np.fromfile(str(f), np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    print(f"[enroll] cannot read {f}")
                    continue
                s = 1280 / max(img.shape[:2])
                if s < 1:
                    img = cv2.resize(img, None, fx=s, fy=s)
                faces = self.detect(img)
                if len(faces) == 0:
                    print(f"[enroll] no face found in {f.name} - skipped")
                    continue
                face = max(faces, key=lambda r: r[2] * r[3])  # largest face
                feats.append(self.embed(img, face))
            if feats:
                self.db[person.name] = np.stack(feats)
                report[person.name] = len(feats)
        return report

    def identify(self, feat):
        best, who = -1.0, None
        for name, F in self.db.items():
            s = float(np.max(F @ feat))
            if s > best:
                best, who = s, name
        return (who if best >= self.thr else None), best

    def __call__(self, frame):
        """Returns list of (box(x,y,w,h), name_or_None, score). Small faces get name '?'."""
        out = []
        for face in self.detect(frame):
            x, y, w, h = face[:4].astype(int)
            if min(w, h) < self.min_px:
                out.append(((x, y, w, h), "?", 0.0))
                continue
            name, score = self.identify(self.embed(frame, face)) if self.db else (None, 0.0)
            out.append(((x, y, w, h), name, score))
        return out
