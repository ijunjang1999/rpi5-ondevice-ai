#!/usr/bin/env python3
"""Take enrollment photos with the webcam:  python tools/capture_face.py 이름 [-n 5]
Saves one photo per second (only when exactly one face is visible) into known/<이름>/."""
import argparse
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from seccam import config as C  # noqa: E402
from seccam.detectors import Camera, FaceID  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("-n", type=int, default=5, help="number of photos")
    args = ap.parse_args()
    cfg = C.load()
    fc = cfg["face"]
    fid = FaceID(C.resolve(fc["detector"]), C.resolve(fc["recognizer"]), fc["det_score"])
    out = C.resolve(fc["known_dir"]) / args.name
    out.mkdir(parents=True, exist_ok=True)
    cam = Camera(**cfg["camera"])
    print(f"카메라를 정면으로 봐 주세요. 사진 {args.n}장을 찍습니다 (얼굴 각도를 조금씩 바꾸면 더 좋아요).")
    saved, last = 0, 0.0
    try:
        while saved < args.n:
            f = cam.read()
            if f is None:
                continue
            faces = fid.detect(f)
            if len(faces) == 1 and time.time() - last >= 1.0 and min(faces[0][2:4]) >= 80:
                p = out / f"{time.strftime('%Y%m%d_%H%M%S')}_{saved}.jpg"
                cv2.imencode(".jpg", f)[1].tofile(str(p))
                saved, last = saved + 1, time.time()
                print(f"  [{saved}/{args.n}] {p.name}")
            elif len(faces) != 1 and time.time() - last >= 3.0:
                print(f"  얼굴 {len(faces)}개 감지됨 - 한 명만 화면에 나오게 해 주세요")
                last = time.time() - 2.0
    finally:
        cam.release()
    print(f"완료: {out}  (다음 실행 때 자동 등록됩니다)")


if __name__ == "__main__":
    main()
