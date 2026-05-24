from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
import json
import os
import re

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

# Simple activation codes for MVP — replace with more codes before selling
VALID_CODES = {
    "TRY-FREE-2026",
    "RESUME-CHECK-001",
    "RESUME-CHECK-002",
    "RESUME-CHECK-003",
    "RESUME-CHECK-004",
    "RESUME-CHECK-005",
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

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "服务端未配置 API Key，请联系管理员"}), 500

    client = anthropic.Anthropic(api_key=api_key)

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
  "suggestions": ["建议1：补充XX相关经验描述", "建议2：...", "建议3：..."]
}}

要求：
- matched: 简历中已经体现的关键词/技能/经验（至少3个）
- missing: 岗位描述中要求但简历中没有或不够突出的关键词（至少3个）
- score: 0-100的匹配度评分
- suggestions: 3-5条具体的修改建议，每条建议要具体到"补什么词、怎么写"
- 请用中文输出，关键词保留中英文混合"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        # Claude 4 models may return ThinkingBlock before TextBlock — grab the TextBlock
        text_blocks = [b for b in response.content if b.type == "text"]
        if not text_blocks:
            return jsonify({"error": "AI 未返回有效文本，请重试"}), 500
        content = text_blocks[0].text

        # Extract JSON from response (handle case where Claude wraps in ```json)
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            result = json.loads(json_match.group())
            return jsonify(result)
        else:
            return jsonify({"error": "AI 解析失败，请重试"}), 500
    except Exception as e:
        return jsonify({"error": f"AI 调用失败: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
