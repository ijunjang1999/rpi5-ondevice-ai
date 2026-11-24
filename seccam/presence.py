"""Research-time tracking: per-person presence sessions -> presence.csv, daily/weekly totals,
Telegram start/end messages and a daily summary.

A session starts when a known face is recognised. It stays alive while that face is seen again,
or (person_keeps_alive) while at least as many people as open sessions are detected - people at a
desk often face away from the camera. It ends `away_after_sec` after the last sighting; the away
tail is not counted."""
import csv
import time
from datetime import date, datetime, timedelta
from pathlib import Path

FIELDS = ["name", "date", "start", "end", "minutes"]


def fmt_min(m):
    m = int(round(m))
    return f"{m // 60}h {m % 60:02d}m"


class Presence:
    def __init__(self, path, cfg, notifier):
        self.path = Path(path)
        if not self.path.exists():
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(FIELDS)
        self.cfg, self.tg = cfg, notifier
        self.active = {}  # name -> {"start": t, "last": t}
        self.reported = date.today().isoformat() if self._past_report_time(datetime.now()) else None

    # ---------- live update ----------
    def update(self, names, n_persons, now):
        for n in set(names):
            s = self.active.get(n)
            if s is None:
                self.active[n] = {"start": now, "last": now}
                if self.cfg["notify"]:
                    self.tg.send(f"🟢 {n} 연구 시작  {time.strftime('%H:%M')}")
            else:
                s["last"] = now
        if self.cfg["person_keeps_alive"] and self.active and n_persons >= len(self.active):
            for s in self.active.values():
                s["last"] = now
        for n, s in list(self.active.items()):
            if now - s["last"] > self.cfg["away_after_sec"]:
                self._close(n, s)
        self._daily_report()

    def _close(self, name, s):
        del self.active[name]
        minutes = (s["last"] - s["start"]) / 60
        if minutes * 60 < self.cfg["min_session_sec"]:
            return
        st, en = datetime.fromtimestamp(s["start"]), datetime.fromtimestamp(s["last"])
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([name, st.date().isoformat(), st.strftime("%H:%M:%S"),
                                    en.strftime("%H:%M:%S"), round(minutes, 1)])
        if self.cfg["notify"]:
            today = self.minutes_by_day(name).get(date.today().isoformat(), 0)
            self.tg.send(f"🔴 {name} 연구 종료  {en.strftime('%H:%M')}\n이번 {fmt_min(minutes)} · 오늘 합계 {fmt_min(today)}")

    def close_all(self):
        for n, s in list(self.active.items()):
            self._close(n, s)

    # ---------- totals ----------
    def _rows(self):
        with open(self.path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def minutes_by_day(self, name=None):
        """{date: minutes} for one person, or {name: {date: minutes}} for everybody. Includes open sessions."""
        out = {}
        for r in self._rows():
            d = out.setdefault(r["name"], {})
            d[r["date"]] = d.get(r["date"], 0) + float(r["minutes"])
        for n, s in self.active.items():
            day = datetime.fromtimestamp(s["start"]).date().isoformat()
            d = out.setdefault(n, {})
            d[day] = d.get(day, 0) + (s["last"] - s["start"]) / 60
        return out.get(name, {}) if name else out

    def summary(self, days=7):
        by = self.minutes_by_day()
        dates = [(date.today() - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
        people = []
        for n in sorted(by):
            row = [round(by[n].get(d, 0)) for d in dates]
            s = self.active.get(n)
            people.append({"name": n, "today": row[-1], "week": sum(row), "days": row,
                           "active": s is not None,
                           "since": time.strftime("%H:%M", time.localtime(s["start"])) if s else None})
        return {"dates": dates, "people": people}

    # ---------- daily Telegram summary ----------
    def _past_report_time(self, dt):
        t = self.cfg.get("daily_report_time")
        return bool(t) and dt.strftime("%H:%M") >= t

    def _daily_report(self):
        now = datetime.now()
        today = now.date().isoformat()
        if self.reported == today or not self._past_report_time(now):
            return
        self.reported = today
        lines = [f"📊 {today} 연구시간"]
        for p in self.summary()["people"]:
            if p["today"] or p["week"]:
                lines.append(f"· {p['name']}: 오늘 {fmt_min(p['today'])} / 최근 7일 {fmt_min(p['week'])}")
        if len(lines) == 1:
            lines.append("기록 없음")
        self.tg.send("\n".join(lines))
