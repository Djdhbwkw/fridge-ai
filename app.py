# AI 冰箱管家 —— 最小可執行版本
# 安裝：pip install flask google-genai
# 執行：python app.py，然後用瀏覽器打開 http://127.0.0.1:5000

import io
import json
import os
import time
from PIL import Image
from flask import Flask, request, render_template_string
from google import genai
from google.genai import types

# 金鑰從環境變數讀取（上線到 Render 時在網站後台設定 GEMINI_API_KEY），不要直接寫在程式裡
API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")   # 可在 Render 環境變數 GEMINI_MODEL 換模型

# 主要模型忙線時改用的備用模型（用逗號分隔，可在 Render 環境變數 GEMINI_FALLBACK 修改）
FALLBACK = [m.strip() for m in os.environ.get("GEMINI_FALLBACK", "gemini-4-hydrogen").split(",") if m.strip()]

client = genai.Client(api_key=API_KEY)


def call_ai(contents, config=None):
    """呼叫 Gemini；遇到 503 忙線或 429 次數上限時自動重試，再換備用模型。"""
    last_err = None
    for model in [MODEL] + FALLBACK:
        for attempt in range(3):
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=config)
                print(f"[AI] 使用模型={model}（第 {attempt + 1} 次嘗試）", flush=True)
                return resp
            except Exception as e:
                last_err = e
                msg = str(e)
                print(f"[AI 重試] 模型={model} 第 {attempt + 1} 次失敗：{msg[:120]}", flush=True)
                if "503" in msg or "UNAVAILABLE" in msg or "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    time.sleep(2 * (attempt + 1))   # 等 2、4、6 秒再試
                    continue
                break   # 其他錯誤（例如模型不存在）直接換下一個模型
    raise last_err


def friendly(e):
    msg = str(e)
    if "503" in msg or "UNAVAILABLE" in msg:
        return "AI 目前使用人數太多，請過 1 分鐘再試一次。"
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "今天的免費使用次數可能用完了，請稍後再試。"
    return f"發生錯誤：{msg[:200]}"
app = Flask(__name__)

PAGE = """
<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 冰箱管家</title>
<style>
 body{font-family:sans-serif;max-width:640px;margin:20px auto;padding:0 16px;background:#f3f8f3}
 h1{color:#2e6b3a} .card{background:#fff;border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 1px 4px #0002}
 button{background:#2e6b3a;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:16px}
 textarea,input[type=text]{width:100%;font-size:16px;padding:6px;box-sizing:border-box}
 pre{white-space:pre-wrap;font-family:inherit}
</style></head><body>
<h1>🥬 AI 冰箱管家</h1>

{% if step == 'upload' %}
<div class="card">
 <p><b>STEP 1：拍照上傳</b></p>
 <form method="post" action="/recognize" enctype="multipart/form-data">
  <input type="file" name="photo" accept="image/*" capture="environment" required><br><br>
  <button>AI 辨識食材</button>
 </form>
</div>
{% endif %}

{% if step == 'confirm' %}
<div class="card">
 <p><b>STEP 3：確認食材清單</b>（可以刪除、修改或新增，一行一個）</p>
 <form method="post" action="/recipe">
  <textarea name="items" rows="8">{{ items }}</textarea>
  <p>即期品（優先用掉，用逗號分隔，可留空）：</p>
  <input type="text" name="expiring" placeholder="例如：豬肉, 豆腐">
  <p>口味或限制（可留空）：</p>
  <input type="text" name="pref" placeholder="例如：不吃辣、15分鐘內">
  <br><br><button>生成食譜</button>
 </form>
</div>
{% endif %}

{% if step == 'recipe' %}
<div class="card"><pre>{{ recipe }}</pre></div>
<a href="/"><button>再拍一次</button></a>
{% endif %}

{% if error %}<div class="card" style="color:#b00">{{ error }}</div>{% endif %}
</body></html>
"""


@app.route("/")
def home():
    return render_template_string(PAGE, step="upload")


@app.route("/recognize", methods=["POST"])
def recognize():
    # STEP 2：AI 辨識
    photo = request.files["photo"]
    # 手機照片很大，先縮小到長邊 1024 像素，加快上傳 AI 的速度、也比較省記憶體
    try:
        img = Image.open(photo.stream)
        img = img.convert("RGB")
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        image_bytes = buf.getvalue()
    except Exception as e:
        return render_template_string(PAGE, step="upload", error=f"照片讀取失敗：{e}")
    prompt = (
        "請辨識這張冰箱照片裡看得到的食材。"
        "只列出照片中清楚看得到的東西，不確定的不要列。"
        '用 JSON 回答，格式：{"items": ["食材1", "食材2"]}，食材名稱用繁體中文。'
    )
    try:
        resp = call_ai(
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        items = json.loads(resp.text).get("items", [])
        print(f"[辨識] 模型={MODEL} 食材={items}", flush=True)
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
    return render_template_string(PAGE, step="recipe", recipe=text)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
