import os
import json
import re
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from PIL import Image
import io

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

class ProcessStep(BaseModel):
    step: int = Field(description="ステップ番号（1から開始）")
    current_A: float = Field(description="延伸電流 (A)")
    speed_ums: float = Field(description="延伸速度 (um/s)")
    start_time_s: float = Field(description="延伸開始時間 (s)")
    stop_time_s: float = Field(description="延伸停止時間 (s)")

class FabricationConditions(BaseModel):
    steps: List[ProcessStep] = Field(description="各ステップの延伸条件リスト")

def safe_float(val: Any, default: float = 0.0) -> float:
    """文字列や単位付きの数値、Noneを安全にfloatへ変換"""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    clean = re.sub(r"[^0-9.-]", "", str(val))
    try:
        return float(clean)
    except (ValueError, TypeError):
        return default

def prepare_image_bytes(image_input: Any) -> bytes:
    """任意の画像入力をRGB形式のJPEGバイト列に変換・最適化"""
    if isinstance(image_input, str):
        img = Image.open(image_input)
    elif isinstance(image_input, bytes):
        img = Image.open(io.BytesIO(image_input))
    elif hasattr(image_input, "read"):
        data = image_input.read()
        if hasattr(image_input, "seek"):
            image_input.seek(0)
        img = Image.open(io.BytesIO(data))
    elif isinstance(image_input, Image.Image):
        img = image_input
    else:
        raise ValueError("サポートされていない画像形式です。")

    img_rgb = img.convert("RGB")

    max_dim = 2048
    if max(img_rgb.size) > max_dim:
        ratio = max_dim / max(img_rgb.size)
        new_size = (int(img_rgb.size[0] * ratio), int(img_rgb.size[1] * ratio))
        img_rgb = img_rgb.resize(new_size, Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img_rgb.save(buf, format="JPEG", quality=92)
    return buf.getvalue()

def extract_conditions_from_image(
    image_input: Any,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    ナノ光ファイバ作製条件の写真からGemini APIを用いて表データを抽出する。
    503混雑時の自動リトライおよび代替モデル（gemini-3.5-flash-lite）へのフォールバックを搭載。
    """
    effective_api_key = api_key or os.environ.get("GEMINI_API_KEY")

    if not effective_api_key:
        return {
            "success": False,
            "data": [],
            "error": "Gemini APIキーが設定されていません。サイドバーの設定画面または環境変数 GEMINI_API_KEY に入力してください。"
        }

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=effective_api_key)
        image_bytes = prepare_image_bytes(image_input)

        prompt = """
あなたはナノ光ファイバ（テーパーファイバ）作製装置の条件設定画面の画像解析の専門家です。
添付された画像から、各行の作製条件（パラメータ表）を正確に読み取り、構造化データとして抽出してください。

表の各列の定義:
- 延伸電流(A): 電流値 (例: 6.000, 5.900)
- 延伸速度(um/s): ステージ延伸速度 (例: 0, 225)
- 延伸開始時間(s): そのステップの開始時刻 (例: 0, 160, 230, 430)
- 延伸停止時間(s): そのステップの終了時刻 (例: 160, 230, 430, 530)

各行を入力ボックスの上から順に読み取り、欠落のないように抽出してください。
画面のモアレや走査線、反射があっても、数字の形状を注意深く判読してください。
"""

        # 混雑時（503 UNAVAILABLE）に備えて優先順モデルリストを用意
        candidate_models = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
        response = None
        used_model = None
        last_error = None

        for model_name in candidate_models:
            for attempt in range(2):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                            prompt
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=FabricationConditions,
                            temperature=0.0
                        )
                    )
                    used_model = model_name
                    break
                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    # 503混雑、あるいはレート制限429の場合は少し待ってリトライまたは次モデルへ
                    if any(code in err_str for code in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"]):
                        time.sleep(1.2 * (attempt + 1))
                        continue
                    else:
                        raise e

            if response is not None:
                break

        if response is None:
            raise last_error or Exception("APIサーバーが高負荷のため応答しませんでした。")

        result_text = response.text
        parsed = json.loads(result_text)
        steps = parsed.get("steps", [])

        formatted_steps = []
        for i, s in enumerate(steps, start=1):
            formatted_steps.append({
                "step": int(safe_float(s.get("step", i), default=i)),
                "current_A": safe_float(s.get("current_A", 0.0)),
                "speed_ums": safe_float(s.get("speed_ums", 0.0)),
                "start_time_s": safe_float(s.get("start_time_s", 0.0)),
                "stop_time_s": safe_float(s.get("stop_time_s", 0.0)),
            })

        return {
            "success": True,
            "data": formatted_steps,
            "model_used": used_model,
            "error": None
        }

    except Exception as e:
        err_str = str(e)
        if "503" in err_str or "UNAVAILABLE" in err_str:
            friendly_msg = "Google AIサーバーが一時的に混雑しています。10〜20秒ほど置いてから再度お試しください。"
        elif "API_KEY_INVALID" in err_str or "400" in err_str and "key" in err_str.lower():
            friendly_msg = "APIキーが無効です。Google AI Studioで取得したキーが正しく入力されているか確認してください。"
        else:
            friendly_msg = f"画像解析中にエラーが発生しました: {err_str}"

        return {
            "success": False,
            "data": [],
            "error": friendly_msg
        }
