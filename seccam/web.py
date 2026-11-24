"""Browser UI: live MJPEG stream, who is present now, recent events with snapshots/clips."""
import logging
import threading
import time

from flask import Flask, Response, abort, jsonify, send_from_directory


class LiveState:
    def __init__(self):
        self.cond = threading.Condition()
        self.jpeg, self.seq = None, 0
        self.status = {}

    def publish(self, jpeg, status):
        with self.cond:
            self.jpeg, self.status = jpeg, status
            self.seq += 1
            self.cond.notify_all()


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pi 보안카메라</title><style>
:root{color-scheme:light dark}body{font-family:system-ui,sans-serif;margin:0 auto;max-width:960px;padding:16px}
img.live{width:100%;border-radius:8px;background:#000}
#st{font-size:1.1em;margin:8px 0}.b{display:inline-block;padding:2px 8px;border-radius:12px;margin-right:4px;
background:#2e7d32;color:#fff}.u{background:#c62828}table{width:100%;border-collapse:collapse;font-size:.9em}
td,th{padding:6px;border-bottom:1px solid #8884;text-align:left;vertical-align:middle}td img{height:60px;border-radius:4px}
</style></head><body>
<h2>Raspberry Pi 5 보안카메라</h2>
<img class="live" src="/stream" alt="live">
<div id="st">연결 중...</div>
<h3>최근 이벤트</h3>
<table><thead><tr><th>스냅샷</th><th>시작</th><th>시간(s)</th><th>인물</th><th>영상</th></tr></thead>
<tbody id="ev"></tbody></table>
<script>
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function tick(){
 try{
  const s=await (await fetch('/status')).json();
  let h=`${s.fps.toFixed(1)} FPS · ${s.motion?'움직임 있음':'조용함'}`;
  if(s.rec) h+=' · <b style="color:#e53935">● 녹화 중</b>';
  h+='<br>'+(s.faces.length?s.faces.map(f=>`<span class="b ${f.name?'':'u'}">${esc(f.name||'Unknown')}</span>`).join(''):(s.persons?`사람 ${s.persons}명 (얼굴 미확인)`:'아무도 없음'));
  document.getElementById('st').innerHTML=h;
  const ev=await (await fetch('/events.json')).json();
  document.getElementById('ev').innerHTML=ev.map(e=>`<tr><td><a href="/media/${esc(e.snapshot)}" target="_blank"><img src="/media/${esc(e.snapshot)}"></a></td>
   <td>${esc(e.start)}</td><td>${esc(e.duration_s)}</td><td>${esc(e.people)}</td>
   <td>${e.clip?`<a href="/media/${esc(e.clip)}" download>mp4</a>`:''}</td></tr>`).join('');
 }catch(e){document.getElementById('st').textContent='연결 끊김'}
}
tick();setInterval(tick,2000);
</script></body></html>"""


def start(state, events, host="0.0.0.0", port=8000):
    app = Flask(__name__)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    @app.route("/")
    def index():
        return PAGE

    @app.route("/stream")
    def stream():
        def gen():
            last = -1
            while True:
                with state.cond:
                    state.cond.wait_for(lambda: state.seq != last, timeout=5)
                    if state.seq == last:
                        continue
                    last, jpg = state.seq, state.jpeg
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                time.sleep(0.03)
        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/status")
    def status():
        return jsonify(state.status)

    @app.route("/events.json")
    def events_json():
        return jsonify(events.recent(50))

    @app.route("/media/<path:name>")
    def media(name):
        if "/" in name or "\\" in name or not name.lower().endswith((".jpg", ".mp4")):
            abort(404)
        return send_from_directory(events.dir, name)

    t = threading.Thread(target=lambda: app.run(host=host, port=port, threaded=True, use_reloader=False),
                         daemon=True)
    t.start()
    print(f"[web] http://<Pi IP>:{port}  (e.g. http://192.168.137.220:{port})", flush=True)
