"""
Nanofiber Heater Current to Temperature Converter
ヒーター電流 (A) と 加熱温度 (°C) の相互換算モジュール

キャリブレーション参照点:
  5.00 A -> 1115 °C
  5.50 A -> 1260 °C
  6.00 A -> 1400 °C
  6.53 A -> 1530 °C
  6.61 A -> 1550 °C
"""

from typing import List, Tuple, Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# グラフから抽出された標準キャリブレーション点 (電流 A, 温度 °C)
CALIBRATION_POINTS: List[Tuple[float, float]] = [
    (5.00, 1115.0),
    (5.50, 1260.0),
    (6.00, 1400.0),
    (6.53, 1530.0),
    (6.61, 1550.0)
]

CURRENT_VALS = np.array([p[0] for p in CALIBRATION_POINTS])
TEMP_VALS = np.array([p[1] for p in CALIBRATION_POINTS])

# 区間ごとの傾き (℃/A)
SLOPE_LOW = (TEMP_VALS[1] - TEMP_VALS[0]) / (CURRENT_VALS[1] - CURRENT_VALS[0])    # (1260 - 1115) / 0.5 = 290.0
SLOPE_HIGH = (TEMP_VALS[-1] - TEMP_VALS[-2]) / (CURRENT_VALS[-1] - CURRENT_VALS[-2]) # (1550 - 1530) / 0.08 = 250.0

# 2次多項式近似係数 (T = a*I^2 + b*I + c)
_POLY2_COEFFS = np.polyfit(CURRENT_VALS, TEMP_VALS, 2)


def convert_current_to_temperature(current_A: float, mode: str = "linear", round_digits: int = 1) -> Optional[float]:
    """
    ヒーター電流 (A) から加熱温度 (°C) を自動換算する。

    Parameters:
        current_A (float): ヒーター電流 (A)
        mode (str): "linear" (区分線形補間・推奨) または "polynomial" (2次多項式近似)
        round_digits (int): 丸め桁数 (0: 整数℃, 1: 小数第1位)

    Returns:
        float: 換算された温度 (°C)。入力が無効な場合は None。
    """
    if current_A is None:
        return None
    try:
        val = float(current_A)
    except (ValueError, TypeError):
        return None

    if val <= 0:
        return 0.0

    if mode == "polynomial":
        t = float(np.polyval(_POLY2_COEFFS, val))
    else:
        # 区分線形補間 (範囲外は端点の傾きで外挿)
        if val < CURRENT_VALS[0]:
            t = float(TEMP_VALS[0] + (val - CURRENT_VALS[0]) * SLOPE_LOW)
        elif val > CURRENT_VALS[-1]:
            t = float(TEMP_VALS[-1] + (val - CURRENT_VALS[-1]) * SLOPE_HIGH)
        else:
            t = float(np.interp(val, CURRENT_VALS, TEMP_VALS))

    t = max(0.0, t)
    return round(t, round_digits) if round_digits > 0 else round(t)


def convert_temperature_to_current(temperature_C: float, mode: str = "linear", round_digits: int = 3) -> Optional[float]:
    """
    加熱温度 (°C) から必要なヒーター電流 (A) を逆算する。

    Parameters:
        temperature_C (float): 加熱温度 (°C)
        mode (str): "linear" (区分線形補間・推奨)
        round_digits (int): 丸め桁数

    Returns:
        float: 換算された電流 (A)。入力が無効な場合は None。
    """
    if temperature_C is None:
        return None
    try:
        t = float(temperature_C)
    except (ValueError, TypeError):
        return None

    if t <= 0:
        return 0.0

    if t < TEMP_VALS[0]:
        curr = float(CURRENT_VALS[0] + (t - TEMP_VALS[0]) / SLOPE_LOW)
    elif t > TEMP_VALS[-1]:
        curr = float(CURRENT_VALS[-1] + (t - TEMP_VALS[-1]) / SLOPE_HIGH)
    else:
        curr = float(np.interp(t, TEMP_VALS, CURRENT_VALS))

    curr = max(0.0, curr)
    return round(curr, round_digits) if round_digits > 0 else round(curr)


def get_calibration_dataframe() -> pd.DataFrame:
    """キャリブレーション参照点のデータフレームを取得"""
    data = []
    for i, (curr, temp) in enumerate(CALIBRATION_POINTS, 1):
        data.append({
            "No.": i,
            "ヒーター電流 (A)": f"{curr:.2f} A",
            "換算温度 (°C)": f"{temp:.0f} °C",
        })
    return pd.DataFrame(data)


def create_calibration_chart(highlight_current: Optional[float] = None) -> go.Figure:
    """
    電流-温度換算の Plotly グラフを作成する。
    指定された電流値がある場合、換算結果をハイライト表示する。
    """
    # 曲線描画用データ (4.5A 〜 7.0A)
    x_curve = np.linspace(4.5, 7.0, 100)
    y_curve = [convert_current_to_temperature(x) for x in x_curve]

    fig = go.Figure()

    # 換算曲線
    fig.add_trace(go.Scatter(
        x=x_curve,
        y=y_curve,
        mode="lines",
        name="電流-温度 換算曲線",
        line=dict(color="#38bdf8", width=3)
    ))

    # 実測キャリブレーション点
    fig.add_trace(go.Scatter(
        x=CURRENT_VALS,
        y=TEMP_VALS,
        mode="markers+text",
        name="校正基準点 (5点)",
        text=[f"{t:.0f}°C" for t in TEMP_VALS],
        textposition="top left",
        textfont=dict(color="#f1f5f9", size=10),
        marker=dict(size=9, color="#fbbf24", symbol="circle", line=dict(color="#0f172a", width=1.5))
    ))

    # ハイライト点
    if highlight_current is not None and highlight_current > 0:
        hl_temp = convert_current_to_temperature(highlight_current)
        fig.add_trace(go.Scatter(
            x=[highlight_current],
            y=[hl_temp],
            mode="markers+text",
            name=f"現在値: {highlight_current:.3f}A -> {hl_temp:.1f}°C",
            text=[f"入力: {highlight_current:.3f}A<br>換算: {hl_temp:.1f}°C"],
            textposition="bottom right",
            textfont=dict(color="#34d399", size=11),
            marker=dict(size=13, color="#34d399", symbol="diamond", line=dict(color="#ffffff", width=2))
        ))

    fig.update_layout(
        title="ヒーター電流 - 加熱温度 換算特性 (Current vs Temperature)",
        xaxis=dict(title="ヒーター電流 Current (A)", range=[4.5, 7.0], gridcolor="#232d3f", zerolinecolor="#232d3f"),
        yaxis=dict(title="加熱温度 Temperature (°C)", range=[1000, 1650], gridcolor="#232d3f", zerolinecolor="#232d3f"),
        template="plotly_dark",
        paper_bgcolor="#141a24",
        plot_bgcolor="#18202d",
        font=dict(color="#f1f5f9"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=45, r=30, t=50, b=40),
        height=320
    )

    return fig
