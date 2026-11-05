/* DCRC's own Unicode portable launcher. Python and Qt remain separate files. */
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <wchar.h>
#include <stdlib.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR args, int show)
{
    wchar_t *root = calloc(32768, sizeof(wchar_t));
    wchar_t *python = calloc(32768, sizeof(wchar_t));
    wchar_t *command = calloc(32768, sizeof(wchar_t));
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    int result = 1;
    DWORD n;
    (void)instance; (void)previous; (void)args; (void)show;
    if (!root || !python || !command) goto done;
    n = GetModuleFileNameW(NULL, root, 32768);
    if (!n || n >= 32768) goto done;
    wchar_t *slash = wcsrchr(root, L'\\');
    if (!slash) goto done;
    *slash = 0;
    if (wcslen(root) > 15000) goto done;
    _snwprintf(python, 32768, L"%ls\\python\\pythonw.exe", root);
    _snwprintf(command, 32768, L"\"%ls\" -B \"%ls\\app\\gui\\run_gui.py\"", python, root);
    startup.cb = sizeof(startup);
    if (!CreateProcessW(python, command, NULL, NULL, FALSE, 0, NULL, root, &startup, &process)) {
        MessageBoxW(NULL, L"Cannot start the bundled Python. Keep python, app and toolchain together.",
                    L"DCRC Converter", MB_ICONERROR);
        goto done;
    }
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    result = 0;
done:
    free(root); free(python); free(command);
    return result;
}
