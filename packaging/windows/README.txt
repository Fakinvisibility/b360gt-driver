B360GT Windows portable PATH scripts
====================================

The release builder must copy all five files in this directory into the root
of the portable B360GT folder, beside B360GT.exe/b360gt.exe.

Users may double-click:

  添加到命令行PATH.cmd

After opening a new PowerShell window, these commands work from any directory:

  b360gt start
  b360gt status
  b360gt stop

To undo the user PATH change, double-click:

  从命令行PATH移除.cmd

The scripts modify only the current user's PATH. They do not require
administrator privileges and do not copy, install, or delete program files.
