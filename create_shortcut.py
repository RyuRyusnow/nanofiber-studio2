# -*- coding: utf-8 -*-
import os

desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
target_dir = os.path.dirname(os.path.abspath(__file__))
target_bat = os.path.join(target_dir, "run_app.bat")

# 1. 過去の壊れたショートカットを削除
for fname in os.listdir(desktop):
    if fname.endswith(".lnk"):
        fpath = os.path.join(desktop, fname)
        try:
            with open(fpath, "rb") as fl:
                data = fl.read()
                if b"nanofiber" in data.lower() or b"run_app" in data.lower():
                    os.remove(fpath)
                    print(f"Removed old shortcut: {fname}")
        except Exception:
            pass

# 2. UTF-16LE で VBScript を生成・実行（日本語ファイル名を文字化けなく確実に作成）
vbs_content = f'''Set ws = CreateObject("WScript.Shell")

Set s1 = ws.CreateShortcut("{desktop}\\ナノ光ファイバ管理.lnk")
s1.TargetPath = "{target_bat}"
s1.WorkingDirectory = "{target_dir}"
s1.Description = "ナノ光ファイバ作製マネージャー"
s1.Save

Set s2 = ws.CreateShortcut("{desktop}\\Nanofiber_Manager.lnk")
s2.TargetPath = "{target_bat}"
s2.WorkingDirectory = "{target_dir}"
s2.Description = "Nanofiber Studio Manager"
s2.Save
'''

vbs_path = os.path.join(target_dir, "_temp_shortcut.vbs")
with open(vbs_path, "w", encoding="utf-16") as f:
    f.write(vbs_content)

os.system(f'cscript //nologo "{vbs_path}"')
if os.path.exists(vbs_path):
    os.remove(vbs_path)

print("Shortcuts created on Desktop: ナノ光ファイバ管理.lnk & Nanofiber_Manager.lnk")
