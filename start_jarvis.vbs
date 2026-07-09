Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\dev\pessoal\JARVIS"
WshShell.Run "C:\dev\pessoal\JARVIS\.venv\Scripts\pythonw.exe -m uvicorn jarvis.server:app --host 127.0.0.1 --port 8787", 0, False
WScript.Sleep 6000
WshShell.Run "C:\dev\pessoal\JARVIS\.venv\Scripts\pythonw.exe voice_run.py", 0, False
