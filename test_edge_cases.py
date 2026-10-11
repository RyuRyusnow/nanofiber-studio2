import os
import io
import pandas as pd
import numpy as np
from PIL import Image

import database as db
import transmittance_analyzer as analyzer
import vision_extractor as vision
import folder_watcher as watcher

def test_edge_cases():
    print("--- 1. Testing Single Column CSV ---")
    single_col_csv = "Transmittance\n5.0\n4.8\n4.5\n4.0\n"
    df, err = analyzer.parse_transmittance_csv(single_col_csv.encode('utf-8'))
    print("DEBUG: df columns:", list(df.columns), "err:", err, "dtypes:", df.dtypes)
    assert err is None
    assert "Time(step)" in df.columns
    print("Single col CSV OK, columns:", list(df.columns))

    print("--- 2. Testing CSV with Comments & Non-numeric Rows ---")
    comment_csv = "# Header 1\n# Header 2\nTime,Power\n0.0,1.2\n1.0,1.1\n2.0,1.0\n"
    df, err = analyzer.parse_transmittance_csv(comment_csv.encode('utf-8'))
    assert err is None
    assert len(df) == 3
    print("Comment CSV OK, shape:", df.shape)

    print("--- 3. Testing Normalization with Zero/Negative Baseline ---")
    df_zero = pd.DataFrame({"t": [0, 1, 2], "v": [0.0, 1.0, 2.0]})
    df_norm, stats = analyzer.calculate_normalized_transmittance(df_zero, "t", "v")
    assert not np.isnan(stats["final_pct"])
    assert not np.isinf(stats["final_pct"])
    print("Zero baseline OK, stats:", stats)

    print("--- 4. Testing Plot with Incomplete / Malformed Conditions ---")
    bad_conditions = [
        {"step": 1, "current_A": None, "speed_ums": "invalid", "start_time_s": 0.0, "stop_time_s": 10.0},
        {"step": 2, "current_A": 5.9, "speed_ums": 200, "start_time_s": 15.0, "stop_time_s": 10.0}, # stop < start
        {"step": 3, "current_A": 6.0, "speed_ums": 0, "start_time_s": "bad", "stop_time_s": "bad"},
    ]
    fig = analyzer.create_transmittance_plot(df_norm, "t", conditions=bad_conditions)
    assert fig is not None
    print("Plot with malformed conditions OK!")

    print("--- 5. Testing Database Record without CSV and with NaN/Inf ---")
    rec_id = db.save_record(
        sample_id="NF-TEST-NOCSV",
        params=bad_conditions,
        photo_path="",
        csv_path="",
        csv_data=None,
        initial_val=float('nan'),
        final_pct=float('inf'),
        min_pct=None,
        notes="Edge case test"
    )
    rec = db.get_record_by_id(rec_id)
    assert rec is not None
    assert rec["initial_val"] is None
    print("DB record without CSV & NaN/Inf OK, record:", rec["sample_id"])

    print("--- 6. Testing Image Preparation with RGBA PNG ---")
    rgba_img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
    buf = io.BytesIO()
    rgba_img.save(buf, format="PNG")
    prepared_bytes = vision.prepare_image_bytes(buf.getvalue())
    assert len(prepared_bytes) > 0
    print("RGBA image conversion OK, size:", len(prepared_bytes))

    print("--- 7. Testing Folder Watcher Path Cleaning ---")
    cleaned = watcher.clean_path('  "G:\\マイドライブ\\parameter photo"  ')
    assert cleaned == r"G:\マイドライブ\parameter photo"
    print("Folder watcher path clean OK:", cleaned)

    print("\n[OK] ALL 7 EDGE-CASE TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_edge_cases()
