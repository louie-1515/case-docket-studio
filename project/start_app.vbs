Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

appDir = FSO.GetParentFolderName(WScript.ScriptFullName)
launcherPath = FSO.BuildPath(appDir, "launcher.py")

WshShell.CurrentDirectory = appDir
WshShell.Run "pyw -3 """ & launcherPath & """", 0, False

Set FSO = Nothing
Set WshShell = Nothing
