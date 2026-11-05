"""FastAPI web service: JSON API + a single-page web UI (fallback to Telegram)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .qalog import ask_logged

app = FastAPI(title="UZEX AI Agent", version="0.2.0")


class AskRequest(BaseModel):
    question: str = Field(..., max_length=500)


class AskResponse(BaseModel):
    answer: str
    intent: str
    lang: str
    sql: str = ""
    filters: str = ""
    seconds: float = 0.0


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    response, elapsed = await run_in_threadpool(ask_logged, request.question, "web")
    return AskResponse(
        answer=response.answer,
        intent=response.intent,
        lang=response.lang,
        sql=response.sql,
        filters=response.filters,
        seconds=round(elapsed, 2),
    )


PAGE = """<!doctype html>
<html lang="uz"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UZEX AI-agent</title>
<style>
 body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;margin:32px auto;padding:0 16px;color:#1d2433;background:#fafaf7}
 h1{font-size:22px;margin:0 0 4px} .sub{color:#667;margin:0 0 20px;font-size:14px}
 form{display:flex;gap:8px} input{flex:1;padding:12px;font-size:16px;border:1px solid #ccd;border-radius:8px}
 button{padding:12px 18px;font-size:16px;border:0;border-radius:8px;background:#1f4e79;color:#fff;cursor:pointer}
 button:disabled{opacity:.6}
 .ex{margin:12px 0 20px;display:flex;flex-wrap:wrap;gap:6px}
 .ex span{font-size:13px;padding:6px 10px;border:1px solid #ccd;border-radius:16px;cursor:pointer;background:#fff}
 .ans{white-space:pre-wrap;background:#fff;border:1px solid #dde;border-radius:8px;padding:16px;line-height:1.45}
 details{margin-top:10px} pre{white-space:pre-wrap;font-size:12px;background:#f0f2f5;padding:10px;border-radius:6px}
 .meta{color:#889;font-size:12px;margin-top:6px}
</style></head><body>
<h1>UZEX birja bitimlari — AI-agent</h1>
<p class="sub">Xuş kelibsiz! Savol bering: özbek (lotin, yangi alifbo, kirill) yoki rus tilida. Javob savol tilida, qanday hisoblangani bilan (03.01.2022 – 30.10.2026).<br>Добро пожаловать! Вопрос можно задать на русском или узбекском.</p>
<form id="f"><input id="q" placeholder="Masalan: 2025-yilda jami savdo summasi qancha?" autofocus>
<button id="b">So‘rash</button></form>
<div class="ex" id="ex"></div>
<div id="out"></div>
<p class="meta" style="margin-top:32px">Qöqon universiteti Andijon filiali (KUAF) iştirokçilari tomonidan tayyorlandi.<br>
Подготовлено участниками Андижанского филиала Кокандского университета (KUAF).</p>
<script>
const EX=["2025-yilda jami savdo summasi qancha?","Ötgan oyda eksport qança dollar?","Ўтган йили энг кўп пахта сотган 3 та компания",
"Топ-5 компаний по сумме сделок в 2024 году","Экспорт в прошлом квартале в долларах",
"Средняя цена хлопка за последние 3 месяца","100001-kontrakt haqida ma’lumot"];
const ex=document.getElementById('ex');
EX.forEach(t=>{const s=document.createElement('span');s.textContent=t;s.onclick=()=>{q.value=t;go()};ex.appendChild(s)});
const f=document.getElementById('f'),q=document.getElementById('q'),b=document.getElementById('b'),out=document.getElementById('out');
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
async function go(){const question=q.value.trim();if(!question)return;b.disabled=true;
 out.innerHTML='<div class="ans">⏳ Tahlil qilinmoqda… / Анализирую…</div>';
 try{const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});
  const d=await r.json();let h='<div class="ans">'+esc(d.answer||'—')+'</div>';
  h+='<div class="meta">'+esc(d.intent||'')+' · '+(d.seconds||0)+' s</div>';
  if(d.sql){h+='<details><summary>🧾 SQL sörov / SQL-запрос</summary><p>'+esc(d.filters||'')+'</p><pre>'+esc(d.sql.trim())+'</pre></details>'}
  out.innerHTML=h}catch(e){out.innerHTML='<div class="ans">Xatolik / Ошибка: '+esc(String(e))+'</div>'}
 b.disabled=false}
f.onsubmit=e=>{e.preventDefault();go()};
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE
