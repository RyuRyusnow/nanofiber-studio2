Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)

WshShell.CurrentDirectory = strDir

' Python (py or python) で launcher.py を完全バックグラウンド（黒い画面なし）で実行
intReturn = WshShell.Run("cmd /c py launcher.py", 0, False)
