import os 
import sys 
import time 
import ctypes 
import tempfile 
import requests 
import webbrowser 
import threading 
from io import BytesIO 

LINKTREE_URL = "https://linktr.ee/werbel"

SCAN_RUNNING = False 
WORKER_THREAD: threading.Thread | None = None 
STOP_EVENT: threading.Event | None = None 

ANSI_GREEN = "\033[92m"
ANSI_RED = "\033[91m"
ANSI_RESET = "\033[0m"

def lock_console(cols: int = 54, rows: int = 8):
    """Ustawia stały rozmiar konsoli i blokuje scrollowanie."""
    if os.name != "nt":
        return 
    try:
        kernel32 = ctypes.windll.kernel32 
        user32 = ctypes.windll.user32 
        h = kernel32.GetStdHandle(-11) 

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [
                ("Left", ctypes.c_short),
                ("Top", ctypes.c_short),
                ("Right", ctypes.c_short),
                ("Bottom", ctypes.c_short),
            ]

        kernel32.SetConsoleScreenBufferSize(h, COORD(cols, rows))
        rect = SMALL_RECT(0, 0, cols - 1, rows - 1)
        kernel32.SetConsoleWindowInfo(h, True, ctypes.byref(rect))
        kernel32.SetConsoleScreenBufferSize(h, COORD(cols, rows))

        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            GWL_STYLE = -16
            WS_MAXIMIZEBOX = 0x00010000
            WS_SIZEBOX = 0x00040000
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style &= ~WS_MAXIMIZEBOX & ~WS_SIZEBOX
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)

    except Exception:
        try:
            os.system(f"mode con: cols={cols} lines={rows}")
        except Exception:
            pass

def enable_ansi_colors_on_windows():
    if os.name != "nt":
        return 
    try:
        kernel32 = ctypes.windll.kernel32 
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            return 
    except Exception:
        pass
    try:
        import colorama
        colorama.just_fix_windows_console()
    except Exception:
        global ANSI_GREEN, ANSI_RED, ANSI_RESET
        ANSI_GREEN = ANSI_RED = ANSI_RESET = ""

def is_user_admin():
    if os.name != "nt":
        return True 
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def run_as_admin_if_needed():
    if os.name != "nt":
        return 
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            params = " ".join(f'"{arg}"' for arg in sys.argv)
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, None, 1
            )
            if rc <= 32:
                print("[BŁĄD] Nie udało się uruchomić jako administrator.")
                sys.exit(1)
            sys.exit(0)
    except Exception as e:
        print("[BŁĄD]", e)
        sys.exit(1)

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def show_loading(duration: float = 3.0):
    total_steps = 30
    interval = duration / total_steps
    print("Ładowanie…\n")
    for i in range(total_steps + 1):
        filled = "█" * i
        empty = " " * (total_steps - i)
        percent = int(i / total_steps * 100)
        print(f"\r[{filled}{empty}] {percent:3d}%", end="", flush=True)
        time.sleep(interval)
    print("\n")

def splash_and_admin(duration = 3.0):
    clear()
    print("=" * 38)
    print("  AutoAccept Bot — Start")
    print("=" * 38)
    if os.name == "nt":
        if not is_user_admin():
            print("Brak uprawnień — próba ponownego uruchomienia jako administrator.")
            run_as_admin_if_needed()
    else:
        print("System inny niż Windows — pomijam sprawdzanie.")
    show_loading(duration)

def download_to_temp(url: str, filename_hint: str) -> str:
    resp = requests.get(url, timeout = 20)
    resp.raise_for_status()
    suffix = os.path.splitext(filename_hint)[1] or ".png"
    fd, tmp_path = tempfile.mkstemp(prefix = "autoaccept_", suffix = suffix)
    os.close(fd)
    with open(tmp_path, "wb") as f:
        f.write(resp.content)
    return tmp_path

def scan_worker(button_url: str, confidence: float, stop_event: threading.Event):
    import pyautogui
    pyautogui.FAILSAFE = True
    try:
        path = download_to_temp(button_url, "accept.png")
    except Exception as e:
        print(f"[BŁĄD] Pobieranie wzorca: {e}")
        return 
    try:
        while not stop_event.is_set():
            try:
                box = pyautogui.locateOnScreen(path, confidence = confidence)
            except Exception:
                time.sleep(1)
                continue
            if box:
                cx, cy = pyautogui.center(box)
                pyautogui.moveTo(cx, cy, duration = 0.05)
                pyautogui.click(cx, cy)
                print("[INFO] Kliknięto przycisk Accept.")
                break
            else:
                time.sleep(1)
    finally:
        if os.path.exists(path):
            os.remove(path)

def status_text():
    return f"{ANSI_GREEN}ON{ANSI_RESET}" if SCAN_RUNNING else f"{ANSI_RED}OFF{ANSI_RESET}"

def welcome_menu():
    clear()
    print("=" * 54)
    print("  AutoAccept Bot — Welcome")
    print("=" * 54)
    print(f"STATUS: {status_text()}")
    print("[1] Start/Stop — przełącz skanowanie (główna pętla)")
    print("[2] Config  — ustawienia (wkrótce)")
    print("[3] Linktree— otwórz moją stronę")
    print("[Q] Wyjdź")
    print("-" * 54)
    return input("Wybierz opcję [1/2/3/Q]: ").strip().lower()

def handle_linktree():
    print("[INFO] Otwieram Linktree…")
    try:
        webbrowser.open(LINKTREE_URL)
    except Exception as e:
        print(f"[BŁĄD] Nie udało się otworzyć strony: {e}")
    time.sleep(2)

def handle_config():
    clear()
    print("=== CONFIG ===")
    print("Edytor konfiguracji wkrótce.")
    input("\nEnter, aby wrócić do menu...")

def toggle_scanning():
    global SCAN_RUNNING, WORKER_THREAD, STOP_EVENT
    if not SCAN_RUNNING:
        STOP_EVENT = threading.Event()
        WORKER_THREAD = threading.Thread(
            target = scan_worker,
            args = (
                "https://raw.githubusercontent.com/bh0per/random-shit/refs/heads/main/accept.png",
                0.9,
                STOP_EVENT,
            ),
            daemon = True,
        )
        SCAN_RUNNING = True
        WORKER_THREAD.start()
    else:
        if STOP_EVENT:
            STOP_EVENT.set()
        if WORKER_THREAD:
            WORKER_THREAD.join(timeout = 0.2)
        SCAN_RUNNING = False

def main():
    enable_ansi_colors_on_windows()
    lock_console(38, 6)
    splash_and_admin(2.5)
    time.sleep(0.2)
    lock_console(54, 8)

    while True:
        c = welcome_menu()
        if c in ("1", "start", "stop"):
            toggle_scanning()
        elif c in ("2", "config", "c"):
            handle_config()
        elif c in ("3", "linktree", "l"):
            handle_linktree()
        elif c in ("q", "quit", "exit"):
            if SCAN_RUNNING and STOP_EVENT:
                STOP_EVENT.set()
            print("Do zobaczenia!")
            break
        else:
            print("Nieznana opcja. Spróbuj ponownie.")
            time.sleep(1)

if __name__ == "__main__":
    main()
