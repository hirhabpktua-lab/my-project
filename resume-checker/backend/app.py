from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
import json
import os
import re
import base64
import io

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "12000"))
MAX_OCR_IMAGE_SIDE = int(os.environ.get("MAX_OCR_IMAGE_SIDE", "2200"))
_rapid_ocr_engine = None
RESUME_SIGNAL_RE = re.compile(
    r"(姓名|电话|手机|邮箱|微信|求职|意向|岗位|职位|工作|经历|项目|实习|教育|学历|本科|"
    r"硕士|博士|专业|学校|技能|技术|证书|获奖|荣誉|自我评价|个人优势|公司|负责|职责|"
    r"成果|业绩|运营|销售|设计|开发|测试|产品|市场|数据|管理|Python|Java|React|Vue|"
    r"Node|SQL|Excel|PPT|AI|Photoshop|TypeScript|JavaScript|Spring|MySQL)",
    re.IGNORECASE,
)
NOISE_RE = re.compile(
    r"(小说|章节|第[一二三四五六七八九十百千万0-9]+章|聊天记录|朋友圈|评论区|点赞|转发|"
    r"广告|立即购买|付款|支付|订单|激活码|使用码|水印|截图|浏览器|搜索|导航|首页|推荐|"
    r"登录|注册|关注|私信|弹幕|免责声明|copyright|http[s]?://|www\.)",
    re.IGNORECASE,
)


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


def analyze_resume(jd, resume):
    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("服务端未配置 DeepSeek API Key，请联系管理员")

    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)
    jd = compact_text_for_scoring(jd, MAX_TEXT_CHARS // 3)
    resume = compact_text_for_scoring(resume, MAX_TEXT_CHARS)

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
- 请忽略任何与求职无关的内容，只基于工作经历、项目经历、技能、教育、证书、成果等简历信息评分。
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
            return json.loads(json_match.group())
        raise RuntimeError("AI 解析失败，请重试")
    except Exception as e:
        raise RuntimeError(f"AI 调用失败: {str(e)}")


def validate_resume_inputs(jd, resume):
    if not jd or not resume:
        return "岗位描述和简历内容都不能为空"
    if len(jd) < 20:
        return "岗位描述太短，请至少输入20个字"
    if len(resume) < 30:
        return "简历内容太短，请至少输入30个字"
    return None


def normalize_text_lines(text):
    lines = []
    seen = set()
    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        line = re.sub(r"^[\-\*\u2022·•\d\.\)、\s]+", "", line).strip()
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return lines


def is_noise_line(line):
    if len(line) <= 2:
        return True
    if NOISE_RE.search(line) and not RESUME_SIGNAL_RE.search(line):
        return True
    if re.fullmatch(r"[\W_]+", line):
        return True
    return False


def extract_work_resume_for_scoring(resume_text):
    original = (resume_text or "").strip()
    lines = normalize_text_lines(original)
    if not lines:
        return original

    keep = set()
    for idx, line in enumerate(lines):
        if is_noise_line(line):
            continue
        is_contact = re.search(r"(电话|手机|邮箱|微信|@|\d{7,})", line, re.IGNORECASE)
        if is_contact and idx > 25 and not RESUME_SIGNAL_RE.search(line):
            continue
        if RESUME_SIGNAL_RE.search(line):
            for nearby in range(max(0, idx - 1), min(len(lines), idx + 3)):
                if not is_noise_line(lines[nearby]):
                    keep.add(nearby)
        elif len(line) >= 12 and not NOISE_RE.search(line):
            # Conservative fallback for OCR text that lost section titles.
            keep.add(idx)

    cleaned_lines = [lines[idx] for idx in sorted(keep)]
    cleaned = "\n".join(cleaned_lines).strip()

    if len(cleaned) < 30 or (len(cleaned) < len(original) * 0.12 and not RESUME_SIGNAL_RE.search(cleaned)):
        return compact_text_for_scoring(original, MAX_TEXT_CHARS)
    return compact_text_for_scoring(cleaned, MAX_TEXT_CHARS)


def clean_resume_for_scoring(resume_text):
    return extract_work_resume_for_scoring(resume_text)


def analyze_resume_with_cleaning(jd, resume):
    cleaned_resume = clean_resume_for_scoring(resume)
    result = analyze_resume(jd, cleaned_resume)
    result["resume_original_length"] = len(resume or "")
    result["resume_cleaned_length"] = len(cleaned_resume or "")
    return result


@app.route("/api/check", methods=["POST"])
def check_resume():
    data = request.get_json()
    jd = data.get("jd", "").strip()
    resume = data.get("resume", "").strip()

    validation_error = validate_resume_inputs(jd, resume)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    try:
        return jsonify(analyze_resume_with_cleaning(jd, resume))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def guess_image_mime(image_b64):
    try:
        header = base64.b64decode(image_b64[:64], validate=False)
    except Exception:
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"GIF8"):
        return "image/gif"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"RIFF") and b"WEBP" in header[:16]:
        return "image/webp"
    return "image/jpeg"


def image_data_url(image_b64):
    return f"data:{guess_image_mime(image_b64)};base64,{image_b64}"


def normalize_image_list(data, plural_key, single_key):
    images = data.get(plural_key)
    if isinstance(images, list):
        return [str(img).strip() for img in images if str(img).strip()]
    single = str(data.get(single_key, "")).strip()
    return [single] if single else []


def decode_image_b64(image_b64):
    try:
        from PIL import Image, ImageOps
        import numpy as np
    except ImportError:
        raise RuntimeError("服务端未安装 OCR 图片依赖，请检查 Pillow/numpy 是否安装")

    raw = base64.b64decode(image_b64)
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max(img.size) > MAX_OCR_IMAGE_SIDE:
        ratio = MAX_OCR_IMAGE_SIDE / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)))
    return np.array(img)


def get_rapid_ocr_engine():
    global _rapid_ocr_engine
    if _rapid_ocr_engine is None:
        try:
            from rapidocr import RapidOCR
        except ImportError:
            raise RuntimeError("服务端未安装 RapidOCR，请检查 requirements.txt")
        _rapid_ocr_engine = RapidOCR()
    return _rapid_ocr_engine


def extract_rapidocr_text(result):
    txts = getattr(result, "txts", None)
    if txts:
        return "\n".join(str(text).strip() for text in txts if str(text).strip()).strip()

    if isinstance(result, tuple) and result:
        result = result[0]

    lines = []
    if isinstance(result, list):
        for item in result:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                text = item[1]
                if isinstance(text, str) and text.strip():
                    lines.append(text.strip())
    return "\n".join(lines).strip()


def extract_text_from_image_rapidocr(image_b64):
    engine = get_rapid_ocr_engine()
    image = decode_image_b64(image_b64)
    result = engine(image)
    return extract_rapidocr_text(result)


def choose_vision_model(quality):
    if quality == "high":
        return os.environ.get("OPENAI_VISION_MODEL_HIGH", "gpt-4.1")
    return os.environ.get("OPENAI_VISION_MODEL", "gpt-4.1-mini")


def extract_text_from_image(client, image_b64, label, page_num, model):
    response = client.responses.create(
        model=model,
        input=[{
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        f"逐行提取这张{label}第{page_num}张图片中的所有可见文字。"
                        "只输出原文文本；不要解释、不要总结、不要翻译、不要改写、不要只提关键词。"
                        "保留换行、数字、英文缩写、项目符号、表格里的文字。"
                    ),
                },
                {
                    "type": "input_image",
                    "image_url": image_data_url(image_b64),
                    "detail": "high",
                },
            ],
        }],
        max_output_tokens=4000,
    )
    return (getattr(response, "output_text", "") or "").strip()


def extract_texts_with_vision(jd_images, resume_images, quality="standard"):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("服务端未配置 OPENAI_API_KEY，拍照识别暂不可用")

    client = OpenAI(api_key=api_key)
    model = choose_vision_model(quality)

    jd_pages = [
        extract_text_from_image(client, image, "岗位描述", idx + 1, model)
        for idx, image in enumerate(jd_images)
    ]
    resume_pages = [
        extract_text_from_image(client, image, "简历", idx + 1, model)
        for idx, image in enumerate(resume_images)
    ]

    jd_text = "\n\n".join(text for text in jd_pages if text).strip()
    resume_text = "\n\n".join(text for text in resume_pages if text).strip()

    if not jd_text:
        raise RuntimeError("未能从岗位描述图片中识别到文字，请换一张更清晰的图片")
    if not resume_text:
        raise RuntimeError("未能从简历图片中识别到文字，请换一张更清晰的图片")
    return jd_text, resume_text, jd_pages, resume_pages


def extract_texts_with_rapidocr(jd_images, resume_images):
    jd_pages = [extract_text_from_image_rapidocr(image) for image in jd_images]
    resume_pages = [extract_text_from_image_rapidocr(image) for image in resume_images]
    jd_text = "\n\n".join(text for text in jd_pages if text).strip()
    resume_text = "\n\n".join(text for text in resume_pages if text).strip()

    if not jd_text:
        raise RuntimeError("未能从岗位描述图片中识别到文字，请换一张更清晰的图片")
    if not resume_text:
        raise RuntimeError("未能从简历图片中识别到文字，请换一张更清晰的图片")
    return jd_text, resume_text, jd_pages, resume_pages


def compact_text_for_scoring(text, max_chars):
    lines = []
    seen = set()
    for raw_line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        key = line.lower()
        if len(line) < 4 or key in seen:
            continue
        seen.add(key)
        lines.append(line)
    compacted = "\n".join(lines)
    if len(compacted) <= max_chars:
        return compacted
    head = compacted[: int(max_chars * 0.7)]
    tail = compacted[-int(max_chars * 0.3):]
    return f"{head}\n...\n{tail}"


@app.route("/api/ocr-photo", methods=["POST"])
def ocr_photo():
    data = request.get_json()
    jd_images = normalize_image_list(data, "jd_images", "jd_image")
    resume_images = normalize_image_list(data, "resume_images", "resume_image")
    quality = "high" if data.get("quality") == "high" else "standard"

    if not jd_images or not resume_images:
        return jsonify({"error": "请同时上传岗位描述照片和简历照片"}), 400

    try:
        jd_text, resume_text, jd_pages, resume_pages = extract_texts_with_rapidocr(
            jd_images,
            resume_images,
        )
        return jsonify({
            "jd_text": jd_text,
            "resume_text": resume_text,
            "jd_pages": jd_pages,
            "resume_pages": resume_pages,
            "quality": "rapidocr",
        })
    except Exception as e:
        return jsonify({"error": f"拍照识别失败: {str(e)}"}), 500


@app.route("/api/check-photo", methods=["POST"])
def check_photo():
    data = request.get_json()
    jd_images = normalize_image_list(data, "jd_images", "jd_image")
    resume_images = normalize_image_list(data, "resume_images", "resume_image")
    quality = "high" if data.get("quality") == "high" else "standard"

    if not jd_images or not resume_images:
        return jsonify({"error": "请同时上传岗位描述照片和简历照片"}), 400

    try:
        jd_text, resume_text, jd_pages, resume_pages = extract_texts_with_rapidocr(
            jd_images,
            resume_images,
        )

        validation_error = validate_resume_inputs(jd_text, resume_text)
        if validation_error:
            return jsonify({"error": f"{validation_error}，请换一张更清晰的图片或使用文字模式"}), 400

        result = analyze_resume_with_cleaning(jd_text, resume_text)
        result["jd_text"] = jd_text
        result["resume_text"] = resume_text
        result["jd_pages"] = jd_pages
        result["resume_pages"] = resume_pages
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": f"拍照识别失败: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
