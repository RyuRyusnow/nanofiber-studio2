import io
import re
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from typing import Dict, Any, List, Optional, Tuple

def parse_transmittance_csv(
    file_input: Any,
    encoding: Optional[str] = None
) -> Tuple[pd.DataFrame, Optional[str]]:
    """
    CSVファイルを堅牢にパースし、DataFrameを返す。
    ヘッダー行、コメント行、タブ・空白区切り、Shift-JIS/UTF-8に全対応。
    """
    encodings = [encoding] if encoding else ["utf-8", "cp932", "shift_jis", "latin1"]
    
    if isinstance(file_input, str):
        with open(file_input, "rb") as f:
            raw_bytes = f.read()
    elif isinstance(file_input, bytes):
        raw_bytes = file_input
    elif hasattr(file_input, "read"):
        raw_bytes = file_input.read()
        if hasattr(file_input, "seek"):
            file_input.seek(0)
    else:
        return pd.DataFrame(), "無効なファイル入力です。"

    df = None
    last_err = None

    standard_seps = [",", "\t", ";", r"\s+"]
    for enc in encodings:
        if not enc or df is not None:
            continue
        for sep in standard_seps:
            try:
                buf = io.BytesIO(raw_bytes)
                df_temp = pd.read_csv(buf, encoding=enc, sep=sep, engine="python", comment="#")
                
                for col in df_temp.columns:
                    converted = pd.to_numeric(df_temp[col], errors="coerce")
                    if converted.notna().sum() > len(df_temp) * 0.4:
                        df_temp[col] = converted

                numeric_cols = df_temp.select_dtypes(include=[np.number]).columns
                if len(numeric_cols) > 0:
                    df = df_temp
                    break
            except Exception as e:
                last_err = str(e)
                continue

    # ヘッダーなし、またはコメント行が多いフォーマットのフォールバック
    if df is None:
        for enc in encodings:
            if not enc or df is not None:
                continue
            for sep in standard_seps:
                try:
                    buf = io.BytesIO(raw_bytes)
                    df_temp = pd.read_csv(buf, encoding=enc, header=None, sep=sep, engine="python", comment="#")
                    for col in df_temp.columns:
                        df_temp[col] = pd.to_numeric(df_temp[col], errors="coerce")
                    numeric_cols = df_temp.select_dtypes(include=[np.number]).columns
                    if len(numeric_cols) > 0:
                        df = df_temp
                        break
                except Exception as e:
                    last_err = str(e)
                    continue

    if df is None:
        return pd.DataFrame(), f"CSVの解析に失敗しました。数値データが見つかりません: {last_err}"

    # もし数値列が1列のみの場合、時間軸（ステップ番号: 0, 1, 2, ...）を自動生成
    numeric_cols = list(df.select_dtypes(include=[np.number]).columns)
    if len(numeric_cols) == 1:
        time_col_name = "Time(step)"
        df.insert(0, time_col_name, np.arange(len(df)))

    return df, None

def calculate_normalized_transmittance(
    df: pd.DataFrame,
    time_col: str,
    val_col: str,
    baseline_mode: str = "first",
    baseline_n_points: int = 5
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    指定された列を用いて、最初の数値を基準(100%)とした正規化透過率を計算する。
    """
    df_clean = df[[time_col, val_col]].dropna().copy()
    df_clean[time_col] = pd.to_numeric(df_clean[time_col], errors="coerce")
    df_clean[val_col] = pd.to_numeric(df_clean[val_col], errors="coerce")
    df_clean = df_clean.dropna().reset_index(drop=True)

    if len(df_clean) == 0:
        raise ValueError("有効な数値データが存在しません。")

    raw_values = df_clean[val_col].values

    # 基準値の決定
    if baseline_mode == "first":
        base_val = raw_values[0]
    elif baseline_mode == "average_first_n":
        n = min(len(raw_values), max(1, baseline_n_points))
        base_val = np.mean(raw_values[:n])
    elif baseline_mode == "max":
        base_val = np.max(raw_values)
    else:
        base_val = raw_values[0]

    # 0 または負数の保護
    if base_val <= 0:
        base_val = 1e-9

    # 100分率（%）計算
    pct_values = (raw_values / base_val) * 100.0
    # nan / inf の除去
    pct_values = np.nan_to_num(pct_values, nan=0.0, posinf=100.0, neginf=0.0)
    df_clean["transmittance_pct"] = pct_values

    # dB換算 (Loss = -10 * log10(T/T0))
    with np.errstate(divide='ignore', invalid='ignore'):
        ratio = np.clip(raw_values / base_val, 1e-12, None)
        loss_db = -10.0 * np.log10(ratio)
        loss_db = np.nan_to_num(loss_db, nan=0.0, posinf=60.0, neginf=0.0)
    df_clean["loss_db"] = loss_db

    initial_val = float(raw_values[0])
    final_pct = float(pct_values[-1])
    min_pct = float(np.min(pct_values))
    max_pct = float(np.max(pct_values))
    final_loss_db = float(loss_db[-1])

    stats = {
        "base_val": float(base_val),
        "initial_val": initial_val,
        "final_pct": final_pct,
        "min_pct": min_pct,
        "max_pct": max_pct,
        "final_loss_db": final_loss_db
    }

    return df_clean, stats

def create_transmittance_plot(
    df_clean: pd.DataFrame,
    time_col: str,
    conditions: Optional[List[Dict[str, Any]]] = None,
    title: str = "ナノ光ファイバ作製時の透過率変化 (100分率表示)",
    show_stages: bool = True
) -> go.Figure:
    """
    Plotlyによるインタラクティブな正規化透過率グラフを作成。
    作製条件（延伸ステージ）のタイムラインを安全に重ねて表示。
    """
    fig = go.Figure()

    if df_clean is None or len(df_clean) == 0:
        fig.update_layout(title="データが存在しません")
        return fig

    times = df_clean[time_col].values
    pct = df_clean["transmittance_pct"].values

    # 透過率曲線の描画（高コントラスト＆シャープなブルー）
    fig.add_trace(go.Scatter(
        x=times,
        y=pct,
        mode="lines",
        name="規格化透過率 T/T₀ (%)",
        line=dict(color="#0284c7", width=2.8),
        hovertemplate="時間 t: %{x:.2f} s<br>規格化透過率: <b>%{y:.2f} %</b><extra></extra>"
    ))

    # 100% 基準線（視認性の高い破線）
    fig.add_hline(
        y=100.0,
        line_dash="dash",
        line_color="#dc2626",
        line_width=1.5,
        annotation_text=" 初期基準透過率 (100%)",
        annotation_position="top right",
        annotation=dict(font=dict(size=11, color="#dc2626", family="sans-serif"))
    )

    # 延伸ステージ（条件）のオーバーレイ
    if show_stages and conditions:
        stage_colors = [
            "rgba(59, 130, 246, 0.08)",  # ブルー
            "rgba(249, 115, 22, 0.10)",  # オレンジ
            "rgba(16, 185, 129, 0.10)",  # グリーン
            "rgba(168, 85, 247, 0.10)",  # パープル
            "rgba(234, 179, 8, 0.10)"    # イエロー
        ]

        for idx, stage in enumerate(conditions):
            try:
                t_start = float(stage.get("start_time_s") if stage.get("start_time_s") is not None else 0.0)
                t_stop = float(stage.get("stop_time_s") if stage.get("stop_time_s") is not None else 0.0)
                curr = float(stage.get("current_A") if stage.get("current_A") is not None else 0.0)
                spd = float(stage.get("speed_ums") if stage.get("speed_ums") is not None else 0.0)
                step_no = stage.get("step", idx + 1)
            except (ValueError, TypeError):
                continue

            if t_stop <= t_start:
                continue

            color = stage_colors[idx % len(stage_colors)]
            label = f"S{step_no}: {curr:.2f}A/{spd:.0f}µm/s"

            fig.add_vrect(
                x0=t_start,
                x1=t_stop,
                fillcolor=color,
                layer="below",
                line_width=1,
                line_color="rgba(148, 163, 184, 0.5)",
                annotation_text=label,
                annotation_position="top left",
                annotation=dict(font=dict(size=11, color="#1e293b", family="sans-serif"))
            )

    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=15, color="#f8fafc")),
        xaxis=dict(
            title=dict(text="<b>時間 t (s)</b>", font=dict(size=12, color="#94a3b8")),
            gridcolor="rgba(255, 255, 255, 0.08)",
            gridwidth=1,
            showgrid=True,
            zeroline=False,
            tickfont=dict(size=11, color="#94a3b8")
        ),
        yaxis=dict(
            title=dict(text="<b>規格化透過率 T / T₀ (%)</b>", font=dict(size=12, color="#94a3b8")),
            gridcolor="rgba(255, 255, 255, 0.08)",
            gridwidth=1,
            showgrid=True,
            zeroline=True,
            zerolinecolor="rgba(255, 255, 255, 0.2)",
            tickfont=dict(size=11, color="#94a3b8")
        ),
        hovermode="x unified",
        plot_bgcolor="#111722",
        paper_bgcolor="#151d2a",
        margin=dict(l=55, r=30, t=50, b=45),
        legend=dict(x=0.02, y=0.98, bgcolor="rgba(21, 29, 42, 0.85)", bordercolor="#334155", borderwidth=1, font=dict(color="#e2e8f0")),
        font=dict(family="sans-serif", color="#e2e8f0")
    )

    return fig

def create_comparison_plot(
    records: List[Dict[str, Any]],
    title: str = "透過率推移の重ね描き比較 (100%基準)"
) -> go.Figure:
    """
    複数サンプルの正規化透過率曲線を1つのグラフに重ねて描画する。
    """
    fig = go.Figure()

    if not records:
        fig.update_layout(title="比較対象データがありません")
        return fig

    palette = [
        "#2563eb", "#ea580c", "#16a34a", "#9333ea",
        "#0891b2", "#e11d48", "#ca8a04", "#4f46e5"
    ]

    has_data = False
    for idx, rec in enumerate(records):
        c_dict = rec.get("csv_data")
        if not c_dict or "time" not in c_dict or "pct" not in c_dict:
            continue
        times = c_dict.get("time", [])
        pcts = c_dict.get("pct", [])
        if not times or not pcts:
            continue

        has_data = True
        color = palette[idx % len(palette)]
        s_id = rec.get("sample_id", f"Record #{rec.get('id')}")
        f_pct = rec.get("final_pct")
        pct_tag = f" ({f_pct:.1f}%)" if f_pct is not None else ""
        label = f"{s_id}{pct_tag}"

        fig.add_trace(go.Scatter(
            x=times,
            y=pcts,
            mode="lines",
            name=label,
            line=dict(color=color, width=2.4),
            hovertemplate=f"<b>{s_id}</b><br>時間 t: %{{x:.2f}} s<br>規格化透過率 T/T₀: <b>%{{y:.2f}} %</b><extra></extra>"
        ))

    if not has_data:
        fig.update_layout(title="有効な透過率データがありません")
        return fig

    # 100% 基準線
    fig.add_hline(
        y=100.0,
        line_dash="dash",
        line_color="#dc2626",
        line_width=1.5,
        annotation_text=" 初期基準透過率 (100%)",
        annotation_position="top right",
        annotation=dict(font=dict(size=11, color="#dc2626", family="sans-serif"))
    )

    fig.update_layout(
        title=dict(text=f"<b>{title}</b>", font=dict(size=15, color="#f8fafc")),
        xaxis=dict(
            title=dict(text="<b>時間 t (s)</b>", font=dict(size=12, color="#94a3b8")),
            gridcolor="rgba(255, 255, 255, 0.08)",
            gridwidth=1,
            showgrid=True,
            zeroline=False,
            tickfont=dict(size=11, color="#94a3b8")
        ),
        yaxis=dict(
            title=dict(text="<b>規格化透過率 T / T₀ (%)</b>", font=dict(size=12, color="#94a3b8")),
            gridcolor="rgba(255, 255, 255, 0.08)",
            gridwidth=1,
            showgrid=True,
            zeroline=True,
            zerolinecolor="rgba(255, 255, 255, 0.2)",
            tickfont=dict(size=11, color="#94a3b8")
        ),
        hovermode="x unified",
        plot_bgcolor="#111722",
        paper_bgcolor="#151d2a",
        margin=dict(l=55, r=30, t=50, b=45),
        legend=dict(x=0.02, y=0.98, bgcolor="rgba(21, 29, 42, 0.85)", bordercolor="#334155", borderwidth=1, font=dict(color="#e2e8f0")),
        font=dict(family="sans-serif", color="#e2e8f0")
    )

    return fig

