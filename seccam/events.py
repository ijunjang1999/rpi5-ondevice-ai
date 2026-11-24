"""Event lifecycle: someone appears -> snapshot + clip (with pre-roll) -> alerts -> CSV log row."""
import csv
import time
from collections import deque
from pathlib import Path

import cv2

FIELDS = ["id", "start", "end", "duration_s", "people", "unknown_faces", "snapshot", "clip"]


class EventManager:
    def __init__(self, storage_dir, cfg, notifier, tg_cfg):
        self.dir = Path(storage_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.csv = self.dir / "events.csv"
        if not self.csv.exists():
            with open(self.csv, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(FIELDS)
        self.cfg, self.tg, self.tg_cfg = cfg, notifier, tg_cfg
        self.pre = deque()
        self.ev = None
        self.last_notified = {}  # name -> time

    @staticmethod
    def _jpeg(frame, q=85):
        return cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, q])[1].tobytes()

    @property
    def recording(self):
        return self.ev is not None and self.ev["writer"] is not None

    def present_names(self):
        return sorted(self.ev["names"]) if self.ev else []

    def update(self, frame, persons, faces, now, fps):
        """frame: annotated frame. Call once per processed frame."""
        self.pre.append(frame)
        while len(self.pre) > max(1, int(self.cfg["pre_record_sec"] * max(fps, 1))):
            self.pre.popleft()

        present = bool(persons) or any(n != "?" for _, n, _ in faces)
        if self.ev is None:
            if present:
                self._start(frame, now, fps)
            else:
                return
        ev = self.ev
        if present:
            ev["last_seen"] = now
        if ev["writer"] is not None:
            ev["writer"].write(frame)

        for _, name, score in faces:
            if name == "?":
                continue
            if name is None:
                ev["unknown"] += 1
                continue
            if name not in ev["names"]:
                ev["names"].add(name)
                if not ev["has_face_snap"]:
                    cv2.imwrite(str(self.dir / ev["snapshot"]), frame)
                    ev["has_face_snap"] = True
                if (self.tg_cfg["notify_known"] and not self.cfg.get("presence_notifies")
                        and now - self.last_notified.get(name, 0) > self.tg_cfg["cooldown_sec"]):
                    self.last_notified[name] = now
                    self.tg.send(f"✅ {name} 님 확인 ({score:.2f})  {time.strftime('%H:%M:%S')}", self._jpeg(frame))

        if not ev["alerted"] and not ev["names"] and now - ev["start"] >= self.cfg["unknown_alert_after_sec"]:
            ev["alerted"] = True
            what = "⚠️ 미등록 인물 감지" if ev["unknown"] else "⚠️ 사람 감지 (얼굴 확인 불가)"
            self.tg.send(f"{what}  {time.strftime('%H:%M:%S')}", self._jpeg(frame))
            if ev["unknown"] and not ev["has_face_snap"]:
                cv2.imwrite(str(self.dir / ev["snapshot"]), frame)

        if now - ev["last_seen"] > self.cfg["end_after_sec"] or now - ev["start"] > self.cfg["max_len_sec"]:
            self._finish(now)

    def _start(self, frame, now, fps):
        eid = time.strftime("%Y%m%d_%H%M%S")
        h, w = frame.shape[:2]
        writer, clip = None, ""
        if self.cfg["record"]:
            clip = f"{eid}.mp4"
            writer = cv2.VideoWriter(str(self.dir / clip), cv2.VideoWriter_fourcc(*"mp4v"),
                                     max(1.0, round(fps, 1)), (w, h))
            if not writer.isOpened():
                print("[event] VideoWriter failed - recording disabled for this event", flush=True)
                writer, clip = None, ""
            else:
                for f in self.pre:
                    writer.write(f)
        snap = f"{eid}.jpg"
        cv2.imwrite(str(self.dir / snap), frame)
        self.ev = dict(id=eid, start=now, last_seen=now, names=set(), unknown=0, alerted=False,
                       writer=writer, clip=clip, snapshot=snap, has_face_snap=False)
        print(f"[event] {eid} start", flush=True)

    def _finish(self, now):
        ev, self.ev = self.ev, None
        if ev["writer"] is not None:
            ev["writer"].release()
        # only known people and no alert raised (e.g. someone studying at the desk all day):
        # drop clip + snapshot to save space; the CSV row is kept
        if ev["names"] and not ev["unknown"] and not ev["alerted"] and not self.cfg.get("keep_known_only_clips", False):
            for k in ("clip", "snapshot"):
                if ev[k]:
                    (self.dir / ev[k]).unlink(missing_ok=True)
                    ev[k] = ""
        row =[ev["id"], time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ev["start"])),
               time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), round(now - ev["start"], 1),
               ";".join(sorted(ev["names"])) or ("Unknown" if ev["unknown"] else "person"),
               ev["unknown"], ev["snapshot"], ev["clip"]]
        with open(self.csv, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)
        print(f"[event] {ev['id']} end: {row[4]} ({row[3]} s)", flush=True)

    def close(self):
        if self.ev is not None:
            self._finish(time.time())

    def recent(self, n=50):
        with open(self.csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return rows[-n:][::-1]
