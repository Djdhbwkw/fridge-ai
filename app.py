# AI 冰箱管家 —— 最小可執行版本
# 安裝：pip install flask google-genai
# 執行：python app.py，然後用瀏覽器打開 http://127.0.0.1:5000

import html
import io
import json
import os
import time
from PIL import Image
import markdown
from flask import Flask, request, render_template_string
from google import genai
from google.genai import types

# 金鑰從環境變數讀取（上線到 Render 時在網站後台設定 GEMINI_API_KEY），不要直接寫在程式裡
API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-4-hydrogen")   # 可在 Render 環境變數 GEMINI_MODEL 換模型

# 主要模型忙線時改用的備用模型（用逗號分隔，可在 Render 環境變數 GEMINI_FALLBACK 修改）
FALLBACK = [m.strip() for m in os.environ.get("GEMINI_FALLBACK", "gemini-3.8-flash").split(",") if m.strip()]

# 每次呼叫 AI 最多等 30 秒，避免一直轉圈圈
client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(timeout=30000))


def _fast_config(config):
    """加上「低思考」設定，讓模型少想一點、回得快一點。套件不支援就維持原設定。"""
    try:
        level = getattr(types, "ThinkingLevel", None)
        tc = types.ThinkingConfig(thinking_level=level.LOW if level else "low")
        if config is None:
            return types.GenerateContentConfig(thinking_config=tc)
        return config.model_copy(update={"thinking_config": tc})
    except Exception:
        return config


def call_ai(contents, config=None):
    """呼叫 Gemini：先用低思考模式求快；主模型忙線（503/429）就立刻換備用模型，不再原地等待。"""
    fast = _fast_config(config)
    last_err = None
    models = [MODEL] + FALLBACK
    start = time.time()
    for round_no in range(2):              # 全部模型都忙的話，休息 2 秒再整輪試一次
        for model in models:
            for cfg in ([fast, config] if fast is not config else [config]):
                if time.time() - start > 90:      # 總共超過 90 秒就放棄，避免頁面一直轉圈圈
                    raise last_err or TimeoutError("AI 回應逾時")
                t0 = time.time()
                try:
                    resp = client.models.generate_content(model=model, contents=contents, config=cfg)
                    print(f"[AI] 使用模型={model} 耗時 {time.time() - t0:.1f} 秒", flush=True)
                    return resp
                except Exception as e:
                    last_err = e
                    msg = str(e)
                    print(f"[AI 失敗] 模型={model} 耗時 {time.time() - t0:.1f} 秒：{msg[:120]}", flush=True)
                    if "thinking" in msg.lower() and cfg is fast:
                        continue           # 這個模型不支援低思考設定 → 用一般設定再試
                    break                  # 忙線、逾時或其他錯誤 → 換下一個模型
        if round_no == 0:
            time.sleep(2)
    raise last_err


def friendly(e):
    msg = str(e)
    if "503" in msg or "UNAVAILABLE" in msg:
        return "AI 目前使用人數太多，請過 1 分鐘再試一次。"
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "今天的免費使用次數可能用完了，請稍後再試。"
    if "timed out" in msg.lower() or "timeout" in msg.lower() or "逾時" in msg:
        return "AI 回應太慢，請再試一次。"
    return f"發生錯誤：{msg[:200]}"


app = Flask(__name__)

PAGE = r"""
<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 冰箱管家</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
:root{--g9:#173d22;--g8:#1f5130;--g7:#2e6b3a;--g5:#4c9a5d;--g2:#cfe8d3;--g1:#eaf5ec;--bg:#f2f8f3;--ink:#1d2a20;--mute:#5f7064;--warn:#e07a1f;--warnbg:#fff1e3;--line:#dbe9dd}
*{box-sizing:border-box}
body{margin:0;font-family:"Noto Sans TC",system-ui,sans-serif;color:var(--ink);background:var(--bg);
 background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);background-size:28px 28px}
.hero{background:linear-gradient(135deg,var(--g9),var(--g7));color:#fff;padding:28px 16px 64px;text-align:center;position:relative;overflow:hidden}
.hero:after{content:"";position:absolute;inset:auto -10% -40px;height:80px;background:var(--bg);border-radius:50% 50% 0 0}
.hero h1{margin:0;font-size:clamp(28px,6vw,40px);font-weight:900;letter-spacing:2px}
.hero h1 span{display:inline-block;transform:translateY(2px);margin-right:6px}
.hero p{margin:8px 0 0;opacity:.85;font-size:15px}
.wrap{max-width:680px;margin:-36px auto 0;padding:0 16px 40px;position:relative;z-index:1}
.steps{display:flex;justify-content:space-between;background:#fff;border-radius:16px;padding:14px 10px;box-shadow:0 6px 20px #1f513014;margin-bottom:16px;position:relative}
.step{flex:1;text-align:center;font-size:12px;color:#9aaa9e;position:relative}
.step i{display:flex;align-items:center;justify-content:center;width:30px;height:30px;margin:0 auto 6px;border-radius:50%;background:#eef2ef;font-style:normal;font-weight:700;position:relative;z-index:1}
.step:not(:last-child):after{content:"";position:absolute;top:15px;left:calc(50% + 18px);right:calc(-50% + 18px);height:3px;border-radius:2px;background:#e3ebe5}
.step.done{color:var(--g7)} .step.done i{background:var(--g2);color:var(--g8)} .step.done:after{background:var(--g5)}
.step.now{color:var(--g8);font-weight:700} .step.now i{background:var(--g7);color:#fff;box-shadow:0 0 0 5px var(--g2)}
.card{background:#fff;border-radius:20px;padding:22px;box-shadow:0 6px 20px #1f513014;margin-bottom:16px}
.card h2{margin:0 0 4px;font-size:20px;color:var(--g8)} .sub{margin:0 0 18px;color:var(--mute);font-size:14px}
.drop{display:block;border:2.5px dashed var(--g5);border-radius:18px;background:var(--g1);padding:34px 16px;text-align:center;cursor:pointer;transition:.2s}
.drop:hover{background:#dff0e2}
.drop .ico{font-size:46px;line-height:1}
.drop b{display:block;margin-top:10px;font-size:17px;color:var(--g8)} .drop small{color:var(--mute)}
.drop img{display:none;max-width:100%;max-height:320px;border-radius:12px}
.drop.has img{margin:0 auto} .drop.has .ph{display:none} .drop.has{padding:12px;border-style:solid}
.drop{position:relative} .drop input[type=file]{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:pointer;font-size:0}
.fname{display:none;margin-top:8px;font-size:14px;color:var(--g8);font-weight:700} .drop.has .fname{display:block}
.btn{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;margin-top:18px;padding:15px;border:0;border-radius:14px;
 background:linear-gradient(135deg,var(--g7),var(--g5));color:#fff;font:700 17px "Noto Sans TC",sans-serif;cursor:pointer;box-shadow:0 6px 16px #2e6b3a40;text-decoration:none}
.btn:disabled{opacity:.5;box-shadow:none;cursor:not-allowed}
.btn.ghost{background:#fff;color:var(--g7);border:2px solid var(--g5);box-shadow:none}
.chips{display:flex;flex-wrap:wrap;gap:8px;min-height:44px}
.chip{display:inline-flex;align-items:center;gap:6px;padding:8px 8px 8px 14px;border-radius:999px;background:var(--g1);border:1.5px solid var(--g2);font-size:15px;cursor:pointer;user-select:none;transition:.15s}
.chip.exp{background:var(--warnbg);border-color:var(--warn);color:#9a4d0b}
.chip.exp:before{content:"⏰"}
.chip button{border:0;background:#0000000f;width:24px;height:24px;border-radius:50%;cursor:pointer;font-size:14px;color:inherit;line-height:1}
.hint{font-size:13px;color:var(--mute);margin:10px 0 0}
.hint em{font-style:normal;color:#9a4d0b;background:var(--warnbg);padding:1px 6px;border-radius:6px}
.add{display:flex;gap:8px;margin-top:14px}
.add input,.field input{flex:1;width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:12px;font:16px "Noto Sans TC",sans-serif;background:#fbfdfb}
.add input:focus,.field input:focus{outline:none;border-color:var(--g5);background:#fff}
.add button{padding:0 18px;border:0;border-radius:12px;background:var(--g2);color:var(--g8);font:700 15px "Noto Sans TC",sans-serif;cursor:pointer}
.field{margin-top:18px} .field label{display:block;font-weight:700;font-size:15px;margin-bottom:8px}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.tags span{font-size:13px;padding:5px 10px;border-radius:999px;background:#f1f4f2;color:var(--mute);cursor:pointer}
.tags span:hover{background:var(--g2);color:var(--g8)}
.intro{background:var(--g1);border-left:5px solid var(--g5);border-radius:12px;padding:14px 16px;margin:0 0 16px;line-height:1.7}
.dish{background:#fff;border-radius:20px;padding:20px 22px;box-shadow:0 6px 20px #1f513014;margin-bottom:16px;line-height:1.75}
.dish h3{margin:0 0 10px;font-size:20px;color:var(--g8);display:flex;gap:10px;align-items:center}
.dish h3:before{content:"🍳";font-size:22px}
.dish ul,.dish ol{padding-left:22px;margin:6px 0} .dish li::marker{color:var(--g5);font-weight:700}
.dish strong{color:var(--g7)}
.dish hr,.recipe>hr{display:none}
.err{background:#fff3f2;border:1.5px solid #f2b8b5;color:#a3261d;border-radius:14px;padding:14px 16px;margin-bottom:16px}
.load{position:fixed;inset:0;background:#173d22e6;display:none;flex-direction:column;align-items:center;justify-content:center;color:#fff;z-index:9;text-align:center;padding:20px}
.load.on{display:flex}
.load .pot{font-size:64px;animation:b 1s ease-in-out infinite}
@keyframes b{50%{transform:translateY(-12px) rotate(-6deg)}}
.load b{font-size:20px;margin-top:14px} .load small{opacity:.75;margin-top:6px}
footer{text-align:center;color:var(--mute);font-size:12px;padding:10px 0 30px}
@media(max-width:480px){.step{font-size:11px}.card,.dish{padding:18px}}
</style></head><body>
<header class="hero">
 <h1><span>🥬</span>AI 冰箱管家</h1>
 <p>讓冰箱裡的剩餘食材，變成下一頓美味。</p>
</header>
<main class="wrap">
{% set n = {'upload':1,'confirm':3,'recipe':5}[step] %}
<nav class="steps">
 {% for s in ['拍照上傳','AI 辨識','確認清單','生成推薦','料理呈現'] %}
 <div class="step {{ 'now' if loop.index==n else ('done' if loop.index<n else '') }}"><i>{{ '✓' if loop.index<n else loop.index }}</i>{{ s }}</div>
 {% endfor %}
</nav>

{% if error %}<div class="err">⚠️ {{ error }}</div>{% endif %}

{% if step == 'upload' %}
<section class="card">
 <h2>📸 拍下你的冰箱</h2>
 <p class="sub">打開冰箱拍一張，AI 會幫你找出有哪些食材。</p>
 <form method="post" action="/recognize" enctype="multipart/form-data" onsubmit="return checkPhoto(this)">
  <label class="drop" id="drop">
   <div class="ph"><div class="ico">📷</div><b>點這裡拍照或選照片</b><small>支援手機相機、相簿圖片</small></div>
   <img id="pv" alt="預覽">
   <div class="fname" id="fname"></div>
   <input type="file" name="photo" id="photo" accept="image/*" onchange="pick(this)" oninput="pick(this)">
  </label>
  <button class="btn" id="go1">✨ AI 辨識食材</button>
 </form>
</section>
{% endif %}

{% if step == 'confirm' %}
<section class="card">
 <h2>🧺 確認食材清單</h2>
 <p class="sub">AI 找到這些食材，認錯的按 ✕ 刪掉，漏掉的自己加。</p>
 <div class="chips" id="chips"></div>
 <p class="hint">💡 點一下食材可標記為 <em>⏰ 即期品</em>，AI 會優先用掉它。</p>
 <div class="add"><input id="newItem" placeholder="新增食材，例如：豆腐" onkeydown="if(event.key==='Enter'){event.preventDefault();addItem()}"><button type="button" onclick="addItem()">＋ 加入</button></div>
 <form method="post" action="/recipe" onsubmit="return submitRecipe(this)">
  <textarea name="items" id="items" hidden>{{ items }}</textarea>
  <input type="hidden" name="expiring" id="expiring">
  <div class="field">
   <label for="pref">🍽️ 口味或需求（可不填）</label>
   <input type="text" name="pref" id="pref" placeholder="例如：不吃辣、15 分鐘內完成">
   <div class="tags">{% for t in ['15 分鐘內','不吃辣','清淡','下飯','一人份','素食'] %}<span onclick="tag('{{t}}')">{{t}}</span>{% endfor %}</div>
  </div>
  <button class="btn">🍳 生成專屬食譜</button>
 </form>
</section>
{% endif %}

{% if step == 'recipe' %}
<div class="recipe" id="recipe">{{ recipe|safe }}</div>
<a href="/" class="btn ghost">📷 再拍一次</a>
{% endif %}
</main>
<footer>AI 冰箱管家 · 剩食食譜智慧推薦系統 · Powered by Gemini</footer>

<div class="load" id="load"><div class="pot">🍲</div><b id="lt">處理中…</b><small id="ls"></small></div>
<script>
function go(f,t,s){document.getElementById('lt').textContent=t;document.getElementById('ls').textContent=s;document.getElementById('load').classList.add('on');var b=f.querySelector('.btn');if(b)b.disabled=true;return true}
window.addEventListener('pageshow',function(){document.getElementById('load').classList.remove('on')});
function pick(i){var f=i.files&&i.files[0];if(!f)return;
 var d=document.getElementById('drop'),p=document.getElementById('pv');
 d.classList.add('has');document.getElementById('fname').textContent='✅ 已選擇：'+f.name;
 p.style.display='block';p.onerror=function(){p.style.display='none'};
 try{p.src=URL.createObjectURL(f)}catch(e){p.style.display='none'}}
function checkPhoto(f){var i=document.getElementById('photo');
 if(!i.files||!i.files[0]){alert('請先拍照或選一張照片');return false}
 return go(f,'AI 正在辨識食材…','大約 10～30 秒')}
var list=[],exp={};
function draw(){var c=document.getElementById('chips');if(!c)return;c.innerHTML='';
 if(!list.length){c.innerHTML='<span class="hint">目前沒有食材，請在下方新增。</span>'}
 list.forEach(function(n,i){var d=document.createElement('span');d.className='chip'+(exp[n]?' exp':'');d.textContent=n;d.title='點一下標記為即期品';
  d.onclick=function(){exp[n]=!exp[n];draw()};
  var x=document.createElement('button');x.type='button';x.textContent='✕';x.title='刪除';x.onclick=function(e){e.stopPropagation();list.splice(i,1);delete exp[n];draw()};
  d.appendChild(x);c.appendChild(d)})}
function addItem(){var i=document.getElementById('newItem');var v=i.value.trim();if(v&&list.indexOf(v)<0){list.push(v);draw()}i.value='';i.focus()}
function tag(t){var p=document.getElementById('pref');p.value=p.value?p.value+'、'+t:t}
function submitRecipe(f){if(!list.length){alert('請至少保留一樣食材');return false}
 document.getElementById('items').value=list.join('\n');
 document.getElementById('expiring').value=list.filter(function(n){return exp[n]}).join(', ');
 return go(f,'AI 正在設計你的食譜…','大約 10～40 秒')}
(function(){var t=document.getElementById('items');if(t){list=t.value.split('\n').map(function(s){return s.trim()}).filter(Boolean);draw()}
 var r=document.getElementById('recipe');if(!r)return;
 var kids=Array.prototype.slice.call(r.childNodes),cur=null,intro=document.createElement('div');intro.className='intro';
 kids.forEach(function(k){if(k.nodeType===1&&/^H[1-3]$/.test(k.tagName)){cur=document.createElement('section');cur.className='dish';r.appendChild(cur);cur.appendChild(k)}
  else if(cur){cur.appendChild(k)}else if(k.nodeType===1||k.textContent.trim()){intro.appendChild(k)}});
 if(intro.textContent.trim())r.insertBefore(intro,r.firstChild);
 r.querySelectorAll('h1,h2').forEach(function(h){var n=document.createElement('h3');n.innerHTML=h.innerHTML;h.replaceWith(n)})})();
</script>
</body></html>
"""


@app.route("/")
def home():
    return render_template_string(PAGE, step="upload")


@app.route("/recognize", methods=["POST"])
def recognize():
    # STEP 2：AI 辨識
    photo = request.files["photo"]
    # 手機照片很大，先縮小到長邊 800 像素，加快上傳 AI 的速度、也比較省記憶體
    raw = photo.read()
    mime = "image/jpeg"
    try:
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
        img.thumbnail((800, 800))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        image_bytes = buf.getvalue()
    except Exception as e:
        # 縮圖失敗就用原始檔案（Gemini 本身支援 HEIC 等格式）
        print(f"[照片] 無法縮圖，改傳原檔：{photo.mimetype} {e}", flush=True)
        image_bytes, mime = raw, (photo.mimetype or "image/jpeg")
    if not image_bytes:
        return render_template_string(PAGE, step="upload", error="沒有收到照片，請重新選擇一次。")
    print(f"[照片] 收到 {photo.filename} 原始 {len(raw) // 1024} KB → 送出 {len(image_bytes) // 1024} KB", flush=True)
    prompt = (
        "請辨識這張冰箱照片裡看得到的食材。"
        "只列出照片中清楚看得到的東西，不確定的不要列。"
        '用 JSON 回答，格式：{"items": ["食材1", "食材2"]}，食材名稱用繁體中文。'
    )
    try:
        resp = call_ai(
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime),
                prompt,
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        items = json.loads(resp.text).get("items", [])
        print(f"[辨識] 食材={items}", flush=True)
    except Exception as e:
        print(f"[辨識失敗] {e}", flush=True)
        return render_template_string(PAGE, step="upload", error="辨識失敗：" + friendly(e))
    return render_template_string(PAGE, step="confirm", items="\n".join(items))


@app.route("/recipe", methods=["POST"])
def recipe():
    # STEP 4：生成食譜（限制只能用清單內食材 → 防止 AI 幻覺）
    items = [x.strip() for x in request.form["items"].splitlines() if x.strip()]
    expiring = request.form.get("expiring", "").strip()
    pref = request.form.get("pref", "").strip()

    prompt = f"""你是家常料理助手。使用者冰箱裡有：{', '.join(items)}。
規則：
1. 只能使用上面清單裡的食材。鹽、糖、醬油、油、水這類基本調味料可以使用，其他不在清單的食材一律不能出現。
2. {'優先使用這些快過期的食材：' + expiring if expiring else '盡量用掉越多種食材越好。'}
3. {'使用者需求：' + pref if pref else '做法簡單，適合下班後料理。'}
請用繁體中文推薦 2 道料理，每道包含：料理名稱、預估時間、所需食材與份量、步驟（編號）。"""
    print(f"[生成食譜] 食材={items} 即期品={expiring} 需求={pref}", flush=True)
    try:
        resp = call_ai(contents=prompt)
        text = resp.text
        print(f"[生成完成] 共 {len(text)} 字", flush=True)
    except Exception as e:
        text = "生成失敗：" + friendly(e)
        print(f"[生成失敗] {e}", flush=True)
    # AI 回的是 Markdown（### 標題、**粗體**），轉成網頁格式；先跳脫 HTML 避免被插入惡意內容
    recipe_html = markdown.markdown(html.escape(text), extensions=["sane_lists"])
    return render_template_string(PAGE, step="recipe", recipe=recipe_html)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
