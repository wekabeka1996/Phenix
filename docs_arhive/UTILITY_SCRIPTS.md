# Utility Scripts

## Kill Python Processes

During development and testing, you may need to kill all running Python processes to clean up the system.

### Windows Batch Script
```cmd
kill_python.bat
```

### PowerShell Script
```powershell
.\kill_python.ps1
```

Both scripts will:
- Find all running `python.exe` and `pythonw.exe` processes
- Terminate them forcefully
- Report success/failure for each process

### Usage Examples

**From Command Prompt:**
```cmd
cd C:\Users\user\Music\Phenix
kill_python.bat
```

**From PowerShell:**
```powershell
cd C:\Users\user\Music\Phenix
.\kill_python.ps1
```

### When to Use

- After Aurora crashes or hangs
- Before starting a new test run
- When multiple Python processes are consuming resources
- During development to ensure clean state

### Safety Note

These scripts will kill ALL Python processes on the system, including:
- Other Python applications you may be running
- IDEs, editors, or tools that use Python
- Background services

Use with caution and ensure no important work will be lost.
