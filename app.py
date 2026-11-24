#!/usr/bin/env python3
"""Raspberry Pi 5 smart security camera.

  motion (MOG2) -> person detection (SSD-MobileNet v1 int8 TFLite) -> face recognition (YuNet + SFace)
  -> event snapshot/clip/CSV, browser live view, Telegram alerts.

Usage:  ./run.sh            (headless, open http://<Pi IP>:8000)
        ./run.sh --show     (also show an OpenCV window on the Pi desktop)
        ./run.sh --enroll   (only register known/ faces and print the result)
"""
import argparse
import signal
import time

import cv2

from seccam import config as C
from seccam import draw, web
from seccam.detectors import Camera, FaceID, MotionDetector, PersonDetector
from seccam.events import EventManager
from seccam.notify import Telegram


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="config.json path")
    ap.add_argument("--show", action="store_true", help="show OpenCV window (q to quit)")
    ap.add_argument("--enroll", action="store_true", help="register known/ faces and exit")
    args = ap.parse_args()
    cfg = C.load(args.config)

    fc = cfg["face"]
    faceid = FaceID(C.resolve(fc["detector"]), C.resolve(fc["recognizer"]),
                    fc["det_score"], fc["match_threshold"], fc["min_face_px"])
    report = faceid.enroll(C.resolve(fc["known_dir"]))
    print(f"[enroll] {report or 'no known faces (put photos in known/<name>/)'}", flush=True)
    if args.enroll:
        return

    pc = cfg["person"]
    person = PersonDetector(C.resolve(pc["model"]), pc["score"], pc["threads"])
    motion = MotionDetector(cfg["motion"]["min_area_ratio"])
    tg_cfg = cfg["telegram"]
    tg = Telegram(tg_cfg["token"], tg_cfg["chat_id"], tg_cfg["enabled"])
    events = EventManager(C.resolve(cfg["storage"]["dir"]), cfg["event"], tg, tg_cfg)
    cam = Camera(**cfg["camera"])

    state = web.LiveState()
    if cfg["web"]["enabled"]:
        web.start(state, events, cfg["web"]["host"], cfg["web"]["port"])
    q = [cv2.IMWRITE_JPEG_QUALITY, cfg["web"]["jpeg_quality"]]

    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    mc = cfg["motion"]
    fps, t_prev, active_until, last_scan = 0.0, time.time(), 0.0, 0.0
    print("[main] running - Ctrl+C to stop", flush=True)
    try:
        while not stop:
            frame = cam.read()
            if frame is None:
                print("[main] no frame from camera", flush=True)
                continue
            now = time.time()
            moving, _ = motion(frame)
            if moving:
                active_until = now + mc["active_sec"]

            persons, faces = [], []
            if now < active_until or events.ev is not None or now - last_scan >= mc["scan_every_sec"]:
                last_scan = now
                persons = person(frame)
                if persons or moving:
                    faces = faceid(frame)
                if persons or faces:
                    active_until = now + mc["active_sec"]

            dt = now - t_prev
            t_prev = now
            fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps and dt > 0 else (1.0 / dt if dt > 0 else 0.0)

            status = {"fps": fps, "motion": moving, "rec": events.recording, "persons": len(persons),
                      "faces": [{"name": n, "score": round(s, 2)} for _, n, s in faces if n != "?"]}
            draw.annotate(frame, persons, faces, status)
            events.update(frame, persons, faces, now, fps)
            status["rec"] = events.recording
            state.publish(cv2.imencode(".jpg", frame, q)[1].tobytes(), status)

            if args.show:
                cv2.imshow("seccam", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        events.close()
        cam.release()
        cv2.destroyAllWindows()
        print("[main] stopped", flush=True)


if __name__ == "__main__":
    main()
