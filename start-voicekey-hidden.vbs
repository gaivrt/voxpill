' 无窗口启动 VoxPill（开机自启用，看不到日志）。
' 把本文件的快捷方式丢进 shell:startup 即可登录自启。
Dim fso, sh
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run "start-voicekey.bat", 0, False
