import shutil
import os

src = r"C:\Users\ryugo.DESKTOP-KGQTT11\.gemini\antigravity\brain\fb1e1fea-24c0-4114-9119-4edc4a4b8571\.user_uploaded\media_1791373325709.jpg"
dst_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data")
os.makedirs(dst_dir, exist_ok=True)
dst = os.path.join(dst_dir, "sample_condition.jpg")

if os.path.exists(src):
    shutil.copy2(src, dst)
    print(f"Copied {src} to {dst}")
else:
    print(f"Source file not found: {src}")
