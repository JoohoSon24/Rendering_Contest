#!/usr/bin/env python3
"""
web_viewer.py — 브라우저 인터랙티브 뷰어 (HTTP 폴링, pyrender EGL)

실행:
  python scripts/web_viewer.py

VS Code PORTS 탭 → 7860 포워딩 → http://localhost:7860
  좌클릭 드래그 : 회전   |   휠 : 줌   |   스페이스바 : 렌더링
"""

import io
import os
import sys
import subprocess
import threading

import numpy as np
from PIL import Image

os.environ["PYOPENGL_PLATFORM"] = "egl"
import pyrender
import trimesh
from flask import Flask, Response, jsonify, render_template_string, request

from glb_utils import load_glb_base
from camera_utils import make_c2w, spherical_to_eye

ROOT          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLB_PATH      = os.path.join(ROOT, "meshes", "deformation1.glb")
OUT_PATH      = os.path.join(ROOT, "renders", "deformation.mp4")
RENDER_SCRIPT = os.path.join(ROOT, "scripts", "render_deformation.py")
PYTHON        = sys.executable

app          = Flask(__name__)
_tl          = threading.local()          # 스레드별 EGL 렌더러
_render_state = {"running": False, "msg": "대기 중", "ok": False}

# ─────────────────────────────────────────────────────────────────────────────
# 메쉬 로드 (서버 시작 시 1회)
# ─────────────────────────────────────────────────────────────────────────────

print(f"메쉬 로딩: {GLB_PATH}")
_pos, _norm, _faces, _colors = load_glb_base(GLB_PATH)
_center = (_pos.min(0) + _pos.max(0)) * 0.5
_diag   = np.linalg.norm(_pos.max(0) - _pos.min(0))
print(f"  center={np.round(_center, 3)}  diag={_diag:.3f}")

PREVIEW_W, PREVIEW_H = 360, 640

# ─────────────────────────────────────────────────────────────────────────────
# 렌더링 (스레드 로컬 EGL 컨텍스트)
# ─────────────────────────────────────────────────────────────────────────────

def _get_renderer():
    """스레드별 독립 EGL 렌더러 반환 (eglMakeCurrent 충돌 방지)."""
    if not hasattr(_tl, "renderer"):
        _tl.renderer = pyrender.OffscreenRenderer(PREVIEW_W, PREVIEW_H)
        fx = (PREVIEW_H / 2.0) / np.tan(np.radians(30))
        _tl.camera = pyrender.IntrinsicsCamera(
            fx=fx, fy=fx, cx=PREVIEW_W / 2, cy=PREVIEW_H / 2,
            znear=0.001, zfar=100.0,
        )
    return _tl.renderer, _tl.camera


def _render_frame(az: float, el: float, dist: float) -> bytes:
    """구면 좌표로 프리뷰 프레임을 렌더링해 JPEG bytes 반환."""
    eye = spherical_to_eye(_center, az, el, dist)
    c2w = make_c2w(eye, _center)
    renderer, camera = _get_renderer()

    fill_pose       = np.eye(4)
    fill_pose[:3, 3] = c2w[:3, 3] + np.array([-_diag * 0.8, _diag * 0.4, 0])

    scene = pyrender.Scene(bg_color=[14, 14, 20, 255], ambient_light=[0.25] * 3)
    scene.add(pyrender.Mesh.from_trimesh(
        trimesh.Trimesh(vertices=_pos, faces=_faces,
                        vertex_normals=_norm, vertex_colors=_colors, process=False),
        smooth=True,
    ))
    scene.add(camera, pose=c2w)
    scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=4.0), pose=c2w)
    scene.add(pyrender.DirectionalLight(color=np.ones(3) * 0.5, intensity=2.0), pose=fill_pose)

    color, _ = renderer.render(scene)
    buf = io.BytesIO()
    Image.fromarray(color).save(buf, format="JPEG", quality=82)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# HTML
# ─────────────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Deformation Viewer</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a14;color:#eee;font-family:monospace;
     display:flex;flex-direction:column;height:100vh;user-select:none}
#hdr{padding:7px 12px;background:#111;display:flex;align-items:center;gap:10px;flex-shrink:0}
#hdr h1{font-size:13px;color:#88aaff}
#status{font-size:11px;color:#aaa;flex:1}
#btn{padding:5px 16px;background:#2244bb;color:#fff;border:none;border-radius:4px;
     cursor:pointer;font-size:12px}
#btn:hover{background:#3355dd}
#btn:disabled{background:#223;color:#556;cursor:not-allowed}
#main{display:flex;flex:1;overflow:hidden}
#img{display:block;cursor:crosshair}
#side{padding:10px 14px;font-size:11px;color:#889;line-height:2;min-width:180px}
#side b{color:#aac}
#eye{margin-top:6px;color:#7be;font-size:10px;line-height:1.6}
#log{padding:6px 12px;font-size:11px;background:#0d0d18;
     border-top:1px solid #1a1a2a;flex-shrink:0;color:#6a8;min-height:28px}
#dl{display:none;margin-top:8px}
#dl a{color:#7be;font-size:10px}
</style>
</head>
<body>
<div id="hdr">
  <h1>🎬 Deformation Viewer</h1>
  <span id="status">로딩 중...</span>
  <button id="btn" onclick="doRender()" disabled>⏳ 로딩 중</button>
</div>
<div id="main">
  <div><img id="img" width="360" height="640"></div>
  <div id="side">
    <b>조작법</b><br>
    좌클릭 드래그 → 회전<br>
    마우스 휠 → 줌<br>
    <b>[스페이스바]</b> → 렌더링<br>
    <br><b>현재 카메라</b>
    <div id="eye">-</div>
    <div id="dl"><a id="dl-a" href="/video" target="_blank">📥 deformation.mp4 다운로드</a></div>
  </div>
</div>
<div id="log">초기화 중...</div>

<script>
const CX = [0.443, -0.387, -0.513];
let az=44, el=39, dist=1.38;
let dragging=false, lastX=0, lastY=0, fetching=false, rendering=false;

const img  = document.getElementById('img');
const btn  = document.getElementById('btn');
const log  = document.getElementById('log');

function sphericalToEye(az,el,d){
  const a=az*Math.PI/180, e=el*Math.PI/180;
  return [CX[0]+d*Math.sin(a)*Math.cos(e), CX[1]+d*Math.sin(e), CX[2]+d*Math.cos(a)*Math.cos(e)];
}

function fetchFrame(){
  if(fetching) return;
  fetching=true;
  fetch(`/frame?az=${az}&el=${el}&dist=${dist}&t=${Date.now()}`)
    .then(r=>{ if(!r.ok) throw r.status; return r.blob(); })
    .then(b=>{
      img.src=URL.createObjectURL(b);
      document.getElementById('status').textContent='준비됨';
      btn.disabled=false; btn.textContent='⏎ SPACE — 렌더링';
      const e=sphericalToEye(az,el,dist);
      document.getElementById('eye').innerHTML=
        `eye=[${e.map(v=>v.toFixed(4)).join(', ')}]<br>az=${az.toFixed(1)}° el=${el.toFixed(1)}° dist=${dist.toFixed(3)}`;
    })
    .catch(e=>{ log.textContent='렌더 오류: '+e; })
    .finally(()=>{ fetching=false; });
}

img.addEventListener('mousedown',e=>{ dragging=true; lastX=e.clientX; lastY=e.clientY; e.preventDefault(); });
window.addEventListener('mouseup',()=>{ dragging=false; });
window.addEventListener('mousemove',e=>{
  if(!dragging) return;
  az+=(e.clientX-lastX)*0.5;
  el=Math.max(-89,Math.min(89,el-(e.clientY-lastY)*0.5));
  lastX=e.clientX; lastY=e.clientY;
  fetchFrame();
});
img.addEventListener('wheel',e=>{
  dist*=e.deltaY>0?1.08:0.93; dist=Math.max(0.3,Math.min(6,dist));
  fetchFrame(); e.preventDefault();
},{passive:false});
img.addEventListener('contextmenu',e=>e.preventDefault());
document.addEventListener('keydown',e=>{ if(e.code==='Space'){ e.preventDefault(); doRender(); } });

function doRender(){
  if(rendering||btn.disabled) return;
  rendering=true; btn.disabled=true; btn.textContent='🎬 렌더링 중...';
  log.textContent='🎬 렌더링 시작 (약 3분 소요)...';
  fetch(`/render?az=${az}&el=${el}&dist=${dist}`,{method:'POST'}).then(r=>r.json()).then(d=>{ log.textContent=d.msg; });
  const poll=setInterval(()=>{
    fetch('/render_status').then(r=>r.json()).then(d=>{
      log.textContent=d.msg;
      if(!d.running){
        clearInterval(poll); rendering=false; btn.disabled=false; btn.textContent='⏎ SPACE — 렌더링';
        if(d.ok){ document.getElementById('dl').style.display='block'; document.getElementById('dl-a').href='/video?t='+Date.now(); }
      }
    });
  },3000);
}

fetchFrame();
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
# Flask 라우트
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/frame")
def frame():
    try:
        data = _render_frame(
            float(request.args.get("az",   44)),
            float(request.args.get("el",   39)),
            float(request.args.get("dist", 1.38)),
        )
        return Response(data, mimetype="image/jpeg",
                        headers={"Cache-Control": "no-store"})
    except Exception as e:
        return str(e), 500


@app.route("/render", methods=["POST"])
def start_render():
    if _render_state["running"]:
        return jsonify({"msg": "이미 렌더링 중입니다.", "ok": False})

    eye      = spherical_to_eye(_center,
                                float(request.args.get("az",   44)),
                                float(request.args.get("el",   39)),
                                float(request.args.get("dist", 1.38)))
    c2w_flat = make_c2w(eye, _center).flatten().tolist()

    print(f"\n📸 eye=[{eye[0]:.4f}, {eye[1]:.4f}, {eye[2]:.4f}]  렌더링 시작")
    _render_state.update(running=True, msg="🎬 렌더링 중...", ok=False)

    def _run():
        result = subprocess.run(
            [PYTHON, RENDER_SCRIPT, "--c2w"] + [str(v) for v in c2w_flat] + ["-o", OUT_PATH],
            text=True,
        )
        ok  = result.returncode == 0
        msg = f"✅ 완료: {os.path.basename(OUT_PATH)}" if ok else f"❌ 실패 (code={result.returncode})"
        print(msg)
        _render_state.update(running=False, msg=msg, ok=ok)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"msg": "렌더링 시작됨", "ok": True})


@app.route("/render_status")
def render_status():
    return jsonify(_render_state)


@app.route("/video")
def video():
    if not os.path.exists(OUT_PATH):
        return "영상 없음", 404
    return Response(
        open(OUT_PATH, "rb").read(),
        mimetype="video/mp4",
        headers={"Content-Disposition": "attachment; filename=deformation.mp4"},
    )


if __name__ == "__main__":
    print(f"\n{'='*55}")
    print("🌐 웹 뷰어  →  http://localhost:7860")
    print("   VS Code PORTS 탭에서 7860 포워딩 후 접속")
    print(f"{'='*55}\n")
    app.run(host="0.0.0.0", port=7860, debug=False, threaded=True)
