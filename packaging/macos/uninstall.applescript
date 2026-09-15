set dialogResult to display dialog "请选择卸载方式：" & return & return & "保留数据卸载：保留账号、模型、历史记录、上传文件和已安装的 Skills。" & return & "彻底卸载：删除程序及全部数据，重新安装后从全新状态开始。" with title "卸载企业 AI 智能体" buttons {"取消", "保留数据卸载", "彻底卸载"} default button "保留数据卸载" cancel button "取消" with icon caution
set uninstallMode to button returned of dialogResult

if uninstallMode is "彻底卸载" then
	set confirmResult to display dialog "彻底卸载将永久删除账号、模型配置、历史记录、上传文件和所有 Skills。此操作无法撤销。" with title "确认彻底卸载" buttons {"取消", "确认彻底卸载"} default button "取消" cancel button "取消" with icon stop
	if button returned of confirmResult is not "确认彻底卸载" then return
end if

set consoleUser to short user name of (system info)
set userHome to POSIX path of (path to home folder)
set userId to do shell script "/usr/bin/id -u " & quoted form of consoleUser
set serviceTarget to "gui/" & userId & "/com.czon.agent"
set launchAgentPath to userHome & "Library/LaunchAgents/com.czon.agent.plist"

set shellCommand to "/bin/launchctl bootout " & quoted form of serviceTarget & " >/dev/null 2>&1 || true; " & ¬
	"/bin/rm -f " & quoted form of launchAgentPath & "; "

if uninstallMode is "彻底卸载" then
	set shellCommand to shellCommand & "/bin/rm -rf '/Applications/czon_agent'; "
else
	set shellCommand to shellCommand & "if [ -d '/Applications/czon_agent' ]; then /usr/bin/find '/Applications/czon_agent' -mindepth 1 -maxdepth 1 ! -name 'data' ! -name 'uploads' ! -name 'workspace' ! -name 'skills' ! -name '.env' -exec /bin/rm -rf {} +; fi; "
end if

set shellCommand to shellCommand & ¬
	"/bin/rm -rf '/Applications/企业 AI 智能体.app'; " & ¬
	"/usr/sbin/pkgutil --forget com.czon.agent >/dev/null 2>&1 || true; " & ¬
	"/bin/rm -rf '/Applications/卸载企业 AI 智能体.app'"

try
	do shell script shellCommand with administrator privileges
	display dialog "卸载完成。现在可以关闭此窗口，或双击新版安装包重新安装。" with title "企业 AI 智能体" buttons {"完成"} default button "完成" with icon note
on error errorMessage number errorNumber
	if errorNumber is -128 then return
	display alert "卸载失败" message errorMessage as critical
end try
