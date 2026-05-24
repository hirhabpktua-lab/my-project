from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
import json
import os
import re
import base64
import io

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

# Check if OCR libraries are available (local dev) or not (cloud deploy)
try:
    from PIL import Image
    import numpy as np
    import easyocr
    _ocr_reader = None
    def get_ocr_reader():
        global _ocr_reader
        if _ocr_reader is None:
            _ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
        return _ocr_reader
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

VALID_CODES = {
    "TRY-FREE-2026",
    "RC-1425XQ1O","RC-3QB21B1U","RC-41ZEJQJU","RC-45SOTGH5","RC-4B45A133",
    "RC-5VI7B3SC","RC-6UTXTRHW","RC-7MBG33MH","RC-7VW17W5Y","RC-8QSV7KPV",
    "RC-9D237MNJ","RC-9NQE9FW5","RC-B2LDF8JO","RC-CB33EX1O","RC-CHF5OQPP",
    "RC-CLYE38L2","RC-DEFW6UTA","RC-DTKNAJ1R","RC-ED38GG7F","RC-EJ9UJV76",
    "RC-F2OPWDFL","RC-GAKHVF0X","RC-GONZ8L9P","RC-GYQM7MU0","RC-H0DZ2OSQ",
    "RC-H32QUCY9","RC-IL2KZCGP","RC-IT77JRC4","RC-J46ZUIG7","RC-JJ46PKUL",
    "RC-JUFU370E","RC-KE7OKFMZ","RC-KI4ZI68N","RC-KV52WEDO","RC-LFFOHL92",
    "RC-MBTNUGKZ","RC-MYMRMKGV","RC-NF4BJ8ZY","RC-O63O5NNA","RC-O9ZK0C48",
    "RC-OD526DUZ","RC-PG8Q7G92","RC-RLR3D7NJ","RC-SPYLXAGT","RC-TWMM6RYG",
    "RC-UY2I9F9W","RC-V3VVJGOU","RC-VCPTTJNV","RC-ZM9F047H","RC-ZZ9KEU0U",
}

@app.route("/api/verify-code", methods=["POST"])
def verify_code():
    data = request.get_json()
    code = data.get("code", "").strip().upper()
    if code in VALID_CODES:
        return jsonify({"valid": True})
    return jsonify({"valid": False, "error": "无效的使用码"})


@app.route("/api/check", methods=["POST"])
def check_resume():
    data = request.get_json()
    jd = data.get("jd", "").strip()
    resume = data.get("resume", "").strip()

    if not jd or not resume:
        return jsonify({"error": "岗位描述和简历内容都不能为空"}), 400
    if len(jd) < 20:
        return jsonify({"error": "岗位描述太短，请至少输入20个字"}), 400
    if len(resume) < 30:
        return jsonify({"error": "简历内容太短，请至少输入30个字"}), 400

    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return jsonify({"error": "服务端未配置 API Key，请联系管理员"}), 500

    # Try Singapore node first (works globally), fall back to default
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = f"""你是一个专业的ATS简历筛选系统。请分析以下岗位描述和简历的匹配度。

## 岗位描述：
{jd}

## 简历内容：
{resume}

请输出严格的JSON格式（不要包含其他文字）：
{{
  "matched": ["关键词1", "关键词2", ...],
  "missing": ["缺失关键词1", "缺失关键词2", ...],
  "score": 75,
  "suggestions": ["建议1：补充XX相关经验描述", "建议2：...", "建议3：..."],
  "optimized": "优化后的完整简历文本..."
}}

要求：
- matched: 简历中已经体现的关键词/技能/经验（至少3个）
- missing: 岗位描述中要求但简历中没有或不够突出的关键词（至少3个）
- score: 0-100的匹配度评分
- suggestions: 3-5条具体的修改建议
- optimized: 在原文基础上融入缺失关键词，优化措辞使其更匹配岗位要求。直接输出改写后的完整简历，让用户可以直接使用。
- 请用中文输出，关键词保留中英文混合"""

    try:
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            max_tokens=1024,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content or ""

        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            result = json.loads(json_match.group())
            return jsonify(result)
        else:
            return jsonify({"error": "AI 解析失败，请重试"}), 500
    except Exception as e:
        return jsonify({"error": f"AI 调用失败: {str(e)}"}), 500


@app.route("/api/check-photo", methods=["POST"])
def check_photo():
    data = request.get_json()
    jd_image = data.get("jd_image", "").strip()      # base64 (no data: prefix needed)
    resume_image = data.get("resume_image", "").strip()

    if not jd_image or not resume_image:
        return jsonify({"error": "请同时上传岗位描述照片和简历照片"}), 400

    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return jsonify({"error": "服务端未配置 API Key"}), 500

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)

    def extract_text_ocr(image_b64, label):
        if not HAS_OCR:
            raise Exception("拍照模式仅支持本地版（双击start.bat启动），线上请使用下方✏️粘贴文字模式。")
        img_data = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_data))
        if max(img.size) > 2000:
            ratio = 2000 / max(img.size)
            img = img.resize((int(img.size[0]*ratio), int(img.size[1]*ratio)))
        img_array = np.array(img)
        reader = get_ocr_reader()
        results = reader.readtext(img_array, detail=0)
        text = "\n".join(results).strip()
        if not text:
            raise Exception(f"未能从{label}中识别到文字，请确保图片清晰")
        return text

    try:
        jd_text = extract_text_ocr(jd_image, "岗位描述")
        resume_text = extract_text_ocr(resume_image, "简历")

        if not jd_text or not resume_text:
            return jsonify({"error": "图片中未识别到文字，请确保图片清晰"}), 400

        # Run the standard ATS analysis with extracted text
        analysis_prompt = f"""你是一个专业的ATS简历筛选系统。请分析以下岗位描述和简历的匹配度。

## 岗位描述：
{jd_text}

## 简历内容：
{resume_text}

请输出严格的JSON格式（不要包含其他文字）：
{{
  "matched": ["关键词1", "关键词2", ...],
  "missing": ["缺失关键词1", "缺失关键词2", ...],
  "score": 75,
  "suggestions": ["建议1：补充XX相关经验描述", "建议2：...", "建议3：..."],
  "optimized": "优化后的完整简历文本..."
}}

要求：
- matched: 简历中已经体现的关键词/技能/经验（至少3个）
- missing: 岗位描述中要求但简历中没有或不够突出的关键词（至少3个）
- score: 0-100的匹配度评分
- suggestions: 3-5条具体的修改建议
- optimized: 在原文基础上融入缺失关键词，优化措辞使其更匹配岗位要求。直接输出改写后的完整简历，让用户可以直接使用。
- 请用中文输出，关键词保留中英文混合"""

        resp = client.chat.completions.create(
            model="deepseek-v4-pro",
            max_tokens=1024,
            temperature=0.3,
            messages=[{"role": "user", "content": analysis_prompt}],
        )
        content = resp.choices[0].message.content or ""
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            result = json.loads(json_match.group())
            # Include extracted texts so frontend can show them
            result["jd_text"] = jd_text
            result["resume_text"] = resume_text
            return jsonify(result)
        else:
            return jsonify({"error": "AI 分析失败"}), 500

    except Exception as e:
        return jsonify({"error": f"AI 调用失败: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
