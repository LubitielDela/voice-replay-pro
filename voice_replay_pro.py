"""
Voice Replay PRO
Record headphone audio and replay it into a virtual microphone.
Запись звука из наушников и воспроизведение в виртуальный микрофон.

Author / Автор: LubitielDela (https://github.com/LubitielDela)
License / Лицензия: MIT
"""
import contextlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import warnings
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import keyboard
import numpy as np
import soundcard as sc
import soundfile as sf

warnings.filterwarnings("ignore", category=getattr(sc, "SoundcardRuntimeWarning", Warning))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIPS_DIR = os.path.join(BASE_DIR, "clips")
CFG_PATH = os.path.join(BASE_DIR, "config.json")
SAMPLE_RATE = 48000
CHUNK = SAMPLE_RATE // 10
MAX_REC_SECONDS = 120
AUTO = "Авто (устройство по умолчанию)"

ACTION_NAMES = {
    "record": "Начать / остановить запись",
    "play": "Воспроизвести / остановить",
    "prev": "Предыдущая запись",
    "next": "Следующая запись",
    "menu": "Открыть / скрыть меню",
    "overlay": "Показать / скрыть оверлей",
}
OVERLAY_NAMES = {
    "record": "запись",
    "play": "воспроизведение",
    "prev": "пред. запись",
    "next": "след. запись",
    "menu": "меню",
    "overlay": "оверлей",
}

DEFAULT_CFG = {
    "hotkeys": {
        "record": "f8", "play": "f9", "prev": "f10",
        "next": "f11", "menu": "insert", "overlay": "f7",
    },
    "overlay": {"enabled": True, "x": None, "y": None, "alpha": 0.85, "topmost": True},
    "menu_topmost": True,
    "volume": 1.0,
    "monitor": False,
    "loopback": AUTO,
    "output": "CABLE Input",
    "selected": "",
}

# ---- цвета ----
BG = "#16181d"
BG2 = "#1f222a"
FG = "#e6e6e6"
DIM = "#8a8f9c"
ACCENT = "#7c5cff"
RED = "#ff5555"
GREEN = "#50fa7b"


def load_cfg():
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    except Exception:
        pass
    return cfg


def fmt_time(sec):
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


class App:
    def __init__(self):
        os.makedirs(CLIPS_DIR, exist_ok=True)
        self.cfg = load_cfg()
        self.q = queue.Queue()

        # состояние
        self.recording = False
        self.rec_start = 0.0
        self.chunks = []
        self.rec_lock = threading.Lock()
        self.playing = False
        self.play_start = 0.0
        self.play_total = 0.0
        self.play_stop = threading.Event()
        self.rec_gen = 0
        self.error = ""
        self.clip_info = {}
        self.capturing = False

        self.root = tk.Tk()
        self.root.title("Voice Replay PRO")
        self.root.geometry("640x520")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", bool(self.cfg["menu_topmost"]))
        self.root.protocol("WM_DELETE_WINDOW", self.hide_menu)
        self._style()
        self._build_menu()
        self._build_overlay()

        self.refresh_clips()
        self.register_hotkeys()
        self.restart_listener()

        self.root.after(50, self._pump)
        self.root.after(200, self._tick)

    # ------------------------------------------------------------ utils
    def ui(self, fn):
        self.q.put(fn)

    def _pump(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        except Exception:
            traceback.print_exc()
        self.root.after(50, self._pump)

    def save_cfg(self):
        try:
            with open(CFG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Не удалось сохранить настройки:", e)

    def hk(self, action):
        return self.cfg["hotkeys"][action]

    # ------------------------------------------------------------ audio devices
    def loopback_names(self):
        try:
            return [m.name for m in sc.all_microphones(include_loopback=True)
                    if getattr(m, "isloopback", False)]
        except Exception:
            return []

    def speaker_names(self):
        try:
            return [s.name for s in sc.all_speakers()]
        except Exception:
            return []

    def get_loopback(self):
        name = self.cfg["loopback"]
        if name and name != AUTO:
            try:
                return sc.get_microphone(id=name, include_loopback=True)
            except Exception:
                pass
        spk = sc.default_speaker()
        return sc.get_microphone(id=str(spk.name), include_loopback=True)

    def get_output(self):
        want = self.cfg["output"].lower()
        for sp in sc.all_speakers():
            if want in sp.name.lower():
                return sp
        raise RuntimeError(f"Не найдено устройство вывода: {self.cfg['output']}")

    # ------------------------------------------------------------ recording
    def restart_listener(self):
        self.rec_gen += 1
        self.error = ""
        threading.Thread(target=self._rec_worker, args=(self.rec_gen,), daemon=True).start()

    def _rec_worker(self, gen):
        try:
            mic = self.get_loopback()
            with mic.recorder(samplerate=SAMPLE_RATE, channels=2) as rec:
                while gen == self.rec_gen:
                    data = rec.record(numframes=CHUNK)
                    if self.recording:
                        with self.rec_lock:
                            self.chunks.append(data.copy())
                        if time.time() - self.rec_start > MAX_REC_SECONDS:
                            self.ui(self.stop_record)
        except Exception as e:
            if gen == self.rec_gen:
                self.error = f"Ошибка записи: {e}"

    def toggle_record(self):
        if self.recording:
            self.stop_record()
        else:
            self.start_record()

    def start_record(self):
        if self.playing:
            self.error = "Сначала останови воспроизведение"
            return
        if self.recording:
            return
        with self.rec_lock:
            self.chunks = []
        self.error = ""
        self.rec_start = time.time()
        self.recording = True

    def stop_record(self):
        if not self.recording:
            return
        self.recording = False
        with self.rec_lock:
            chunks, self.chunks = self.chunks, []
        if not chunks:
            self.error = "Запись пустая (проверь устройство прослушивания)"
            return
        audio = np.concatenate(chunks, axis=0)
        path = os.path.join(CLIPS_DIR, f"clip_{time.strftime('%Y%m%d_%H%M%S')}.wav")
        try:
            sf.write(path, audio, SAMPLE_RATE)
        except Exception as e:
            self.error = f"Не удалось сохранить: {e}"
            return
        self.cfg["selected"] = path
        self.save_cfg()
        self.refresh_clips()

    # ------------------------------------------------------------ playback
    def toggle_play(self):
        if self.playing:
            self.play_stop.set()
            return
        if self.recording:
            self.error = "Сначала останови запись"
            return
        path = self.cfg.get("selected")
        if not path or not os.path.isfile(path):
            self.error = "Не выбрана запись"
            return
        self.play_stop.clear()
        self.play_start = time.time()
        self.play_total = self.clip_duration(path)
        self.playing = True
        self.error = ""
        threading.Thread(target=self._play_worker, args=(path,), daemon=True).start()

    def _play_worker(self, path):
        try:
            data, sr = sf.read(path, dtype="float32")
            if data.ndim == 1:
                data = np.stack([data, data], axis=1)
            self.play_total = len(data) / sr
            self.play_start = time.time()
            out = self.get_output()
            with contextlib.ExitStack() as stack:
                players = [stack.enter_context(out.player(samplerate=sr, channels=data.shape[1]))]
                if self.cfg.get("monitor"):
                    try:
                        mon = sc.default_speaker()
                        if mon.name != out.name:
                            players.append(stack.enter_context(
                                mon.player(samplerate=sr, channels=data.shape[1])))
                    except Exception:
                        pass
                step = sr // 10
                for i in range(0, len(data), step):
                    if self.play_stop.is_set():
                        break
                    chunk = np.clip(data[i:i + step] * float(self.cfg.get("volume", 1.0)), -1.0, 1.0)
                    for p in players:
                        p.play(chunk)
        except Exception as e:
            self.error = f"Ошибка воспроизведения: {e}"
        finally:
            self.playing = False

    # ------------------------------------------------------------ clips
    def clip_paths(self):
        files = [os.path.join(CLIPS_DIR, f) for f in os.listdir(CLIPS_DIR) if f.lower().endswith(".wav")]
        return sorted(files, key=os.path.getmtime)

    def clip_duration(self, path):
        try:
            mt = os.path.getmtime(path)
            cached = self.clip_info.get(path)
            if cached and cached[0] == mt:
                return cached[1]
            d = sf.info(path).duration
            self.clip_info[path] = (mt, d)
            return d
        except Exception:
            return 0.0

    def refresh_clips(self):
        paths = self.clip_paths()
        sel = self.cfg.get("selected")
        if sel not in paths:
            sel = paths[-1] if paths else ""
            self.cfg["selected"] = sel
        if hasattr(self, "tree"):
            self.tree.delete(*self.tree.get_children())
            for p in paths:
                self.tree.insert("", "end", iid=p, values=(
                    os.path.basename(p), fmt_time(self.clip_duration(p)),
                    time.strftime("%d.%m %H:%M", time.localtime(os.path.getmtime(p)))))
            if sel:
                self.tree.selection_set(sel)
                self.tree.see(sel)

    def select_delta(self, delta):
        paths = self.clip_paths()
        if not paths:
            return
        sel = self.cfg.get("selected")
        idx = paths.index(sel) if sel in paths else len(paths) - 1
        self.cfg["selected"] = paths[(idx + delta) % len(paths)]
        self.save_cfg()
        if hasattr(self, "tree"):
            self.tree.selection_set(self.cfg["selected"])
            self.tree.see(self.cfg["selected"])

    def on_tree_select(self, _e=None):
        s = self.tree.selection()
        if s:
            self.cfg["selected"] = s[0]
            self.save_cfg()

    def delete_clip(self):
        p = self.cfg.get("selected")
        if not p or not os.path.isfile(p):
            return
        if messagebox.askyesno("Удалить", f"Удалить запись {os.path.basename(p)}?", parent=self.root):
            try:
                os.remove(p)
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.root)
            self.cfg["selected"] = ""
            self.refresh_clips()
            self.save_cfg()

    def rename_clip(self):
        p = self.cfg.get("selected")
        if not p or not os.path.isfile(p):
            return
        old = os.path.splitext(os.path.basename(p))[0]
        new = simpledialog.askstring("Переименовать", "Новое имя:", initialvalue=old, parent=self.root)
        if not new:
            return
        new = "".join(c for c in new if c not in '\\/:*?"<>|').strip()
        if not new:
            return
        np_ = os.path.join(CLIPS_DIR, new + ".wav")
        if os.path.exists(np_):
            messagebox.showerror("Ошибка", "Файл с таким именем уже есть", parent=self.root)
            return
        os.rename(p, np_)
        self.cfg["selected"] = np_
        self.save_cfg()
        self.refresh_clips()

    def open_folder(self):
        try:
            if sys.platform.startswith("win"):
                os.startfile(CLIPS_DIR)  # noqa
            else:
                subprocess.Popen(["xdg-open", CLIPS_DIR])
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self.root)

    # ------------------------------------------------------------ hotkeys
    def register_hotkeys(self):
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        actions = {
            "record": self.toggle_record,
            "play": self.toggle_play,
            "prev": lambda: self.select_delta(-1),
            "next": lambda: self.select_delta(1),
            "menu": self.toggle_menu,
            "overlay": self.toggle_overlay,
        }
        for name, fn in actions.items():
            try:
                keyboard.add_hotkey(self.hk(name), lambda f=fn: self.ui(f))
            except Exception as e:
                self.error = f"Не удалось назначить {self.hk(name)}: {e}"

    def rebind(self, action):
        if self.capturing:
            return
        self.capturing = True
        self.bind_btns[action].config(text="Нажми комбинацию... (Esc - отмена)")
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

        def worker():
            try:
                hk = keyboard.read_hotkey(suppress=False)
            except Exception:
                hk = None

            def done():
                self.capturing = False
                if hk and hk != "esc":
                    clash = [a for a, v in self.cfg["hotkeys"].items() if v == hk and a != action]
                    if clash:
                        messagebox.showwarning(
                            "Занято", f"{hk.upper()} уже используется для: {ACTION_NAMES[clash[0]]}",
                            parent=self.root)
                    else:
                        self.cfg["hotkeys"][action] = hk
                        self.save_cfg()
                self.register_hotkeys()
                self.refresh_bind_buttons()
                self.rebuild_overlay_text()

            self.ui(done)

        threading.Thread(target=worker, daemon=True).start()

    def reset_hotkeys(self):
        self.cfg["hotkeys"] = dict(DEFAULT_CFG["hotkeys"])
        self.save_cfg()
        self.register_hotkeys()
        self.refresh_bind_buttons()
        self.rebuild_overlay_text()

    # ------------------------------------------------------------ menu UI
    def _style(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure(".", background=BG, foreground=FG, fieldbackground=BG2, bordercolor=BG2,
                     lightcolor=BG2, darkcolor=BG2, font=("Segoe UI", 10))
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background=BG2, foreground=DIM, padding=(14, 6))
        st.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "#fff")])
        st.configure("TButton", background=BG2, foreground=FG, padding=6, borderwidth=0)
        st.map("TButton", background=[("active", ACCENT)])
        st.configure("Accent.TButton", background=ACCENT, foreground="#fff")
        st.configure("Treeview", background=BG2, fieldbackground=BG2, foreground=FG, rowheight=26, borderwidth=0)
        st.configure("Treeview.Heading", background=BG, foreground=DIM, borderwidth=0)
        st.map("Treeview", background=[("selected", ACCENT)])
        st.configure("TCheckbutton", background=BG, foreground=FG)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("TFrame", background=BG)
        st.configure("Dim.TLabel", foreground=DIM)
        st.configure("Horizontal.TScale", background=BG)

    def _build_menu(self):
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=14, pady=(12, 4))
        ttk.Label(top, text="Voice Replay PRO", font=("Segoe UI", 15, "bold")).pack(side="left")
        self.menu_status = ttk.Label(top, text="", style="Dim.TLabel")
        self.menu_status.pack(side="right")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=14, pady=8)
        tab_clips = ttk.Frame(nb)
        tab_keys = ttk.Frame(nb)
        tab_set = ttk.Frame(nb)
        nb.add(tab_clips, text="Записи")
        nb.add(tab_keys, text="Горячие клавиши")
        nb.add(tab_set, text="Настройки")

        # --- Записи
        bar = ttk.Frame(tab_clips)
        bar.pack(fill="x", pady=8)
        self.btn_rec = ttk.Button(bar, text="● Запись", style="Accent.TButton", command=self.toggle_record)
        self.btn_rec.pack(side="left", padx=(0, 6))
        self.btn_play = ttk.Button(bar, text="▶ Играть", style="Accent.TButton", command=self.toggle_play)
        self.btn_play.pack(side="left", padx=6)
        ttk.Button(bar, text="Переименовать", command=self.rename_clip).pack(side="left", padx=6)
        ttk.Button(bar, text="Удалить", command=self.delete_clip).pack(side="left", padx=6)
        ttk.Button(bar, text="Папка", command=self.open_folder).pack(side="left", padx=6)

        cols = ("name", "len", "date")
        self.tree = ttk.Treeview(tab_clips, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("name", text="Название")
        self.tree.heading("len", text="Длина")
        self.tree.heading("date", text="Дата")
        self.tree.column("name", width=300)
        self.tree.column("len", width=70, anchor="center")
        self.tree.column("date", width=120, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-1>", lambda e: self.toggle_play())
        ttk.Label(tab_clips, text="Двойной клик по записи - воспроизвести", style="Dim.TLabel").pack(anchor="w", pady=4)

        # --- Горячие клавиши
        self.bind_btns = {}
        grid = ttk.Frame(tab_keys)
        grid.pack(fill="x", pady=10)
        for i, action in enumerate(ACTION_NAMES):
            ttk.Label(grid, text=ACTION_NAMES[action]).grid(row=i, column=0, sticky="w", padx=6, pady=7)
            b = ttk.Button(grid, width=34, command=lambda a=action: self.rebind(a))
            b.grid(row=i, column=1, padx=10, pady=7)
            self.bind_btns[action] = b
        grid.columnconfigure(0, weight=1)
        ttk.Button(tab_keys, text="Сбросить по умолчанию", command=self.reset_hotkeys).pack(anchor="w", padx=6, pady=8)
        ttk.Label(tab_keys, text="Нажми кнопку и затем нужную клавишу или комбинацию (например, ctrl+f5).",
                  style="Dim.TLabel").pack(anchor="w", padx=6)
        self.refresh_bind_buttons()

        # --- Настройки
        self._build_settings(tab_set)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(bottom, text="Скрыть меню", command=self.hide_menu).pack(side="left")
        ttk.Label(bottom, text="Автор / Author: LubitielDela", style="Dim.TLabel").pack(side="left", padx=14)
        ttk.Button(bottom, text="Выход", command=self.quit).pack(side="right")

    def _build_settings(self, tab):
        r = 0
        ttk.Label(tab, text="Откуда записывать (твои наушники):").grid(row=r, column=0, sticky="w", padx=6, pady=8)
        self.cb_loop = ttk.Combobox(tab, width=42, state="readonly",
                                    values=[AUTO] + self.loopback_names())
        self.cb_loop.set(self.cfg["loopback"] if self.cfg["loopback"] in [AUTO] + self.loopback_names() else AUTO)
        self.cb_loop.grid(row=r, column=1, padx=6)
        self.cb_loop.bind("<<ComboboxSelected>>", self.on_loop_change)

        r += 1
        ttk.Label(tab, text="Куда воспроизводить (виртуальный кабель):").grid(row=r, column=0, sticky="w", padx=6, pady=8)
        spk = self.speaker_names()
        self.cb_out = ttk.Combobox(tab, width=42, state="readonly", values=spk)
        cur = next((n for n in spk if self.cfg["output"].lower() in n.lower()), "")
        self.cb_out.set(cur)
        self.cb_out.grid(row=r, column=1, padx=6)
        self.cb_out.bind("<<ComboboxSelected>>", self.on_out_change)

        r += 1
        ttk.Label(tab, text="Громкость воспроизведения:").grid(row=r, column=0, sticky="w", padx=6, pady=8)
        self.vol = tk.DoubleVar(value=self.cfg["volume"])
        ttk.Scale(tab, from_=0.1, to=2.0, variable=self.vol, length=260,
                  command=self.on_vol).grid(row=r, column=1, sticky="w", padx=6)

        r += 1
        self.mon_var = tk.BooleanVar(value=self.cfg["monitor"])
        ttk.Checkbutton(tab, text="Слышать воспроизведение в своих наушниках",
                        variable=self.mon_var, command=self.on_mon).grid(row=r, column=0, columnspan=2, sticky="w", padx=6, pady=8)

        r += 1
        ttk.Separator(tab).grid(row=r, column=0, columnspan=2, sticky="ew", pady=8)

        r += 1
        self.ov_var = tk.BooleanVar(value=self.cfg["overlay"]["enabled"])
        ttk.Checkbutton(tab, text="Показывать оверлей", variable=self.ov_var,
                        command=self.on_overlay_check).grid(row=r, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        r += 1
        self.ov_top_var = tk.BooleanVar(value=self.cfg["overlay"]["topmost"])
        ttk.Checkbutton(tab, text="Оверлей поверх всех окон", variable=self.ov_top_var,
                        command=self.on_ov_topmost).grid(row=r, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        r += 1
        self.menu_top_var = tk.BooleanVar(value=self.cfg["menu_topmost"])
        ttk.Checkbutton(tab, text="Меню поверх всех окон", variable=self.menu_top_var,
                        command=self.on_menu_topmost).grid(row=r, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        r += 1
        ttk.Label(tab, text="Прозрачность оверлея:").grid(row=r, column=0, sticky="w", padx=6, pady=8)
        self.alpha = tk.DoubleVar(value=self.cfg["overlay"]["alpha"])
        ttk.Scale(tab, from_=0.3, to=1.0, variable=self.alpha, length=260,
                  command=self.on_alpha).grid(row=r, column=1, sticky="w", padx=6)

        r += 1
        ttk.Label(tab, text="Положение оверлея:").grid(row=r, column=0, sticky="w", padx=6, pady=8)
        corners = ttk.Frame(tab)
        corners.grid(row=r, column=1, sticky="w", padx=6)
        for txt, c in (("↖", "tl"), ("↗", "tr"), ("↙", "bl"), ("↘", "br")):
            ttk.Button(corners, text=txt, width=4, command=lambda c=c: self.place_corner(c)).pack(side="left", padx=3)
        ttk.Label(tab, text="(или перетащи оверлей мышью)", style="Dim.TLabel").grid(row=r + 1, column=1, sticky="w", padx=6)

    # --- settings callbacks
    def on_loop_change(self, _e=None):
        self.cfg["loopback"] = self.cb_loop.get()
        self.save_cfg()
        self.restart_listener()

    def on_out_change(self, _e=None):
        self.cfg["output"] = self.cb_out.get()
        self.save_cfg()

    def on_vol(self, _v=None):
        self.cfg["volume"] = round(self.vol.get(), 2)
        self.save_cfg()

    def on_mon(self):
        self.cfg["monitor"] = bool(self.mon_var.get())
        self.save_cfg()

    def on_overlay_check(self):
        self.cfg["overlay"]["enabled"] = bool(self.ov_var.get())
        self.save_cfg()
        self.apply_overlay_visibility()

    def on_ov_topmost(self):
        self.cfg["overlay"]["topmost"] = bool(self.ov_top_var.get())
        self.save_cfg()
        self.ov.attributes("-topmost", self.cfg["overlay"]["topmost"])

    def on_menu_topmost(self):
        self.cfg["menu_topmost"] = bool(self.menu_top_var.get())
        self.save_cfg()
        self.root.attributes("-topmost", self.cfg["menu_topmost"])

    def on_alpha(self, _v=None):
        self.cfg["overlay"]["alpha"] = round(self.alpha.get(), 2)
        self.save_cfg()
        if hasattr(self, "ov"):
            self.ov.attributes("-alpha", self.cfg["overlay"]["alpha"])

    def refresh_bind_buttons(self):
        for a, b in self.bind_btns.items():
            b.config(text=self.hk(a).upper())

    # ------------------------------------------------------------ menu show/hide
    def toggle_menu(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.attributes("-topmost", bool(self.cfg["menu_topmost"]))
            self.root.lift()
            self.root.focus_force()
        else:
            self.hide_menu()

    def hide_menu(self):
        self.root.withdraw()

    def quit(self):
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.save_cfg()
        self.root.destroy()
        os._exit(0)

    # ------------------------------------------------------------ overlay
    def _build_overlay(self):
        self.ov = tk.Toplevel(self.root)
        self.ov.overrideredirect(True)
        self.ov.attributes("-topmost", bool(self.cfg["overlay"]["topmost"]))
        try:
            self.ov.attributes("-alpha", self.cfg["overlay"]["alpha"])
        except Exception:
            pass
        self.ov.configure(bg=BG)
        frame = tk.Frame(self.ov, bg=BG, highlightthickness=1, highlightbackground=ACCENT)
        frame.pack(fill="both", expand=True)
        self.ov_title = tk.Label(frame, text="Voice Replay PRO", bg=BG, fg=ACCENT,
                                 font=("Segoe UI", 10, "bold"), anchor="w")
        self.ov_title.pack(fill="x", padx=10, pady=(6, 0))
        self.ov_status = tk.Label(frame, text="", bg=BG, fg=DIM, font=("Segoe UI", 11, "bold"), anchor="w")
        self.ov_status.pack(fill="x", padx=10)
        self.ov_clip = tk.Label(frame, text="", bg=BG, fg=FG, font=("Segoe UI", 9), anchor="w")
        self.ov_clip.pack(fill="x", padx=10)
        tk.Frame(frame, bg=BG2, height=1).pack(fill="x", padx=10, pady=4)
        self.ov_binds = tk.Label(frame, text="", bg=BG, fg=DIM, font=("Consolas", 9), anchor="w", justify="left")
        self.ov_binds.pack(fill="x", padx=10, pady=(0, 6))
        self.rebuild_overlay_text()

        # перетаскивание мышью
        self._drag = (0, 0)
        for w in (self.ov, frame, self.ov_title, self.ov_status, self.ov_clip, self.ov_binds):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)

        self.ov.update_idletasks()
        x, y = self.cfg["overlay"]["x"], self.cfg["overlay"]["y"]
        if x is None or y is None:
            x = self.root.winfo_screenwidth() - self.ov.winfo_reqwidth() - 20
            y = 20
        self.ov.geometry(f"+{int(x)}+{int(y)}")
        self.apply_overlay_visibility()

    def rebuild_overlay_text(self):
        lines = [f"{self.hk(a).upper():<10}{OVERLAY_NAMES[a]}" for a in ACTION_NAMES]
        self.ov_binds.config(text="\n".join(lines))

    def apply_overlay_visibility(self):
        if self.cfg["overlay"]["enabled"]:
            self.ov.deiconify()
            self.ov.attributes("-topmost", bool(self.cfg["overlay"]["topmost"]))
        else:
            self.ov.withdraw()

    def toggle_overlay(self):
        self.cfg["overlay"]["enabled"] = not self.cfg["overlay"]["enabled"]
        if hasattr(self, "ov_var"):
            self.ov_var.set(self.cfg["overlay"]["enabled"])
        self.save_cfg()
        self.apply_overlay_visibility()

    def _drag_start(self, e):
        self._drag = (e.x_root - self.ov.winfo_x(), e.y_root - self.ov.winfo_y())

    def _drag_move(self, e):
        self.ov.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def _drag_end(self, _e):
        self.cfg["overlay"]["x"] = self.ov.winfo_x()
        self.cfg["overlay"]["y"] = self.ov.winfo_y()
        self.save_cfg()

    def place_corner(self, c):
        self.ov.update_idletasks()
        w, h = self.ov.winfo_reqwidth(), self.ov.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        m = 20
        x = m if c in ("tl", "bl") else sw - w - m
        y = m if c in ("tl", "tr") else sh - h - m - 40
        self.ov.geometry(f"+{x}+{y}")
        self.cfg["overlay"]["x"], self.cfg["overlay"]["y"] = x, y
        self.save_cfg()

    # ------------------------------------------------------------ periodic UI update
    def _tick(self):
        try:
            if self.recording:
                el = time.time() - self.rec_start
                text, color = f"● ЗАПИСЬ  {fmt_time(el)}", RED
            elif self.playing:
                el = min(time.time() - self.play_start, self.play_total)
                text, color = f"▶ ВОСПРОИЗВЕДЕНИЕ  {fmt_time(el)}/{fmt_time(self.play_total)}", GREEN
            elif self.error:
                text, color = f"⚠ {self.error}", "#ffb86c"
            else:
                text, color = "● Ожидание", DIM
            sel = self.cfg.get("selected")
            clip = f"Запись: {os.path.basename(sel)} ({fmt_time(self.clip_duration(sel))})" if sel else "Записей нет"
            self.ov_status.config(text=text, fg=color)
            self.ov_clip.config(text=clip)
            if hasattr(self, "btn_rec"):
                self.btn_rec.config(text="■ Стоп записи" if self.recording else "● Запись")
                self.btn_play.config(text="■ Стоп" if self.playing else "▶ Играть")
                self.menu_status.config(text=text)
            if self.cfg["overlay"]["enabled"] and self.cfg["overlay"]["topmost"]:
                # периодически поднимаем оверлей, чтобы его не перекрыла игра
                self.ov.attributes("-topmost", True)
                self.ov.lift()
        except Exception:
            traceback.print_exc()
        self.root.after(200, self._tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        App().run()
    except Exception:
        print("\n=== ОШИБКА ===")
        traceback.print_exc()
        input("\nНажми Enter, чтобы закрыть окно...")
