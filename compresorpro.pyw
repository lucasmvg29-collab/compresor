#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CompresorPRO v3.1
=================
Suite de compresión multi-formato con GUI moderna.
Formatos: .luc (LZMA), .zip, .7z, .tar, .tar.gz, .tar.bz2, .tar.xz
Extras: carpetas, contraseñas AES-256, split, búsqueda, perfiles, temas en vivo.
"""

import os
import sys
import json
import time
import shutil
import zipfile
import tarfile
import lzma
import threading
from datetime import datetime

# ----------------------------------------------------------------------
# Ocultar consola en Windows
# ----------------------------------------------------------------------
if os.name == "nt":
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ----------------------------------------------------------------------
# Dependencias opcionales
# ----------------------------------------------------------------------
try:
    import py7zr
    HAS_7Z = True
except ImportError:
    HAS_7Z = False

try:
    import pyzipper
    HAS_ZIP_CRYPTO = True
except ImportError:
    HAS_ZIP_CRYPTO = False

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False


# ----------------------------------------------------------------------
# Constantes globales
# ----------------------------------------------------------------------
APP_NAME = "CompresorPRO"
APP_VERSION = "3.1"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

FORMATOS_COMPRIMIR = {
    "🟣  LUC  (LZMA extremo, mejor ratio)": ".luc",
    "🔵  ZIP  (máxima compatibilidad)": ".zip",
    "🟠  7Z   (equilibrado, soporta AES)": ".7z",
    "🟢  TAR.GZ  (Linux-friendly)": ".tar.gz",
    "🟡  TAR.BZ2  (buen ratio, lento)": ".tar.bz2",
    "🔴  TAR.XZ  (excelente ratio)": ".tar.xz",
    "⚪  TAR  (sin comprimir)": ".tar",
}

DICT_SIZES = {
    "8 MiB (rápido)": 8 << 20,
    "32 MiB": 32 << 20,
    "64 MiB (recomendado)": 64 << 20,
    "128 MiB": 128 << 20,
    "256 MiB (potente)": 256 << 20,
    "512 MiB (máxima)": 512 << 20,
}

PRESETS = {
    "⚡ Rápido": 1,
    "⚖ Equilibrado": 6,
    "🔥 Alta compresión": 9,
    "💎 MÁXIMO (EXTREME)": 9 | lzma.PRESET_EXTREME,
}

TEMAS = {
    "oscuro": {
        "bg": "#1e1e2e", "bg2": "#282a3a", "fg": "#e0e0e0", "fg2": "#a0a0a0",
        "accent": "#7c5cff", "accent2": "#5a3fd6", "success": "#4ade80",
        "error": "#f87171", "entry": "#2d2d44", "border": "#3a3a55",
    },
    "claro": {
        "bg": "#f5f6fa", "bg2": "#ffffff", "fg": "#1a1a1a", "fg2": "#666666",
        "accent": "#4f46e5", "accent2": "#4338ca", "success": "#16a34a",
        "error": "#dc2626", "entry": "#ffffff", "border": "#d1d5db",
    },
}

# Extensiones ya comprimidas por naturaleza (avisar al usuario)
EXTENSIONES_YA_COMPRIMIDAS = {
    ".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".luc",
    ".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".txz",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".avif",
    ".mp3", ".aac", ".ogg", ".flac", ".m4a", ".wma",
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv",
    ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp",
    ".pdf",
}

DEFAULT_CFG = {
    "tema": "oscuro",
    "perfil_actual": "Equilibrado",
    "formato_preferido": ".luc",
    "preset": "💎 MÁXIMO (EXTREME)",
    "dict_size": "64 MiB (recomendado)",
    "chunk_mb": 4,
    "historial": [],
    "perfiles": {
        "Rápido":         {"formato": ".zip", "preset": "⚡ Rápido",        "dict_size": "8 MiB (rápido)"},
        "Equilibrado":    {"formato": ".7z",  "preset": "⚖ Equilibrado",   "dict_size": "64 MiB (recomendado)"},
        "Máximo":         {"formato": ".luc", "preset": "💎 MÁXIMO (EXTREME)", "dict_size": "256 MiB (potente)"},
        "Email (25 MB)":  {"formato": ".zip", "preset": "⚖ Equilibrado",   "dict_size": "32 MiB", "split_mb": 25},
        "Backup Linux":   {"formato": ".tar.gz", "preset": "🔥 Alta compresión", "dict_size": "64 MiB (recomendado)"},
    },
}


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
def cargar_config():
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    try:
        if os.path.isfile(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg.update(data)
    except Exception:
        pass
    return cfg


def guardar_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------
def humano(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.2f} {u}"
        n /= 1024
    return f"{n:.2f} PB"


def _filtros_lzma(cfg):
    return [{
        "id": lzma.FILTER_LZMA2,
        "preset": PRESETS.get(cfg["preset"], 9 | lzma.PRESET_EXTREME),
        "dict_size": DICT_SIZES.get(cfg["dict_size"], 64 << 20),
    }]


def _es_carpeta(p): return os.path.isdir(p)


def _listar(ruta):
    if _es_carpeta(ruta):
        total, files = 0, []
        for root, _, fs in os.walk(ruta):
            for f in fs:
                fp = os.path.join(root, f)
                try:
                    total += os.path.getsize(fp)
                    files.append(fp)
                except OSError:
                    pass
        return files, total
    return [ruta], os.path.getsize(ruta)


def _parece_comprimido(rutas):
    """True si >70% de los archivos ya están comprimidos de origen."""
    archivos = []
    for r in rutas:
        if os.path.isfile(r):
            archivos.append(r)
        elif os.path.isdir(r):
            for root, _, fs in os.walk(r):
                for f in fs:
                    archivos.append(os.path.join(root, f))
    if not archivos:
        return False
    ya = sum(1 for a in archivos
             if any(a.lower().endswith(e) for e in EXTENSIONES_YA_COMPRIMIDAS))
    return (ya / len(archivos)) > 0.7


# ----------------------------------------------------------------------
# Backends de compresión
# ----------------------------------------------------------------------
def comprimir_luc(origenes, destino, cfg, progress=None):
    total = sum(os.path.getsize(p) for p in origenes if os.path.isfile(p))
    procesado = 0
    chunk = cfg["chunk_mb"] * 1024 * 1024
    with lzma.open(destino, "wb", format=lzma.FORMAT_XZ,
                   filters=_filtros_lzma(cfg)) as f_out:
        for p in origenes:
            with open(p, "rb") as f_in:
                while True:
                    b = f_in.read(chunk)
                    if not b:
                        break
                    f_out.write(b)
                    procesado += len(b)
                    if progress:
                        progress(procesado, total)


def comprimir_zip(origenes, destino, cfg, password=None, progress=None):
    total = sum(os.path.getsize(p) for p in origenes if os.path.isfile(p))
    procesado = 0
    if password and HAS_ZIP_CRYPTO:
        zf = pyzipper.AESZipFile(destino, "w",
                                 compression=pyzipper.ZIP_LZMA,
                                 encryption=pyzipper.WZ_AES)
        zf.setpassword(password.encode())
        zf.setencryption(pyzipper.WZ_AES, nbits=256)
    else:
        zf = zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=9)
    with zf:
        for p in origenes:
            if os.path.isfile(p):
                zf.write(p, arcname=os.path.basename(p))
                procesado += os.path.getsize(p)
                if progress: progress(procesado, total)
            elif os.path.isdir(p):
                base = os.path.dirname(p)
                for root, _, files in os.walk(p):
                    for f in files:
                        fp = os.path.join(root, f)
                        arc = os.path.relpath(fp, base)
                        zf.write(fp, arcname=arc)
                        procesado += os.path.getsize(fp)
                        if progress: progress(procesado, total)


def comprimir_7z(origenes, destino, cfg, password=None, progress=None):
    if not HAS_7Z:
        raise RuntimeError("py7zr no está instalado. Ejecuta: pip install py7zr")
    total = sum(os.path.getsize(p) for p in origenes if os.path.isfile(p))
    procesado = 0
    kwargs = {}
    if password:
        kwargs["password"] = password
    with py7zr.SevenZipFile(destino, "w", **kwargs) as z:
        for p in origenes:
            if os.path.isfile(p):
                z.write(p, arcname=os.path.basename(p))
                procesado += os.path.getsize(p)
                if progress: progress(procesado, total)
            elif os.path.isdir(p):
                base = os.path.dirname(p)
                for root, _, files in os.walk(p):
                    for f in files:
                        fp = os.path.join(root, f)
                        arc = os.path.relpath(fp, base).replace("\\", "/")
                        z.write(fp, arcname=arc)
                        procesado += os.path.getsize(fp)
                        if progress: progress(procesado, total)


def comprimir_tar(origenes, destino, cfg, modo="w:gz", progress=None):
    total = sum(os.path.getsize(p) for p in origenes if os.path.isfile(p))
    procesado = 0
    with tarfile.open(destino, modo) as tf:
        for p in origenes:
            if os.path.isfile(p):
                tf.add(p, arcname=os.path.basename(p))
                procesado += os.path.getsize(p)
                if progress: progress(procesado, total)
            elif os.path.isdir(p):
                base = os.path.dirname(p)
                for root, _, files in os.walk(p):
                    for f in files:
                        fp = os.path.join(root, f)
                        arc = os.path.relpath(fp, base)
                        tf.add(fp, arcname=arc)
                        procesado += os.path.getsize(fp)
                        if progress: progress(procesado, total)


def descomprimir(ruta, destino, password=None, progress=None):
    low = ruta.lower()
    os.makedirs(destino, exist_ok=True)

    if low.endswith(".luc") or low.endswith(".xz") or low.endswith(".lzma"):
        with lzma.open(ruta, "rb") as f_in:
            out = os.path.join(destino, os.path.basename(ruta).rsplit(".", 1)[0])
            with open(out, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out, 1 << 20)
    elif low.endswith(".zip"):
        if password and HAS_ZIP_CRYPTO:
            with pyzipper.AESZipFile(ruta, "r") as zf:
                zf.setpassword(password.encode())
                zf.extractall(destino)
        else:
            with zipfile.ZipFile(ruta, "r") as zf:
                zf.extractall(destino)
    elif low.endswith(".7z"):
        if not HAS_7Z:
            raise RuntimeError("py7zr no está instalado.")
        kwargs = {"password": password} if password else {}
        with py7zr.SevenZipFile(ruta, "r", **kwargs) as z:
            z.extractall(destino)
    elif low.endswith(".tar"):
        with tarfile.open(ruta, "r:") as tf:
            tf.extractall(destino)
    elif low.endswith(".tar.gz") or low.endswith(".tgz"):
        with tarfile.open(ruta, "r:gz") as tf:
            tf.extractall(destino)
    elif low.endswith(".tar.bz2"):
        with tarfile.open(ruta, "r:bz2") as tf:
            tf.extractall(destino)
    elif low.endswith(".tar.xz") or low.endswith(".txz"):
        with tarfile.open(ruta, "r:xz") as tf:
            tf.extractall(destino)
    else:
        raise ValueError(f"Formato no reconocido: {ruta}")


def buscar_en_archivo(ruta, patron):
    patron = patron.lower()
    resultados = []
    low = ruta.lower()
    try:
        if low.endswith(".zip"):
            with zipfile.ZipFile(ruta, "r") as zf:
                for n in zf.namelist():
                    try:
                        data = zf.read(n).decode("utf-8", errors="ignore")
                        for i, linea in enumerate(data.splitlines(), 1):
                            if patron in linea.lower():
                                resultados.append((n, i, linea[:200]))
                    except Exception:
                        pass
        elif low.endswith(".tar") or ".tar." in low:
            modo = {"gz": "r:gz", "bz2": "r:bz2", "xz": "r:xz"}.get(
                low.rsplit(".", 1)[-1], "r:")
            with tarfile.open(ruta, modo) as tf:
                for m in tf.getmembers():
                    if m.isfile() and m.size < 5_000_000:
                        f = tf.extractfile(m)
                        if f:
                            try:
                                data = f.read().decode("utf-8", errors="ignore")
                                for i, linea in enumerate(data.splitlines(), 1):
                                    if patron in linea.lower():
                                        resultados.append((m.name, i, linea[:200]))
                            except Exception:
                                pass
    except Exception as e:
        resultados.append((f"[error: {e}]", 0, ""))
    return resultados


def dividir_archivo(ruta, tam_mb):
    tam = tam_mb * 1024 * 1024
    partes = []
    with open(ruta, "rb") as f:
        i = 1
        while True:
            b = f.read(tam)
            if not b:
                break
            p = f"{ruta}.{i:03d}"
            with open(p, "wb") as o:
                o.write(b)
            partes.append(p)
            i += 1
    return partes


# ======================================================================
# GUI
# ======================================================================
BaseTk = TkinterDnD.Tk if HAS_DND else tk.Tk


class CompresorPRO(BaseTk):

    def __init__(self):
        super().__init__()
        self.cfg = cargar_config()
        self.colores = TEMAS[self.cfg["tema"]]
        self._widgets_tema = []

        self.title(f"🗜  {APP_NAME}  v{APP_VERSION}")
        self.geometry("900x680")
        self.minsize(820, 600)
        self.configure(bg=self.colores["bg"])

        self._aplicar_estilos()
        self._construir_ui()
        self._registrar_dnd()
        self._aplicar_icono()

    # -------------------------------------------------- estilos
    def _aplicar_estilos(self):
        c = self.colores
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", background=c["bg"], foreground=c["fg"],
                    fieldbackground=c["entry"], font=("Segoe UI", 10))
        s.configure("TFrame", background=c["bg"])
        s.configure("TLabel", background=c["bg"], foreground=c["fg"])
        s.configure("Header.TFrame", background=c["bg2"])
        s.configure("Header.TLabel", background=c["bg2"], foreground=c["fg"],
                    font=("Segoe UI", 15, "bold"))
        s.configure("Sub.TLabel", background=c["bg2"], foreground=c["fg2"],
                    font=("Segoe UI", 9))
        s.configure("TNotebook", background=c["bg"], borderwidth=0)
        s.configure("TNotebook.Tab", background=c["bg2"], foreground=c["fg2"],
                    padding=(18, 9), font=("Segoe UI", 10))
        s.map("TNotebook.Tab",
              background=[("selected", c["accent"])],
              foreground=[("selected", "#ffffff")])
        s.configure("TButton", background=c["bg2"], foreground=c["fg"],
                    borderwidth=0, padding=(10, 8), font=("Segoe UI", 10))
        s.map("TButton", background=[("active", c["border"])])
        s.configure("Accent.TButton", background=c["accent"], foreground="#ffffff",
                    font=("Segoe UI", 10, "bold"), padding=(14, 10))
        s.map("Accent.TButton", background=[("active", c["accent2"])])
        s.configure("TLabelframe", background=c["bg"], foreground=c["fg"])
        s.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"])
        s.configure("TEntry", fieldbackground=c["entry"], foreground=c["fg"],
                    insertcolor=c["fg"])
        s.configure("TCombobox", fieldbackground=c["entry"], foreground=c["fg"])
        s.configure("Horizontal.TProgressbar",
                    background=c["accent"], troughcolor=c["bg2"])

    # -------------------------------------------------- UI
    def _construir_ui(self):
        c = self.colores

        head = ttk.Frame(self, style="Header.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=f"🗜  {APP_NAME}", style="Header.TLabel"
                  ).pack(side="left", padx=18, pady=14)
        ttk.Label(head, text=f"v{APP_VERSION}  ·  multi-formato",
                  style="Sub.TLabel").pack(side="left", padx=4, pady=(22, 14))
        self.btn_tema = ttk.Button(head, text=self._txt_tema(),
                                   command=self._toggle_tema)
        self.btn_tema.pack(side="right", padx=6, pady=10)
        ttk.Button(head, text="ℹ Acerca de",
                   command=self._acerca_de).pack(side="right", padx=6, pady=10)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        self._tab_comprimir()
        self._tab_descomprimir()
        self._tab_explorar()
        self._tab_historial()
        self._tab_config()

        pie = ttk.Frame(self)
        pie.pack(fill="x", side="bottom")
        self.pb = ttk.Progressbar(pie, mode="determinate")
        self.pb.pack(fill="x", padx=12, pady=(4, 0))
        self.status = tk.StringVar(value="Listo.")
        self.lbl_status = tk.Label(pie, textvariable=self.status, bg=c["bg"],
                                   fg=c["fg2"], anchor="w", font=("Segoe UI", 9))
        self.lbl_status.pack(fill="x", padx=14, pady=(2, 8))
        self._registrar_widget_tema(self.lbl_status)

    def _txt_tema(self):
        return "🌙 Oscuro" if self.cfg["tema"] == "oscuro" else "☀ Claro"

    # ------------------ Tab 1: Comprimir ------------------
    def _tab_comprimir(self):
        f = ttk.Frame(self.nb, padding=16)
        self.nb.add(f, text="📦  Comprimir")

        ttk.Label(f, text="Archivos o carpetas a comprimir:",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=4,
                                                     sticky="w", pady=(0, 6))

        self.lst_comp = tk.Listbox(f, height=6, bg=self.colores["entry"],
                                   fg=self.colores["fg"],
                                   selectbackground=self.colores["accent"],
                                   highlightthickness=1,
                                   highlightbackground=self.colores["border"],
                                   font=("Segoe UI", 9))
        self.lst_comp.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=(0, 8))
        self._registrar_widget_tema(self.lst_comp)

        ttk.Button(f, text="➕ Añadir archivos",
                   command=self._add_archivos).grid(row=2, column=0, sticky="w")
        ttk.Button(f, text="📁 Añadir carpeta",
                   command=self._add_carpeta).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Button(f, text="➖ Quitar selección",
                   command=self._quitar_sel).grid(row=2, column=2, sticky="w")
        ttk.Button(f, text="🗑 Limpiar",
                   command=lambda: self.lst_comp.delete(0, "end")
                   ).grid(row=2, column=3, sticky="w")

        opt = ttk.LabelFrame(f, text="Opciones de compresión", padding=12)
        opt.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        opt.columnconfigure(1, weight=1)
        opt.columnconfigure(3, weight=1)

        ttk.Label(opt, text="Formato:").grid(row=0, column=0, sticky="w", pady=4)
        self.cmb_formato = ttk.Combobox(opt, values=list(FORMATOS_COMPRIMIR.keys()),
                                        state="readonly")
        self.cmb_formato.set(next(k for k, v in FORMATOS_COMPRIMIR.items()
                                  if v == self.cfg["formato_preferido"]))
        self.cmb_formato.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(opt, text="Perfil:").grid(row=0, column=2, sticky="w", pady=4)
        self.cmb_perfil = ttk.Combobox(opt, values=list(self.cfg["perfiles"].keys()),
                                       state="readonly")
        self.cmb_perfil.set(self.cfg["perfil_actual"])
        self.cmb_perfil.bind("<<ComboboxSelected>>", self._cargar_perfil)
        self.cmb_perfil.grid(row=0, column=3, sticky="ew", padx=6, pady=4)

        ttk.Label(opt, text="Preset LZMA:").grid(row=1, column=0, sticky="w", pady=4)
        self.cmb_preset = ttk.Combobox(opt, values=list(PRESETS.keys()), state="readonly")
        self.cmb_preset.set(self.cfg["preset"])
        self.cmb_preset.grid(row=1, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(opt, text="Diccionario:").grid(row=1, column=2, sticky="w", pady=4)
        self.cmb_dict = ttk.Combobox(opt, values=list(DICT_SIZES.keys()), state="readonly")
        self.cmb_dict.set(self.cfg["dict_size"])
        self.cmb_dict.grid(row=1, column=3, sticky="ew", padx=6, pady=4)

        ttk.Label(opt, text="🔒 Contraseña (opcional):").grid(row=2, column=0, sticky="w", pady=4)
        self.ent_pass = ttk.Entry(opt, show="•")
        self.ent_pass.grid(row=2, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(opt, text="✂ Dividir en (MB, 0=no):").grid(row=2, column=2, sticky="w", pady=4)
        self.ent_split = ttk.Entry(opt)
        self.ent_split.insert(0, "0")
        self.ent_split.grid(row=2, column=3, sticky="ew", padx=6, pady=4)

        ttk.Label(opt, text="Destino:").grid(row=3, column=0, sticky="w", pady=4)
        self.ent_destino_c = ttk.Entry(opt)
        self.ent_destino_c.grid(row=3, column=1, columnspan=2, sticky="ew", padx=6, pady=4)
        ttk.Button(opt, text="Examinar…",
                   command=self._elegir_destino_c).grid(row=3, column=3, sticky="ew", padx=6)

        ttk.Button(f, text="🚀  COMPRIMIR AHORA", style="Accent.TButton",
                   command=self._accion_comprimir
                   ).grid(row=4, column=0, columnspan=4, sticky="ew", pady=(18, 0), ipady=6)

        f.rowconfigure(1, weight=1)
        for i in range(4):
            f.columnconfigure(i, weight=1)

    # ------------------ Tab 2: Descomprimir ------------------
    def _tab_descomprimir(self):
        f = ttk.Frame(self.nb, padding=16)
        self.nb.add(f, text="📂  Descomprimir")

        ttk.Label(f, text="Archivo comprimido:",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.ent_entrada_d = ttk.Entry(f)
        self.ent_entrada_d.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(f, text="Examinar…",
                   command=self._elegir_entrada_d).grid(row=1, column=1)

        ttk.Label(f, text="Carpeta de destino:",
                  font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(12, 0))
        self.ent_salida_d = ttk.Entry(f)
        self.ent_salida_d.grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(f, text="Examinar…",
                   command=self._elegir_salida_d).grid(row=3, column=1)

        ttk.Label(f, text="🔒 Contraseña (si aplica):").grid(row=4, column=0, sticky="w", pady=(12, 0))
        self.ent_pass_d = ttk.Entry(f, show="•")
        self.ent_pass_d.grid(row=5, column=0, sticky="ew", padx=(0, 8))

        ttk.Button(f, text="📤  DESCOMPRIMIR AHORA", style="Accent.TButton",
                   command=self._accion_descomprimir
                   ).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(20, 0), ipady=6)

        nota = ("Formatos soportados:  .luc · .zip · .7z · .tar · "
                ".tar.gz · .tar.bz2 · .tar.xz · .xz · .tgz · .txz\n"
                "Se detecta automáticamente por la extensión.")
        ttk.Label(f, text=nota, foreground=self.colores["fg2"],
                  font=("Segoe UI", 9)).grid(row=7, column=0, columnspan=2,
                                             sticky="w", pady=(20, 0))
        f.columnconfigure(0, weight=1)

    # ------------------ Tab 3: Explorar ------------------
    def _tab_explorar(self):
        f = ttk.Frame(self.nb, padding=16)
        self.nb.add(f, text="🔍  Explorar")

        ttk.Label(f, text="Buscar dentro de un archivo comprimido (sin extraerlo)",
                  font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=3,
                                                     sticky="w", pady=(0, 10))

        ttk.Label(f, text="Archivo:").grid(row=1, column=0, sticky="w")
        self.ent_expl = ttk.Entry(f)
        self.ent_expl.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(0, 8))
        ttk.Button(f, text="Examinar…",
                   command=lambda: self._set_entry(self.ent_expl,
                                                   filedialog.askopenfilename())
                   ).grid(row=2, column=2)

        ttk.Label(f, text="Texto a buscar:").grid(row=3, column=0, sticky="w", pady=(12, 0))
        self.ent_patron = ttk.Entry(f)
        self.ent_patron.grid(row=4, column=0, columnspan=2, sticky="ew", padx=(0, 8))
        ttk.Button(f, text="🔎 Buscar",
                   command=self._accion_buscar).grid(row=4, column=2)

        self.txt_result = tk.Text(f, height=14, bg=self.colores["entry"],
                                  fg=self.colores["fg"],
                                  insertbackground=self.colores["fg"],
                                  font=("Consolas", 9), wrap="word",
                                  highlightthickness=1,
                                  highlightbackground=self.colores["border"])
        self.txt_result.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(14, 0))
        self._registrar_widget_tema(self.txt_result)

        f.rowconfigure(5, weight=1)
        f.columnconfigure(0, weight=1)

    # ------------------ Tab 4: Historial ------------------
    def _tab_historial(self):
        f = ttk.Frame(self.nb, padding=16)
        self.nb.add(f, text="🕘  Historial")

        ttk.Label(f, text="Últimas operaciones",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))

        self.lst_hist = tk.Listbox(f, bg=self.colores["entry"], fg=self.colores["fg"],
                                   selectbackground=self.colores["accent"],
                                   highlightthickness=1,
                                   highlightbackground=self.colores["border"],
                                   font=("Consolas", 9))
        self.lst_hist.pack(fill="both", expand=True)
        self._registrar_widget_tema(self.lst_hist)

        ttk.Button(f, text="🗑 Limpiar historial",
                   command=self._limpiar_hist).pack(anchor="e", pady=(8, 0))

        self._refrescar_hist()

    # ------------------ Tab 5: Configuración ------------------
    def _tab_config(self):
        f = ttk.Frame(self.nb, padding=16)
        self.nb.add(f, text="⚙️  Configuración")

        ttk.Label(f, text="Preferencias generales",
                  font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2,
                                                     sticky="w", pady=(0, 12))

        ttk.Label(f, text="Tema:").grid(row=1, column=0, sticky="w", pady=4)
        self.cmb_tema = ttk.Combobox(f, values=list(TEMAS.keys()), state="readonly", width=20)
        self.cmb_tema.set(self.cfg["tema"])
        self.cmb_tema.grid(row=1, column=1, sticky="w", padx=8)

        ttk.Label(f, text="Formato por defecto:").grid(row=2, column=0, sticky="w", pady=4)
        self.cmb_def = ttk.Combobox(f, values=list(FORMATOS_COMPRIMIR.keys()),
                                    state="readonly", width=40)
        self.cmb_def.set(next(k for k, v in FORMATOS_COMPRIMIR.items()
                              if v == self.cfg["formato_preferido"]))
        self.cmb_def.grid(row=2, column=1, sticky="w", padx=8)

        ttk.Button(f, text="💾 Guardar preferencias",
                   command=self._guardar_prefs
                   ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(20, 0))

        dep = ttk.LabelFrame(f, text="Dependencias detectadas", padding=12)
        dep.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(24, 0))
        deps = [
            ("LZMA (estándar)", "✔ disponible"),
            ("ZIP (estándar)", "✔ disponible"),
            ("TAR (estándar)", "✔ disponible"),
            ("7Z (py7zr)", "✔ disponible" if HAS_7Z else "✘  pip install py7zr"),
            ("ZIP AES (pyzipper)", "✔ disponible" if HAS_ZIP_CRYPTO else "✘  pip install pyzipper"),
            ("Drag & Drop (tkinterdnd2)", "✔ disponible" if HAS_DND else "✘  pip install tkinterdnd2"),
        ]
        for i, (n, s) in enumerate(deps):
            ttk.Label(dep, text=f"• {n}").grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(dep, text=s,
                      foreground=self.colores["success"] if "✔" in s else self.colores["error"]
                      ).grid(row=i, column=1, sticky="w", padx=12, pady=2)

    # =========================================================
    # Sistema de tema en vivo
    # =========================================================
    def _registrar_widget_tema(self, widget):
        self._widgets_tema.append(widget)

    def _aplicar_tema_en_vivo(self):
        c = TEMAS[self.cfg["tema"]]
        self.configure(bg=c["bg"])

        # Widgets tk puros
        for w in self._widgets_tema:
            try:
                tipo = w.winfo_class()
                if tipo in ("Text", "Listbox", "Entry"):
                    w.configure(bg=c["entry"], fg=c["fg"], insertbackground=c["fg"])
                    if tipo == "Listbox":
                        w.configure(selectbackground=c["accent"])
                else:
                    w.configure(bg=c["bg"])
                    try:
                        w.configure(fg=c["fg"])
                    except tk.TclError:
                        pass
            except tk.TclError:
                pass

        # Estilos ttk
        s = ttk.Style(self)
        s.configure("TFrame", background=c["bg"])
        s.configure("TLabel", background=c["bg"], foreground=c["fg"])
        s.configure("Header.TFrame", background=c["bg2"])
        s.configure("Header.TLabel", background=c["bg2"], foreground=c["fg"])
        s.configure("Sub.TLabel", background=c["bg2"], foreground=c["fg2"])
        s.configure("TNotebook", background=c["bg"])
        s.configure("TNotebook.Tab", background=c["bg2"], foreground=c["fg2"])
        s.map("TNotebook.Tab",
              background=[("selected", c["accent"])],
              foreground=[("selected", "#ffffff")])
        s.configure("TButton", background=c["bg2"], foreground=c["fg"])
        s.map("TButton", background=[("active", c["border"])])
        s.configure("Accent.TButton", background=c["accent"], foreground="#ffffff")
        s.map("Accent.TButton", background=[("active", c["accent2"])])
        s.configure("TLabelframe", background=c["bg"], foreground=c["fg"])
        s.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"])
        s.configure("TEntry", fieldbackground=c["entry"], foreground=c["fg"])
        s.configure("TCombobox", fieldbackground=c["entry"], foreground=c["fg"])
        s.configure("Horizontal.TProgressbar",
                    background=c["accent"], troughcolor=c["bg2"])

        self.btn_tema.configure(text=self._txt_tema())
        self.status.set("Tema aplicado.")

    def _toggle_tema(self):
        self.cfg["tema"] = "claro" if self.cfg["tema"] == "oscuro" else "oscuro"
        self.colores = TEMAS[self.cfg["tema"]]
        guardar_config(self.cfg)
        self._aplicar_tema_en_vivo()

    # =========================================================
    # Acciones
    # =========================================================
    def _add_archivos(self):
        fs = filedialog.askopenfilenames(title="Selecciona archivos")
        for p in fs:
            self.lst_comp.insert("end", p)

    def _add_carpeta(self):
        d = filedialog.askdirectory(title="Selecciona carpeta")
        if d:
            self.lst_comp.insert("end", d)

    def _quitar_sel(self):
        for i in reversed(self.lst_comp.curselection()):
            self.lst_comp.delete(i)

    def _elegir_destino_c(self):
        fmt = FORMATOS_COMPRIMIR[self.cmb_formato.get()]
        sugerido = "comprimido" + fmt
        p = filedialog.asksaveasfilename(
            title="Guardar como", defaultextension=fmt,
            initialfile=sugerido,
            filetypes=[("Todos", "*.*")])
        if p:
            self._set_entry(self.ent_destino_c, p)

    def _elegir_entrada_d(self):
        p = filedialog.askopenfilename(
            title="Archivo comprimido",
            filetypes=[("Comprimidos", "*.luc *.zip *.7z *.tar *.gz *.bz2 *.xz *.tgz *.txz"),
                       ("Todos", "*.*")])
        self._set_entry(self.ent_entrada_d, p)
        if p and not self.ent_salida_d.get():
            self._set_entry(self.ent_salida_d,
                            os.path.join(os.path.dirname(p),
                                         os.path.splitext(os.path.basename(p))[0] + "_extraido"))

    def _elegir_salida_d(self):
        d = filedialog.askdirectory(title="Carpeta de destino")
        self._set_entry(self.ent_salida_d, d)

    def _set_entry(self, entry, valor):
        if valor:
            entry.delete(0, "end")
            entry.insert(0, valor)

    def _cargar_perfil(self, *a):
        perfil = self.cfg["perfiles"].get(self.cmb_perfil.get())
        if not perfil:
            return
        fmt = perfil.get("formato")
        for k, v in FORMATOS_COMPRIMIR.items():
            if v == fmt:
                self.cmb_formato.set(k); break
        if perfil.get("preset") in PRESETS:
            self.cmb_preset.set(perfil["preset"])
        if perfil.get("dict_size") in DICT_SIZES:
            self.cmb_dict.set(perfil["dict_size"])
        if perfil.get("split_mb"):
            self.ent_split.delete(0, "end")
            self.ent_split.insert(0, str(perfil["split_mb"]))

    # ------------------ COMPRIMIR ------------------
    def _accion_comprimir(self):
        origenes = list(self.lst_comp.get(0, "end"))
        if not origenes:
            messagebox.showwarning("Sin entradas", "Añade archivos o carpetas.")
            return

        destino = self.ent_destino_c.get().strip()
        if not destino:
            messagebox.showwarning("Falta destino", "Indica dónde guardar el archivo.")
            return

        # Aviso si el archivo ya está comprimido
        if _parece_comprimido(origenes):
            if not messagebox.askyesno(
                "Posible compresión inútil",
                "Los archivos seleccionados ya están comprimidos "
                "(.jpg, .mp4, .zip, .pdf, .docx…).\n\n"
                "LZMA no encontrará patrones que reducir y el resultado "
                "será casi del mismo tamaño.\n\n"
                "¿Quieres continuar de todas formas?"):
                return

        fmt_key = self.cmb_formato.get()
        extension = FORMATOS_COMPRIMIR[fmt_key]
        password = self.ent_pass.get() or None

        try:
            split_mb = int(self.ent_split.get() or "0")
        except ValueError:
            split_mb = 0

        if not destino.lower().endswith(extension):
            destino += extension

        self.cfg["formato_preferido"] = extension
        self.cfg["preset"] = self.cmb_preset.get()
        self.cfg["dict_size"] = self.cmb_dict.get()
        self.cfg["perfil_actual"] = self.cmb_perfil.get()
        guardar_config(self.cfg)

        self.status.set(f"Comprimiendo en formato {extension} …")
        self.pb["value"] = 0

        def worker():
            try:
                t0 = time.time()
                if extension == ".luc":
                    temp_tar = None
                    a_comprimir = origenes
                    if any(os.path.isdir(p) for p in origenes):
                        tmp = os.path.join(os.path.dirname(destino), "_tmp_luc.tar")
                        comprimir_tar(origenes, tmp, self.cfg, modo="w")
                        a_comprimir = [tmp]
                        temp_tar = tmp
                    comprimir_luc(a_comprimir, destino, self.cfg,
                                  progress=self._progress_cb)
                    if temp_tar:
                        os.remove(temp_tar)

                elif extension == ".zip":
                    comprimir_zip(origenes, destino, self.cfg,
                                  password=password, progress=self._progress_cb)
                elif extension == ".7z":
                    comprimir_7z(origenes, destino, self.cfg,
                                 password=password, progress=self._progress_cb)
                elif extension == ".tar":
                    comprimir_tar(origenes, destino, self.cfg, modo="w",
                                  progress=self._progress_cb)
                elif extension == ".tar.gz":
                    comprimir_tar(origenes, destino, self.cfg, modo="w:gz",
                                  progress=self._progress_cb)
                elif extension == ".tar.bz2":
                    comprimir_tar(origenes, destino, self.cfg, modo="w:bz2",
                                  progress=self._progress_cb)
                elif extension == ".tar.xz":
                    comprimir_tar(origenes, destino, self.cfg, modo="w:xz",
                                  progress=self._progress_cb)

                partes = []
                if split_mb > 0 and os.path.getsize(destino) > split_mb * 1024 * 1024:
                    partes = dividir_archivo(destino, split_mb)

                dt = time.time() - t0
                tam_orig = sum(_listar(p)[1] for p in origenes)
                tam_comp = os.path.getsize(destino) if os.path.exists(destino) else \
                    sum(os.path.getsize(p) for p in partes)
                ratio = (1 - tam_comp / tam_orig) * 100 if tam_orig else 0

                self._hist_append({
                    "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "op": "COMPRIMIR", "formato": extension,
                    "entrada": ", ".join(os.path.basename(p) for p in origenes)[:80],
                    "salida": os.path.basename(destino),
                    "orig": humano(tam_orig), "comp": humano(tam_comp),
                    "ratio": f"{ratio:.1f}%", "tiempo": f"{dt:.1f}s",
                })

                self.after(0, lambda: self.status.set(
                    f"✔ Comprimido en {dt:.1f}s  →  ratio {ratio:.1f}%  ({humano(tam_comp)})"))
                self.after(0, lambda: self.pb.configure(value=100))
                self.after(0, lambda: messagebox.showinfo(
                    "¡Hecho!",
                    f"Archivo creado:\n{destino}\n\n"
                    f"Original:  {humano(tam_orig)}\n"
                    f"Comprimido: {humano(tam_comp)}\n"
                    f"Ahorro:    {ratio:.2f}%\n"
                    f"Tiempo:    {dt:.1f} s"))

            except Exception as e:
                self.after(0, lambda: self.status.set(f"✘ Error: {e}"))
                self.after(0, lambda: messagebox.showerror("Error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------ DESCOMPRIMIR ------------------
    def _accion_descomprimir(self):
        origen = self.ent_entrada_d.get().strip()
        destino = self.ent_salida_d.get().strip()
        password = self.ent_pass_d.get() or None

        if not origen or not os.path.isfile(origen):
            messagebox.showwarning("Falta archivo", "Selecciona un archivo válido.")
            return
        if not destino:
            messagebox.showwarning("Falta destino", "Indica dónde extraer.")
            return

        self.status.set("Descomprimiendo…")
        self.pb["value"] = 0

        def worker():
            try:
                t0 = time.time()
                descomprimir(origen, destino, password=password)
                dt = time.time() - t0
                self._hist_append({
                    "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "op": "DESCOMPRIMIR", "formato": os.path.splitext(origen)[1],
                    "entrada": os.path.basename(origen),
                    "salida": destino, "tiempo": f"{dt:.1f}s",
                })
                self.after(0, lambda: self.status.set(f"✔ Extraído en {dt:.1f}s"))
                self.after(0, lambda: self.pb.configure(value=100))
                self.after(0, lambda: messagebox.showinfo("¡Hecho!",
                                                          f"Contenido extraído en:\n{destino}"))
            except Exception as e:
                self.after(0, lambda: self.status.set(f"✘ Error: {e}"))
                self.after(0, lambda: messagebox.showerror("Error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------ BUSCAR ------------------
    def _accion_buscar(self):
        ruta = self.ent_expl.get().strip()
        patron = self.ent_patron.get().strip()
        if not ruta or not os.path.isfile(ruta) or not patron:
            messagebox.showwarning("Faltan datos", "Indica archivo y patrón.")
            return

        self.txt_result.delete("1.0", "end")
        self.txt_result.insert("end", "🔎 Buscando…\n")
        self.status.set("Buscando…")

        def worker():
            res = buscar_en_archivo(ruta, patron)
            def _upd():
                self.txt_result.delete("1.0", "end")
                if not res:
                    self.txt_result.insert("end", "Sin coincidencias.\n")
                else:
                    self.txt_result.insert("end",
                                           f"✔ {len(res)} coincidencia(s) encontradas:\n\n")
                    for m, i, l in res[:500]:
                        self.txt_result.insert("end", f"[{m}:{i}]  {l}\n")
                self.status.set(f"Búsqueda finalizada ({len(res)} resultados).")
            self.after(0, _upd)

        threading.Thread(target=worker, daemon=True).start()

    # ------------------ Historial ------------------
    def _hist_append(self, item):
        self.cfg["historial"].insert(0, item)
        self.cfg["historial"] = self.cfg["historial"][:200]
        guardar_config(self.cfg)
        self.after(0, self._refrescar_hist)

    def _refrescar_hist(self):
        self.lst_hist.delete(0, "end")
        for it in self.cfg["historial"]:
            linea = (f"{it['fecha']}  {it['op']:<12} {it.get('formato',''):<8}  "
                     f"{it.get('entrada','')[:40]}  →  {it.get('salida','')[:40]}  "
                     f"{it.get('ratio','')} {it.get('tiempo','')}")
            self.lst_hist.insert("end", linea)

    def _limpiar_hist(self):
        if messagebox.askyesno("Confirmar", "¿Borrar todo el historial?"):
            self.cfg["historial"] = []
            guardar_config(self.cfg)
            self._refrescar_hist()

    # ------------------ Config ------------------
    def _guardar_prefs(self):
        tema_nuevo = self.cmb_tema.get()
        self.cfg["formato_preferido"] = FORMATOS_COMPRIMIR[self.cmb_def.get()]
        if tema_nuevo != self.cfg["tema"]:
            self.cfg["tema"] = tema_nuevo
            self.colores = TEMAS[tema_nuevo]
            guardar_config(self.cfg)
            self._aplicar_tema_en_vivo()
            messagebox.showinfo("Guardado", "Tema y preferencias aplicados.")
        else:
            guardar_config(self.cfg)
            messagebox.showinfo("Guardado", "Preferencias guardadas.")

    def _acerca_de(self):
        messagebox.showinfo(
            f"{APP_NAME} v{APP_VERSION}",
            f"{APP_NAME} — suite de compresión multi-formato.\n\n"
            "• Formatos: LUC, ZIP, 7Z, TAR, TAR.GZ, TAR.BZ2, TAR.XZ\n"
            "• Carpetas, contraseñas AES-256, split, búsqueda, historial.\n"
            f"• 7Z soportado: {'sí' if HAS_7Z else 'no (pip install py7zr)'}\n"
            f"• AES-256 soportado: {'sí' if HAS_ZIP_CRYPTO else 'no (pip install pyzipper)'}\n"
            f"• Drag & drop: {'sí' if HAS_DND else 'no (pip install tkinterdnd2)'}")

    # -------------------------------------------------- misc
    def _registrar_dnd(self):
        if not HAS_DND:
            return
        try:
            self.lst_comp.drop_target_register(DND_FILES)
            self.lst_comp.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

    def _on_drop(self, event):
        rutas = self.tk.splitlist(event.data)
        for r in rutas:
            self.lst_comp.insert("end", r)

    def _aplicar_icono(self):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        for n in ("icono.ico", "app.ico", "compresorpro.ico"):
            r = os.path.join(base, n)
            if os.path.isfile(r):
                try:
                    self.iconbitmap(r); return
                except Exception:
                    pass

    def _progress_cb(self, actual, total):
        pct = (actual / total * 100) if total else 0
        self.after(0, lambda: self.pb.configure(value=pct))
        self.after(0, lambda: self.status.set(
            f"Procesando…  {pct:5.1f}%  ({humano(actual)} / {humano(total)})"))


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    app = CompresorPRO()
    app.mainloop()