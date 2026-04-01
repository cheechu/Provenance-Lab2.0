"""
CasAI Provenance Lab — API Playground
GET /playground  — serves an interactive in-browser API tester
                   (no external deps, plain HTML + JS)
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

playground_router = APIRouter(tags=["Playground"])

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CasAI API Playground</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0c0d0f;--bg1:#111317;--bg2:#161820;--line:rgba(255,255,255,0.07);--text:#e8eaf0;--muted:#636878;--dim:#3a3e4d;--blue:#3d8ef0;--green:#3ecf8e;--amber:#f0a23d;--red:#e05858;--mono:'IBM Plex Mono',monospace;--sans:'IBM Plex Sans',sans-serif}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:13px;line-height:1.5;padding:28px;max-width:960px;margin:0 auto}
h1{font-family:var(--mono);font-size:14px;color:var(--blue);letter-spacing:0.12em;text-transform:uppercase;margin-bottom:4px}
.sub{font-family:var(--mono);font-size:10px;color:var(--muted);margin-bottom:24px}
.panel{background:var(--bg1);border:1px solid var(--line);border-radius:5px;margin-bottom:16px;overflow:hidden}
.ph{padding:10px 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;background:var(--bg2)}
.ph-title{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.1em}
.pb{padding:14px 16px}
label{font-family:var(--mono);font-size:10px;color:var(--muted);display:block;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.08em}
input,select,textarea{width:100%;background:var(--bg2);border:1px solid rgba(255,255,255,0.1);border-radius:3px;padding:7px 10px;font-family:var(--mono);font-size:11px;color:var(--text);outline:none;margin-bottom:12px}
input:focus,select:focus,textarea:focus{border-color:var(--blue)}
textarea{height:120px;resize:vertical}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.method-url{display:flex;gap:8px;margin-bottom:12px;align-items:center}
select.method{width:auto;min-width:80px;margin-bottom:0;color:var(--blue)}
input.url{flex:1;margin-bottom:0}
button{font-family:var(--mono);font-size:11px;padding:7px 16px;border-radius:3px;cursor:pointer;border:1px solid rgba(255,255,255,0.1);background:var(--blue);color:#fff;transition:all 0.12s}
button:hover{background:#5aa0f5}
button.sec{background:transparent;color:var(--muted)}
button.sec:hover{color:var(--text);border-color:var(--dim)}
.result{font-family:var(--mono);font-size:11px;background:var(--bg);border:1px solid var(--line);border-radius:3px;padding:12px 14px;max-height:320px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;color:var(--muted);line-height:1.7;margin-top:12px}
.result .key{color:var(--blue)}.result .str{color:var(--green)}.result .num{color:var(--amber)}.result .bool{color:var(--red)}
.status-ok{color:var(--green);font-family:var(--mono);font-size:10px}.status-err{color:var(--red);font-family:var(--mono);font-size:10px}
.endpoint-list{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
.ep{font-family:var(--mono);font-size:10px;padding:3px 9px;border-radius:2px;border:1px solid var(--line);cursor:pointer;color:var(--muted);transition:all 0.12s}
.ep:hover{color:var(--text);border-color:var(--dim)}
.ep.post{border-color:rgba(62,207,142,0.2);color:var(--green)}.ep.get{border-color:var(--blue);color:var(--blue)}.ep.del{border-color:rgba(224,88,88,0.2);color:var(--red)}
</style>
</head>
<body>
<h1>CasAI Provenance Lab · API Playground</h1>
<div class="sub">Interactive API tester · auth pre-fills from login · base: http://localhost:8000</div>

<div class="panel">
  <div class="ph"><span class="ph-title">Auth · get a JWT</span></div>
  <div class="pb">
    <div class="row">
      <div><label>Email</label><input id="email" value="researcher@casai.dev"></div>
      <div><label>Password</label><input id="password" type="password" value="CasAI2025!"></div>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <button onclick="doLogin()">Login →</button>
      <button class="sec" onclick="doRegister()">Register first</button>
      <span id="auth-status" style="font-family:var(--mono);font-size:10px;color:var(--muted)"></span>
    </div>
  </div>
</div>

<div class="panel">
  <div class="ph"><span class="ph-title">Request builder</span><span id="req-status"></span></div>
  <div class="pb">
    <div class="endpoint-list">
      <span class="ep get" onclick="load('GET','/runs')">GET /runs</span>
      <span class="ep post" onclick="load('POST','/runs',runPayload)">POST /runs</span>
      <span class="ep post" onclick="load('POST','/runs/stream',runPayload)">POST /runs/stream</span>
      <span class="ep get" onclick="load('GET','/benchmarks/leaderboard')">GET /leaderboard</span>
      <span class="ep post" onclick="load('POST','/benchmarks/run',runPayload)">POST /benchmark</span>
      <span class="ep get" onclick="load('GET','/auth/me')">GET /me</span>
      <span class="ep get" onclick="load('GET','/auth/api-keys')">GET /api-keys</span>
      <span class="ep post" onclick="load('POST','/auth/api-keys',{name:'playground-key'})">POST /api-key</span>
      <span class="ep get" onclick="load('GET','/notifications')">GET /notifications</span>
      <span class="ep get" onclick="load('GET','/settings/me')">GET /settings</span>
      <span class="ep get" onclick="load('GET','/admin/stats')">GET /admin/stats</span>
      <span class="ep get" onclick="load('GET','/health')">GET /health</span>
    </div>
    <div class="method-url">
      <select class="method" id="method"><option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option></select>
      <input class="url" id="url" value="/health">
    </div>
    <label>Request body (JSON)</label>
    <textarea id="body" placeholder="Leave empty for GET requests"></textarea>
    <label>Bearer token (auto-filled after login)</label>
    <input id="token" placeholder="eyJ...">
    <div style="display:flex;gap:8px">
      <button onclick="sendRequest()">Send ↗</button>
      <button class="sec" onclick="clearResult()">Clear</button>
    </div>
    <div id="result" class="result" style="display:none"></div>
  </div>
</div>

<script>
const BASE = 'http://localhost:8000';
let token = '';

const runPayload = {
  guide_rna:{sequence:"ATGCATGCATGCATGCATGC",pam:"NGG",target_gene:"BRCA1",chromosome:"chr17",position_start:41196312,position_end:41196331,strand:"+"},
  editor_config:{editor_type:"CBE",cas_variant:"nCas9",deaminase:"APOBEC3A",editing_window_start:4,editing_window_end:8,algorithms:["CFD","MIT"]},
  track:"genomics_research",random_seed:42,benchmark_mode:false
};

function load(method, url, body) {
  document.getElementById('method').value = method;
  document.getElementById('url').value = url;
  document.getElementById('body').value = body ? JSON.stringify(body, null, 2) : '';
}

async function doLogin() {
  const r = await fetch(BASE + '/auth/login', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({email: document.getElementById('email').value, password: document.getElementById('password').value})
  });
  const d = await r.json();
  if (d.access_token) {
    token = d.access_token;
    document.getElementById('token').value = token;
    document.getElementById('auth-status').textContent = '✓ logged in as ' + d.user.email;
    document.getElementById('auth-status').style.color = '#3ecf8e';
  } else {
    document.getElementById('auth-status').textContent = d.detail || 'Login failed';
    document.getElementById('auth-status').style.color = '#e05858';
  }
}

async function doRegister() {
  await fetch(BASE + '/auth/register', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({email: document.getElementById('email').value, password: document.getElementById('password').value, full_name: 'Playground User'})
  });
  await doLogin();
}

async function sendRequest() {
  const method = document.getElementById('method').value;
  const url = BASE + document.getElementById('url').value;
  const body = document.getElementById('body').value.trim();
  const tok = document.getElementById('token').value.trim();
  const headers = {'Content-Type': 'application/json'};
  if (tok) headers['Authorization'] = 'Bearer ' + tok;
  const opts = {method, headers};
  if (body && method !== 'GET') { try { opts.body = body; } catch(e){} }
  const t0 = performance.now();
  try {
    const r = await fetch(url, opts);
    const ms = (performance.now() - t0).toFixed(0);
    const text = await r.text();
    let parsed;
    try { parsed = JSON.parse(text); } catch(e) { parsed = text; }
    const el = document.getElementById('result');
    el.style.display = 'block';
    document.getElementById('req-status').innerHTML = `<span class="${r.ok ? 'status-ok' : 'status-err'}">${r.status} ${r.statusText} · ${ms}ms</span>`;
    el.innerHTML = syntaxHL(typeof parsed === 'string' ? parsed : JSON.stringify(parsed, null, 2));
  } catch(e) {
    document.getElementById('result').style.display = 'block';
    document.getElementById('result').textContent = 'Network error: ' + e.message;
  }
}

function syntaxHL(json) {
  return json
    .replace(/(".*?")(\s*:)/g, '<span class="key">$1</span>$2')
    .replace(/:\s*(".*?")/g, ': <span class="str">$1</span>')
    .replace(/:\s*(true|false|null)/g, ': <span class="bool">$1</span>')
    .replace(/:\s*(-?\d+\.?\d*)/g, ': <span class="num">$1</span>');
}

function clearResult() {
  document.getElementById('result').style.display = 'none';
  document.getElementById('req-status').innerHTML = '';
}
</script>
</body>
</html>"""


@playground_router.get("/playground", response_class=HTMLResponse, include_in_schema=False)
def playground() -> str:
    return _HTML
