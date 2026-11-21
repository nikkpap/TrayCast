#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrayCast v1.0.1
-----------------------------------------------------------------
Καιρός στη γραμμή εργασιών των Windows (δίπλα στην αλλαγή γλώσσας).

  • Μονό κλικ στο εικονίδιο  -> γρήγορο αναδυόμενο παράθυρο (flyout)
  • Διπλό κλικ               -> πλήρης εφαρμογή
  • Δεξί κλικ                -> μενού (τοποθεσίες, ρυθμίσεις, έξοδος)
  • Μεσαίο κλικ              -> ανανέωση

Δεδομένα: Open-Meteo.com (δωρεάν, χωρίς κλειδί API, CC BY 4.0)
Developer: Nikolaos K. Paridis (aka nikkpap) — ALU DEV TEAM

Οι εξαρτήσεις (PyQt6) εγκαθίστανται αυτόματα στην πρώτη εκκίνηση.
"""

APP_NAME = "TrayCast"
APP_VERSION = "1.0.1"
APP_AUTHOR = "Nikolaos K. Paridis (aka nikkpap)"
APP_TEAM = "ALU DEV TEAM"

# =================================================================
#  1. Αυτόματη εγκατάσταση εξαρτήσεων (μόνο stdlib εδώ)
# =================================================================
import os
import sys
import subprocess
import importlib

REQUIRED = [("PyQt6", "PyQt6")]


def _ensure_dependencies():
    missing = []
    for mod, pip_name in REQUIRED:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pip_name)
    if not missing:
        return

    py = sys.executable
    if py.lower().endswith("pythonw.exe"):
        cand = py[:-len("pythonw.exe")] + "python.exe"
        if os.path.exists(cand):
            py = cand
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW

    root = None
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title(f"{APP_NAME} – Εγκατάσταση")
        root.geometry("440x130")
        root.resizable(False, False)
        root.configure(bg="#1d2b44")
        tk.Label(root, text="Πρώτη εκκίνηση: εγκατάσταση απαραίτητων πακέτων…",
                 fg="white", bg="#1d2b44", font=("Segoe UI", 11)).pack(pady=(26, 6))
        tk.Label(root, text=", ".join(missing) + "  (μπορεί να πάρει 1–2 λεπτά)",
                 fg="#9fc3ff", bg="#1d2b44", font=("Segoe UI", 9)).pack()
        root.update()
    except Exception:
        root = None

    ok = False
    for extra in ([], ["--user"]):
        try:
            r = subprocess.call([py, "-m", "pip", "install", "--disable-pip-version-check", *extra, *missing],
                                creationflags=flags)
            if r == 0:
                ok = True
                break
        except Exception:
            pass

    if root is not None:
        try:
            root.destroy()
        except Exception:
            pass

    importlib.invalidate_caches()
    try:
        import site
        usp = site.getusersitepackages()
        if usp and usp not in sys.path and os.path.isdir(usp):
            sys.path.append(usp)
    except Exception:
        pass

    still = []
    for mod, pip_name in REQUIRED:
        try:
            importlib.import_module(mod)
        except ImportError:
            still.append(pip_name)
    if still or not ok:
        if not still:
            return
        msg = ("Δεν ήταν δυνατή η αυτόματη εγκατάσταση των πακέτων:\n  " + ", ".join(still) +
               "\n\nΆνοιξε τη γραμμή εντολών (cmd) και γράψε:\n  pip install " + " ".join(still))
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk(); r.withdraw()
            messagebox.showerror(APP_NAME, msg)
            r.destroy()
        except Exception:
            print(msg)
        sys.exit(1)


_ensure_dependencies()

# =================================================================
#  2. Imports
# =================================================================
import json
import math
import time
import urllib.request
import urllib.parse
from datetime import datetime, date

from PyQt6.QtCore import (Qt, QTimer, QThread, pyqtSignal, QObject, QPointF, QRectF, QPoint,
                          QRect, QSize)
from PyQt6.QtGui import (QIcon, QPixmap, QPainter, QColor, QPen, QFont, QFontMetrics,
                         QLinearGradient, QRadialGradient, QPainterPath, QAction, QGuiApplication,
                         QCursor, QPolygonF, QActionGroup)
from PyQt6.QtWidgets import (QApplication, QWidget, QMainWindow, QSystemTrayIcon, QMenu,
                             QPushButton, QLineEdit, QLabel, QHBoxLayout, QVBoxLayout,
                             QGridLayout, QScrollArea, QDialog, QFormLayout, QComboBox,
                             QSpinBox, QCheckBox, QDialogButtonBox, QMessageBox, QSizePolicy,
                             QFrame)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

# =================================================================
#  3. Ρυθμίσεις / αρχεία
# =================================================================
IS_WIN = os.name == "nt"
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"), "TrayCast")
os.makedirs(DATA_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
CACHE_FILE = os.path.join(DATA_DIR, "cache.json")
INSTANCE_KEY = "TrayCast_nikkpap_single_instance"
FONT_FAMILY = "Segoe UI" if IS_WIN else ""

DEFAULT_LOCATION = {"name": "Πτολεμαΐδα", "admin1": "Δυτική Μακεδονία", "country": "Ελλάδα",
                    "lat": 40.5144, "lon": 21.6787}

DEFAULT_SETTINGS = {
    "lang": "el",
    "temp_unit": "celsius",      # celsius | fahrenheit
    "wind_unit": "kmh",          # kmh | ms | mph | kn
    "interval_min": 15,
    "tray_mode": "temp",         # temp | icon
    "autostart": False,
    "rain_notify": True,
    "location": DEFAULT_LOCATION,
    "recent": [DEFAULT_LOCATION],
    "first_close_hint": True,
}


def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            s.update(json.load(f))
    except Exception:
        pass
    return s


def save_settings(s):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_autostart(enable):
    if not IS_WIN:
        return
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, "ALU_WeatherTray")   # παλιό όνομα (v1.0.0)
        except FileNotFoundError:
            pass
        if enable:
            exe = sys.executable
            if exe.lower().endswith("python.exe"):
                w = exe[:-len("python.exe")] + "pythonw.exe"
                if os.path.exists(w):
                    exe = w
            winreg.SetValueEx(key, "TrayCast", 0, winreg.REG_SZ,
                              f'"{exe}" "{os.path.abspath(__file__)}" --tray')
        else:
            try:
                winreg.DeleteValue(key, "TrayCast")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


# =================================================================
#  4. Μεταφράσεις
# =================================================================
T = {
    "el": {
        "open_app": "Άνοιγμα εφαρμογής", "refresh": "Ανανέωση", "settings": "Ρυθμίσεις",
        "about": "Σχετικά", "exit": "Έξοδος", "locations": "Τοποθεσίες",
        "search_ph": "Αναζήτηση πόλης… (π.χ. Κοζάνη, Θεσσαλονίκη)", "search": "Αναζήτηση",
        "no_results": "Δεν βρέθηκαν αποτελέσματα", "searching": "Αναζήτηση…",
        "loading": "Φόρτωση δεδομένων…", "updated": "Ενημέρωση", "now": "Τώρα", "today": "Σήμερα",
        "feels": "Αισθητή", "hi": "Μέγ.", "lo": "Ελάχ.",
        "hourly": "ΩΡΙΑΙΑ ΠΡΟΓΝΩΣΗ (24 ΩΡΕΣ)", "daily": "ΠΡΟΓΝΩΣΗ 7 ΗΜΕΡΩΝ",
        "t_feels": "ΑΙΣΘΗΤΗ", "feels_warmer": "Πιο ζεστά από την πραγματική",
        "feels_colder": "Πιο κρύα από την πραγματική", "feels_same": "Ίδια με την πραγματική",
        "t_hum": "ΥΓΡΑΣΙΑ", "dew": "Σημείο δρόσου",
        "t_wind": "ΑΝΕΜΟΣ", "gusts": "Ριπές",
        "t_press": "ΠΙΕΣΗ", "sea_level": "Στάθμη θάλασσας",
        "t_cloud": "ΝΕΦΟΚΑΛΥΨΗ", "visibility": "Ορατότητα",
        "t_uv": "ΔΕΙΚΤΗΣ UV (ΜΕΓ.)", "uv_levels": ["Χαμηλός", "Μέτριος", "Υψηλός", "Πολύ υψηλός", "Ακραίος"],
        "t_sun": "ΑΝΑΤΟΛΗ / ΔΥΣΗ", "sunset": "Δύση", "sunrise": "Ανατολή",
        "t_aqi": "ΠΟΙΟΤΗΤΑ ΑΕΡΑ",
        "aqi_levels": ["Καλή", "Ικανοποιητική", "Μέτρια", "Κακή", "Πολύ κακή", "Εξαιρ. κακή"],
        "na": "—",
        "days": ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"],
        "days_s": ["Δευ", "Τρί", "Τετ", "Πέμ", "Παρ", "Σάβ", "Κυρ"],
        "compass": ["Β", "ΒΑ", "Α", "ΝΑ", "Ν", "ΝΔ", "Δ", "ΒΔ"],
        "err_net": "Σφάλμα σύνδεσης – νέα προσπάθεια σε 1 λεπτό",
        "running_tray": "Η εφαρμογή συνεχίζει να τρέχει στη γραμμή εργασιών.\n"
                        "Μονό κλικ: γρήγορη προβολή · Διπλό κλικ: εφαρμογή · Δεξί κλικ: μενού",
        "rain_t": "Έρχεται βροχή ☔", "rain_msg": "Πιθανότητα υετού {p}% γύρω στις {h} στην περιοχή {c}.",
        "lang": "Γλώσσα", "temp_unit": "Θερμοκρασία", "wind_unit": "Ταχύτητα ανέμου",
        "interval": "Αυτόματη ανανέωση κάθε", "minutes": " λεπτά",
        "tray_show": "Εικονίδιο γραμμής εργασιών", "tray_temp": "Θερμοκρασία (αριθμός)",
        "tray_icon": "Εικονίδιο καιρού", "autostart": "Εκκίνηση μαζί με τα Windows",
        "rain_notify": "Ειδοποίηση όταν έρχεται βροχή", "save": "Αποθήκευση", "cancel": "Άκυρο",
        "data_by": "Δεδομένα: Open-Meteo.com (CC BY 4.0)",
        "hint": "Μονό κλικ στο εικονίδιο: γρήγορη προβολή · Διπλό κλικ: εφαρμογή",
        "about_text": "<h3>{app} v{ver}</h3>"
                      "<p>Καιρός στη γραμμή εργασιών με δεδομένα από το "
                      "<a href='https://open-meteo.com'>Open-Meteo.com</a> (CC BY 4.0).</p>"
                      "<p><b>Μονό κλικ</b>: γρήγορη προβολή<br><b>Διπλό κλικ</b>: πλήρης εφαρμογή<br>"
                      "<b>Δεξί κλικ</b>: μενού<br><b>Μεσαίο κλικ</b>: ανανέωση</p>"
                      "<p>Developer: <b>{author}</b><br>{team}</p>",
        "lang_toggle": "EN",
    },
    "en": {
        "open_app": "Open app", "refresh": "Refresh", "settings": "Settings",
        "about": "About", "exit": "Exit", "locations": "Locations",
        "search_ph": "Search city… (e.g. Athens, London)", "search": "Search",
        "no_results": "No results found", "searching": "Searching…",
        "loading": "Loading data…", "updated": "Updated", "now": "Now", "today": "Today",
        "feels": "Feels like", "hi": "H", "lo": "L",
        "hourly": "HOURLY FORECAST (24 H)", "daily": "7-DAY FORECAST",
        "t_feels": "FEELS LIKE", "feels_warmer": "Warmer than actual",
        "feels_colder": "Colder than actual", "feels_same": "Similar to actual",
        "t_hum": "HUMIDITY", "dew": "Dew point",
        "t_wind": "WIND", "gusts": "Gusts",
        "t_press": "PRESSURE", "sea_level": "Mean sea level",
        "t_cloud": "CLOUD COVER", "visibility": "Visibility",
        "t_uv": "UV INDEX (MAX)", "uv_levels": ["Low", "Moderate", "High", "Very high", "Extreme"],
        "t_sun": "SUNRISE / SUNSET", "sunset": "Sunset", "sunrise": "Sunrise",
        "t_aqi": "AIR QUALITY",
        "aqi_levels": ["Good", "Fair", "Moderate", "Poor", "Very poor", "Extremely poor"],
        "na": "—",
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "days_s": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "compass": ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
        "err_net": "Connection error – retrying in 1 minute",
        "running_tray": "The app keeps running in the taskbar.\n"
                        "Single click: quick view · Double click: app · Right click: menu",
        "rain_t": "Rain is coming ☔", "rain_msg": "{p}% chance of precipitation around {h} in {c}.",
        "lang": "Language", "temp_unit": "Temperature", "wind_unit": "Wind speed",
        "interval": "Auto refresh every", "minutes": " min",
        "tray_show": "Taskbar icon", "tray_temp": "Temperature (number)",
        "tray_icon": "Weather icon", "autostart": "Start with Windows",
        "rain_notify": "Notify when rain is coming", "save": "Save", "cancel": "Cancel",
        "data_by": "Data: Open-Meteo.com (CC BY 4.0)",
        "hint": "Single click the tray icon: quick view · Double click: app",
        "about_text": "<h3>{app} v{ver}</h3>"
                      "<p>Weather in your taskbar, powered by "
                      "<a href='https://open-meteo.com'>Open-Meteo.com</a> (CC BY 4.0).</p>"
                      "<p><b>Single click</b>: quick view<br><b>Double click</b>: full app<br>"
                      "<b>Right click</b>: menu<br><b>Middle click</b>: refresh</p>"
                      "<p>Developer: <b>{author}</b><br>{team}</p>",
        "lang_toggle": "ΕΛ",
    },
}

WMO = {
    0: ("Αίθριος", "Clear sky"), 1: ("Κυρίως αίθριος", "Mainly clear"),
    2: ("Μερική συννεφιά", "Partly cloudy"), 3: ("Συννεφιά", "Overcast"),
    45: ("Ομίχλη", "Fog"), 48: ("Παγωμένη ομίχλη", "Rime fog"),
    51: ("Ασθενές ψιχάλισμα", "Light drizzle"), 53: ("Ψιχάλισμα", "Drizzle"),
    55: ("Πυκνό ψιχάλισμα", "Dense drizzle"), 56: ("Παγωμένο ψιχάλισμα", "Freezing drizzle"),
    57: ("Παγωμένο ψιχάλισμα", "Freezing drizzle"), 61: ("Ασθενής βροχή", "Light rain"),
    63: ("Βροχή", "Rain"), 65: ("Ισχυρή βροχή", "Heavy rain"),
    66: ("Παγωμένη βροχή", "Freezing rain"), 67: ("Ισχυρή παγωμένη βροχή", "Heavy freezing rain"),
    71: ("Ασθενής χιονόπτωση", "Light snow"), 73: ("Χιονόπτωση", "Snow"),
    75: ("Ισχυρή χιονόπτωση", "Heavy snow"), 77: ("Χιονόκοκκοι", "Snow grains"),
    80: ("Ασθενείς μπόρες", "Light showers"), 81: ("Μπόρες", "Showers"),
    82: ("Ισχυρές μπόρες", "Violent showers"), 85: ("Μπόρες χιονιού", "Snow showers"),
    86: ("Ισχυρές μπόρες χιονιού", "Heavy snow showers"), 95: ("Καταιγίδα", "Thunderstorm"),
    96: ("Καταιγίδα με χαλάζι", "Thunderstorm with hail"),
    99: ("Ισχυρή καταιγίδα με χαλάζι", "Severe thunderstorm with hail"),
}


class I18n:
    lang = "el"


def tr(key):
    return T.get(I18n.lang, T["el"]).get(key, T["el"].get(key, key))


def wmo_text(code):
    t = WMO.get(int(code or 0), ("—", "—"))
    return t[0] if I18n.lang == "el" else t[1]


def wmo_kind(code):
    c = int(code or 0)
    if c in (0, 1):
        return "clear"
    if c == 2:
        return "partly"
    if c == 3:
        return "cloudy"
    if c in (45, 48):
        return "fog"
    if 51 <= c <= 57:
        return "drizzle"
    if 61 <= c <= 67:
        return "rain"
    if 80 <= c <= 82:
        return "showers"
    if 71 <= c <= 77 or c in (85, 86):
        return "snow"
    if c >= 95:
        return "thunder"
    return "cloudy"


# =================================================================
#  5. Open-Meteo API
# =================================================================
UA = {"User-Agent": f"{APP_NAME}/{APP_VERSION} (Windows tray weather app)"}


def http_json(url, params, timeout=20):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_forecast(loc, settings):
    params = {
        "latitude": loc["lat"], "longitude": loc["lon"],
        "current": ",".join([
            "temperature_2m", "relative_humidity_2m", "apparent_temperature", "is_day",
            "precipitation", "weather_code", "cloud_cover", "pressure_msl", "wind_speed_10m",
            "wind_direction_10m", "wind_gusts_10m", "dew_point_2m", "visibility"]),
        "hourly": "temperature_2m,precipitation_probability,weather_code,is_day",
        "daily": ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min", "sunrise", "sunset",
            "uv_index_max", "precipitation_sum", "precipitation_probability_max",
            "wind_speed_10m_max"]),
        "timezone": "auto", "forecast_days": 7,
        "temperature_unit": settings.get("temp_unit", "celsius"),
        "wind_speed_unit": settings.get("wind_unit", "kmh"),
    }
    return http_json("https://api.open-meteo.com/v1/forecast", params)


def fetch_air(loc):
    params = {"latitude": loc["lat"], "longitude": loc["lon"],
              "current": "european_aqi,pm2_5,pm10", "timezone": "auto"}
    return http_json("https://air-quality-api.open-meteo.com/v1/air-quality", params)


def geocode(name, lang):
    params = {"name": name, "count": 10, "language": "el" if lang == "el" else "en", "format": "json"}
    d = http_json("https://geocoding-api.open-meteo.com/v1/search", params)
    out = []
    for r in d.get("results", []) or []:
        out.append({"name": r.get("name", ""), "admin1": r.get("admin1", ""),
                    "country": r.get("country", ""), "lat": r.get("latitude"),
                    "lon": r.get("longitude")})
    return out


class Fetcher(QThread):
    done = pyqtSignal(object, object)
    failed = pyqtSignal(str)

    def __init__(self, loc, settings):
        super().__init__()
        self.loc = dict(loc)
        self.settings = dict(settings)

    def run(self):
        try:
            raw = fetch_forecast(self.loc, self.settings)
        except Exception as e:
            self.failed.emit(str(e))
            return
        try:
            aq = fetch_air(self.loc)
        except Exception:
            aq = None
        self.done.emit(raw, aq)


class GeoSearch(QThread):
    results = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, text, lang):
        super().__init__()
        self.text, self.lang = text, lang

    def run(self):
        try:
            self.results.emit(geocode(self.text, self.lang))
        except Exception as e:
            self.failed.emit(str(e))


def _f(v, d=None):
    try:
        return float(v) if v is not None else d
    except Exception:
        return d


def parse_model(raw, aq, loc, settings):
    c = raw.get("current", {})
    cur_time = datetime.fromisoformat(c.get("time"))
    cur = {
        "time": cur_time, "temp": _f(c.get("temperature_2m"), 0.0),
        "feels": _f(c.get("apparent_temperature")), "hum": _f(c.get("relative_humidity_2m")),
        "dew": _f(c.get("dew_point_2m")), "code": int(c.get("weather_code") or 0),
        "is_day": bool(c.get("is_day", 1)), "wind": _f(c.get("wind_speed_10m")),
        "wdir": _f(c.get("wind_direction_10m")), "gust": _f(c.get("wind_gusts_10m")),
        "press": _f(c.get("pressure_msl")), "cloud": _f(c.get("cloud_cover")),
        "vis": _f(c.get("visibility")), "precip": _f(c.get("precipitation")),
    }
    h = raw.get("hourly", {})
    times = h.get("time", [])
    key = c.get("time", "")[:13]
    start = 0
    for i, t in enumerate(times):
        if t[:13] >= key:
            start = i
            break
    hours = []
    for i in range(start, min(start + 25, len(times))):
        hours.append({
            "t": datetime.fromisoformat(times[i]),
            "temp": _f(h["temperature_2m"][i], 0.0),
            "pop": _f((h.get("precipitation_probability") or [None] * len(times))[i], 0.0) or 0.0,
            "code": int(h["weather_code"][i] or 0),
            "is_day": bool(h["is_day"][i]),
        })
    if hours:
        hours[0]["temp"] = cur["temp"]
        hours[0]["code"] = cur["code"]
        hours[0]["is_day"] = cur["is_day"]
    d = raw.get("daily", {})
    days = []
    for i, ds in enumerate(d.get("time", [])):
        days.append({
            "d": date.fromisoformat(ds), "code": int(d["weather_code"][i] or 0),
            "tmax": _f(d["temperature_2m_max"][i], 0.0), "tmin": _f(d["temperature_2m_min"][i], 0.0),
            "pop": _f(d["precipitation_probability_max"][i], 0.0) or 0.0,
            "psum": _f(d["precipitation_sum"][i], 0.0) or 0.0,
            "sunrise": datetime.fromisoformat(d["sunrise"][i]) if d["sunrise"][i] else None,
            "sunset": datetime.fromisoformat(d["sunset"][i]) if d["sunset"][i] else None,
            "uv": _f(d["uv_index_max"][i]), "wmax": _f(d["wind_speed_10m_max"][i]),
        })
    air = None
    if aq and aq.get("current"):
        a = aq["current"]
        air = {"aqi": _f(a.get("european_aqi")), "pm25": _f(a.get("pm2_5")), "pm10": _f(a.get("pm10"))}
    units = raw.get("current_units", {})
    return {
        "loc": loc, "cur": cur, "hours": hours, "days": days, "air": air,
        "tunit": units.get("temperature_2m", "°C"),
        "wunit": {"kmh": "km/h", "ms": "m/s", "mph": "mph", "kn": "kn"}.get(settings.get("wind_unit"), "km/h"),
        "is_f": settings.get("temp_unit") == "fahrenheit",
    }


# =================================================================
#  6. Βοηθητικά σχεδίασης
# =================================================================
def qfont(px, weight=QFont.Weight.Normal):
    f = QFont(FONT_FAMILY) if FONT_FAMILY else QFont()
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    return f


def fmt_t(v, unit=False, m=None):
    if v is None:
        return "—"
    s = f"{round(v):d}°"
    if unit and m:
        s = f"{round(v):d}{m['tunit']}"
    return s.replace("-", "−")


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return QColor(int(lerp(a.red(), b.red(), t)), int(lerp(a.green(), b.green(), t)),
                  int(lerp(a.blue(), b.blue(), t)), int(lerp(a.alpha(), b.alpha(), t)))


TEMP_STOPS = [(-10, "#8FB2FF"), (0, "#6FD0F5"), (8, "#78E3C0"), (15, "#B9E86A"),
              (22, "#FFD24A"), (29, "#FF9A45"), (36, "#FF5A5A")]


def temp_color(t, is_f=False):
    if t is None:
        return QColor("#ffffff")
    c = (t - 32) * 5 / 9 if is_f else t
    stops = [(v, QColor(col)) for v, col in TEMP_STOPS]
    if c <= stops[0][0]:
        return stops[0][1]
    for (v1, c1), (v2, c2) in zip(stops, stops[1:]):
        if c <= v2:
            return lerp_color(c1, c2, (c - v1) / (v2 - v1))
    return stops[-1][1]


def theme_colors(code, is_day):
    k = wmo_kind(code)
    if not is_day:
        if k in ("clear", "partly"):
            return QColor("#0E1A3A"), QColor("#2C3F72")
        if k in ("rain", "drizzle", "showers", "thunder"):
            return QColor("#11161F"), QColor("#2B3A4F")
        return QColor("#151C2B"), QColor("#38455C")
    return {
        "clear": (QColor("#1F7BF0"), QColor("#6DB9FF")),
        "partly": (QColor("#3477C9"), QColor("#86B4E4")),
        "cloudy": (QColor("#4E5F76"), QColor("#8C9DB3")),
        "fog": (QColor("#6B7886"), QColor("#A9B4BF")),
        "drizzle": (QColor("#3D5268"), QColor("#7790A8")),
        "rain": (QColor("#2D3F55"), QColor("#5E7A96")),
        "showers": (QColor("#2F4C6E"), QColor("#6F93B8")),
        "snow": (QColor("#5F7FA3"), QColor("#BFD0E3")),
        "thunder": (QColor("#24203A"), QColor("#4E4870")),
    }.get(k, (QColor("#3477C9"), QColor("#86B4E4")))


def draw_text(p, rect, text, font, color, flags=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
              shadow=True):
    p.setFont(font)
    r = QRectF(rect)
    if shadow:
        p.setPen(QColor(0, 0, 0, 55))
        p.drawText(r.translated(0, 1.2), int(flags), text)
    p.setPen(color)
    p.drawText(r, int(flags), text)


# ---------------- Εικονίδια καιρού (διανυσματικά) ----------------
def _cloud_path(r):
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    p1 = QPainterPath(); p1.addEllipse(QRectF(x + 0.04 * w, y + 0.40 * h, 0.42 * w, 0.52 * h))
    p2 = QPainterPath(); p2.addEllipse(QRectF(x + 0.24 * w, y + 0.06 * h, 0.50 * w, 0.72 * h))
    p3 = QPainterPath(); p3.addEllipse(QRectF(x + 0.54 * w, y + 0.34 * h, 0.42 * w, 0.58 * h))
    p4 = QPainterPath(); p4.addRect(QRectF(x + 0.25 * w, y + 0.55 * h, 0.52 * w, 0.37 * h))
    return p1.united(p2).united(p3).united(p4).simplified()


def draw_cloud(p, r, dark=False, alpha=255):
    path = _cloud_path(r)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    if dark:
        g.setColorAt(0, QColor(150, 160, 178, alpha)); g.setColorAt(1, QColor(96, 106, 124, alpha))
    else:
        g.setColorAt(0, QColor(255, 255, 255, alpha)); g.setColorAt(1, QColor(214, 224, 238, alpha))
    p.setPen(QPen(QColor(0, 0, 0, 28), max(0.6, r.width() * 0.012)))
    p.setBrush(g)
    p.drawPath(path)


def draw_sun(p, c, r):
    p.save()
    pen = QPen(QColor(255, 196, 45), max(1.0, r * 0.18))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    for i in range(8):
        a = i * math.pi / 4
        p.drawLine(QPointF(c.x() + math.cos(a) * r * 1.38, c.y() + math.sin(a) * r * 1.38),
                   QPointF(c.x() + math.cos(a) * r * 1.78, c.y() + math.sin(a) * r * 1.78))
    g = QRadialGradient(QPointF(c.x() - r * 0.3, c.y() - r * 0.3), r * 1.4)
    g.setColorAt(0, QColor(255, 244, 150)); g.setColorAt(1, QColor(255, 165, 25))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(g)
    p.drawEllipse(c, r, r)
    p.restore()


def draw_moon(p, c, r):
    p.save()
    full = QPainterPath(); full.addEllipse(c, r, r)
    cut = QPainterPath(); cut.addEllipse(QPointF(c.x() + r * 0.58, c.y() - r * 0.38), r * 0.88, r * 0.88)
    m = full.subtracted(cut)
    g = QLinearGradient(QPointF(c.x() - r, c.y() - r), QPointF(c.x() + r, c.y() + r))
    g.setColorAt(0, QColor(255, 250, 215)); g.setColorAt(1, QColor(236, 214, 140))
    p.setPen(QPen(QColor(0, 0, 0, 30), max(0.6, r * 0.04)))
    p.setBrush(g)
    p.drawPath(m)
    p.restore()


def draw_drops(p, r, n=3, color=QColor(90, 175, 255), drizzle=False):
    p.save()
    pen = QPen(color, max(1.0, r.width() * (0.045 if drizzle else 0.06)))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    step = r.width() / (n + 1)
    ln = r.height() * (0.38 if drizzle else 0.62)
    for i in range(n):
        x = r.x() + step * (i + 1)
        y = r.y() + (r.height() * 0.22 if i % 2 else 0)
        p.drawLine(QPointF(x, y), QPointF(x - ln * 0.35, y + ln))
    p.restore()


def draw_flakes(p, r, n=3):
    p.save()
    pen = QPen(QColor(255, 255, 255), max(1.0, r.width() * 0.035))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    step = r.width() / (n + 1)
    fr = r.height() * 0.22
    for i in range(n):
        cx = r.x() + step * (i + 1)
        cy = r.y() + fr + (r.height() * 0.38 if i % 2 else 0)
        for k in range(3):
            a = k * math.pi / 3
            p.drawLine(QPointF(cx - math.cos(a) * fr, cy - math.sin(a) * fr),
                       QPointF(cx + math.cos(a) * fr, cy + math.sin(a) * fr))
    p.restore()


def draw_bolt(p, r):
    x, y, w, h = r.x(), r.y(), r.width(), r.height()
    poly = QPolygonF([QPointF(x + 0.55 * w, y), QPointF(x + 0.15 * w, y + 0.58 * h),
                      QPointF(x + 0.45 * w, y + 0.58 * h), QPointF(x + 0.30 * w, y + h),
                      QPointF(x + 0.85 * w, y + 0.38 * h), QPointF(x + 0.55 * w, y + 0.38 * h),
                      QPointF(x + 0.72 * w, y)])
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0, QColor(255, 236, 110)); g.setColorAt(1, QColor(255, 170, 20))
    p.setPen(QPen(QColor(150, 90, 0, 120), max(0.6, w * 0.03)))
    p.setBrush(g)
    p.drawPolygon(poly)


def draw_weather_icon(p, rect, code, is_day=True):
    s = min(rect.width(), rect.height())
    x0 = rect.center().x() - s / 2
    y0 = rect.center().y() - s / 2
    k = wmo_kind(code)
    c = int(code or 0)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if k == "clear":
        cc = QPointF(x0 + s / 2, y0 + s / 2)
        if is_day:
            draw_sun(p, cc, s * 0.24)
        else:
            draw_moon(p, cc, s * 0.32)
        if c == 1:
            draw_cloud(p, QRectF(x0 + s * 0.42, y0 + s * 0.56, s * 0.5, s * 0.34))
    elif k in ("partly", "showers"):
        cc = QPointF(x0 + s * 0.36, y0 + s * 0.34)
        if is_day:
            draw_sun(p, cc, s * 0.17)
        else:
            draw_moon(p, cc, s * 0.22)
        if k == "partly":
            draw_cloud(p, QRectF(x0 + s * 0.16, y0 + s * 0.32, s * 0.80, s * 0.56))
        else:
            draw_cloud(p, QRectF(x0 + s * 0.14, y0 + s * 0.26, s * 0.80, s * 0.50))
            draw_drops(p, QRectF(x0 + s * 0.22, y0 + s * 0.72, s * 0.62, s * 0.24), n=3 if c < 82 else 4)
    elif k == "cloudy":
        draw_cloud(p, QRectF(x0 + s * 0.02, y0 + s * 0.14, s * 0.62, s * 0.44), dark=True)
        draw_cloud(p, QRectF(x0 + s * 0.18, y0 + s * 0.30, s * 0.80, s * 0.56))
    elif k == "fog":
        draw_cloud(p, QRectF(x0 + s * 0.10, y0 + s * 0.06, s * 0.80, s * 0.52))
        pen = QPen(QColor(235, 240, 248), max(1.0, s * 0.055))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        for i, (a, b) in enumerate([(0.12, 0.80), (0.22, 0.90), (0.16, 0.70)]):
            yy = y0 + s * (0.68 + i * 0.11)
            p.drawLine(QPointF(x0 + s * a, yy), QPointF(x0 + s * b, yy))
    elif k in ("drizzle", "rain"):
        heavy = c in (65, 67)
        draw_cloud(p, QRectF(x0 + s * 0.08, y0 + s * 0.06, s * 0.84, s * 0.58), dark=heavy)
        col = QColor(150, 220, 255) if c in (56, 57, 66, 67) else QColor(90, 175, 255)
        draw_drops(p, QRectF(x0 + s * 0.16, y0 + s * 0.68, s * 0.68, s * 0.28),
                   n=4 if heavy else 3, color=col, drizzle=(k == "drizzle"))
    elif k == "snow":
        draw_cloud(p, QRectF(x0 + s * 0.08, y0 + s * 0.04, s * 0.84, s * 0.58))
        draw_flakes(p, QRectF(x0 + s * 0.14, y0 + s * 0.64, s * 0.72, s * 0.32), n=3)
    elif k == "thunder":
        draw_cloud(p, QRectF(x0 + s * 0.06, y0 + s * 0.04, s * 0.88, s * 0.58), dark=True)
        draw_drops(p, QRectF(x0 + s * 0.12, y0 + s * 0.68, s * 0.40, s * 0.26), n=2)
        draw_bolt(p, QRectF(x0 + s * 0.48, y0 + s * 0.50, s * 0.30, s * 0.46))
    p.restore()


def app_icon():
    icon = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(sz, sz)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_weather_icon(p, QRectF(0, 0, sz, sz), 2, True)
        p.end()
        icon.addPixmap(pm)
    return icon


def tray_pixmap(model, mode):
    sz = 64
    pm = QPixmap(sz, sz)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    if model is None:
        draw_weather_icon(p, QRectF(0, 0, sz, sz), 2, True)
    elif mode == "icon":
        draw_weather_icon(p, QRectF(0, 0, sz, sz), model["cur"]["code"], model["cur"]["is_day"])
    else:
        t = round(model["cur"]["temp"])
        txt = f"{t}°" if -10 < t < 100 else f"{t}"
        txt = txt.replace("-", "−")
        px = 52
        while px > 16:
            f = qfont(px, QFont.Weight.Bold)
            fm = QFontMetrics(f)
            if fm.horizontalAdvance(txt) <= sz - 2:
                break
            px -= 2
        f = qfont(px, QFont.Weight.Bold)
        fm = QFontMetrics(f)
        w = fm.horizontalAdvance(txt)
        path = QPainterPath()
        base_y = (sz + fm.capHeight()) / 2
        path.addText(QPointF((sz - w) / 2, base_y), f, txt)
        col = temp_color(model["cur"]["temp"], model.get("is_f"))
        p.setPen(QPen(QColor(0, 0, 0, 200), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(lerp_color(QColor("#ffffff"), col, 0.55))
        p.drawPath(path)
    p.end()
    return pm


# =================================================================
#  7. Στυλ (QSS)
# =================================================================
QSS = """
* { font-family: '%(f)s'; }
QMenu { background: #1b2433; color: #eef3fb; border: 1px solid #34425a; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 26px 7px 14px; border-radius: 6px; font-size: 13px; }
QMenu::item:selected { background: #2f5ea8; }
QMenu::item:disabled { color: #8494ad; }
QMenu::separator { height: 1px; background: #34425a; margin: 5px 8px; }
QMenu::indicator { width: 14px; height: 14px; left: 6px; }
QToolTip { background: #1b2433; color: #eef3fb; border: 1px solid #34425a; padding: 4px; }
QPushButton#glass { background: rgba(255,255,255,0.16); color: white; border: 1px solid rgba(255,255,255,0.28);
                    border-radius: 10px; padding: 7px 14px; font-size: 13px; font-weight: 600; }
QPushButton#glass:hover { background: rgba(255,255,255,0.28); }
QPushButton#glass:pressed { background: rgba(255,255,255,0.10); }
QLineEdit#glass { background: rgba(255,255,255,0.16); color: white; border: 1px solid rgba(255,255,255,0.28);
                  border-radius: 10px; padding: 7px 12px; font-size: 13px; selection-background-color: #2f5ea8; }
QLineEdit#glass:focus { border: 1px solid rgba(255,255,255,0.65); background: rgba(255,255,255,0.22); }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.30); border-radius: 4px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 2px; }
QScrollBar::handle:horizontal { background: rgba(255,255,255,0.30); border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QDialog#settings { background: #1b2433; }
QDialog#settings QLabel { color: #dfe7f3; font-size: 13px; }
QDialog#settings QComboBox, QDialog#settings QSpinBox {
    background: #243045; color: white; border: 1px solid #3a4a66; border-radius: 7px; padding: 5px 8px; min-width: 190px; font-size: 13px; }
QDialog#settings QComboBox QAbstractItemView { background: #243045; color: white; selection-background-color: #2f5ea8; }
QDialog#settings QCheckBox { color: #dfe7f3; font-size: 13px; spacing: 8px; }
QDialog#settings QPushButton { background: #2f5ea8; color: white; border: none; border-radius: 8px; padding: 7px 18px; font-size: 13px; }
QDialog#settings QPushButton:hover { background: #3a6fc4; }
""" % {"f": FONT_FAMILY or "sans-serif"}


def make_menu(parent=None):
    m = QMenu(parent)
    m.setWindowFlags(m.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
    m.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return m


# =================================================================
#  8. Widgets κύριου παραθύρου
# =================================================================
def glass_card(p, r, radius=16):
    p.setPen(QPen(QColor(255, 255, 255, 48), 1))
    p.setBrush(QColor(255, 255, 255, 30))
    p.drawRoundedRect(QRectF(r).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


class Hero(QWidget):
    def __init__(self):
        super().__init__()
        self.m = None
        self.setMinimumHeight(206)

    def set_model(self, m):
        self.m = m
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        glass_card(p, self.rect(), 20)
        W = self.width()
        white = QColor(255, 255, 255)
        soft = QColor(255, 255, 255, 200)
        if not self.m:
            draw_text(p, self.rect(), tr("loading"), qfont(18), white, Qt.AlignmentFlag.AlignCenter)
            return
        m, c = self.m, self.m["cur"]
        loc = m["loc"]
        draw_text(p, QRectF(24, 14, W - 260, 32), loc.get("name", ""), qfont(22, QFont.Weight.DemiBold), white)
        sub = ", ".join([x for x in (loc.get("admin1"), loc.get("country")) if x])
        draw_text(p, QRectF(24, 44, W - 260, 20), sub, qfont(13), soft)
        draw_text(p, QRectF(W - 240, 16, 220, 20),
                  f"{tr('updated')} {c['time'].strftime('%H:%M')}", qfont(12), soft,
                  Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        draw_weather_icon(p, QRectF(14, 64, 134, 134), c["code"], c["is_day"])
        tf = qfont(84, QFont.Weight.Light)
        ttxt = fmt_t(c["temp"])
        draw_text(p, QRectF(160, 62, 260, 110), ttxt, tf, white)
        tw = QFontMetrics(tf).horizontalAdvance(ttxt)
        x2 = 160 + tw + 24
        draw_text(p, QRectF(x2, 80, W - x2 - 20, 30), wmo_text(c["code"]), qfont(21, QFont.Weight.DemiBold), white)
        d0 = m["days"][0] if m["days"] else None
        draw_text(p, QRectF(x2, 112, W - x2 - 20, 22), f"{tr('feels')} {fmt_t(c['feels'])}", qfont(14), soft)
        if d0:
            draw_text(p, QRectF(x2, 136, W - x2 - 20, 22),
                      f"{tr('hi')} {fmt_t(d0['tmax'])}   ·   {tr('lo')} {fmt_t(d0['tmin'])}", qfont(14), soft)
        draw_text(p, QRectF(160, 172, W - 180, 22), tr("hint"), qfont(11), QColor(255, 255, 255, 150))


class HourlyChart(QWidget):
    COL = 64

    def __init__(self):
        super().__init__()
        self.hours = []
        self.is_f = False
        self.setFixedHeight(214)

    def set_model(self, m):
        self.hours = m["hours"] if m else []
        self.is_f = m.get("is_f", False) if m else False
        self.setFixedWidth(max(300, len(self.hours) * self.COL + 16))
        self.update()

    def paintEvent(self, e):
        if not self.hours:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        temps = [h["temp"] for h in self.hours]
        lo, hi = min(temps), max(temps)
        span = (hi - lo) or 1.0
        top_y, bot_y = 104, 150
        pts = []
        for i, h in enumerate(self.hours):
            x = 8 + self.COL * i + self.COL / 2
            y = bot_y - (h["temp"] - lo) / span * (bot_y - top_y)
            pts.append(QPointF(x, y))
        # Καμπύλη (Catmull-Rom -> Bezier)
        path = QPainterPath(pts[0])
        for i in range(len(pts) - 1):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1, p2 = pts[i], pts[i + 1]
            p3 = pts[i + 2] if i + 2 < len(pts) else p2
            c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6, p1.y() + (p2.y() - p0.y()) / 6)
            c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6, p2.y() - (p3.y() - p1.y()) / 6)
            path.cubicTo(c1, c2, p2)
        fill = QPainterPath(path)
        fill.lineTo(pts[-1].x(), bot_y + 14)
        fill.lineTo(pts[0].x(), bot_y + 14)
        fill.closeSubpath()
        g = QLinearGradient(0, top_y - 10, 0, bot_y + 14)
        g.setColorAt(0, QColor(255, 210, 90, 110))
        g.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawPath(fill)
        lg = QLinearGradient(pts[0], pts[-1])
        for i, h in enumerate(self.hours):
            lg.setColorAt(i / max(1, len(self.hours) - 1), temp_color(h["temp"], self.is_f))
        pen = QPen(lg, 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        white = QColor(255, 255, 255)
        for i, h in enumerate(self.hours):
            cx = pts[i].x()
            col_r = QRectF(cx - self.COL / 2, 0, self.COL, self.height())
            if i == 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 34))
                p.drawRoundedRect(col_r.adjusted(4, 2, -4, -2), 12, 12)
            lbl = tr("now") if i == 0 else h["t"].strftime("%H:00")
            draw_text(p, QRectF(col_r.x(), 6, self.COL, 20), lbl,
                      qfont(12, QFont.Weight.DemiBold if i == 0 else QFont.Weight.Normal),
                      white, Qt.AlignmentFlag.AlignCenter)
            draw_weather_icon(p, QRectF(cx - 18, 30, 36, 36), h["code"], h["is_day"])
            draw_text(p, QRectF(cx - 30, pts[i].y() - 30, 60, 20), fmt_t(h["temp"]),
                      qfont(14, QFont.Weight.DemiBold), white, Qt.AlignmentFlag.AlignCenter)
            p.setPen(QPen(QColor(255, 255, 255), 2))
            p.setBrush(temp_color(h["temp"], self.is_f))
            p.drawEllipse(pts[i], 4, 4)
            # Πιθανότητα υετού
            pop = h["pop"] or 0
            bh = 26 * pop / 100.0
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawRoundedRect(QRectF(cx - 9, 172, 18, 26), 4, 4)
            if bh > 0:
                p.setBrush(QColor(80, 170, 255, 230))
                p.drawRoundedRect(QRectF(cx - 9, 198 - bh, 18, bh), 4, 4)
            if pop >= 10:
                draw_text(p, QRectF(cx - 30, 154, 60, 16), f"{int(pop)}%", qfont(11, QFont.Weight.DemiBold),
                          QColor(150, 210, 255), Qt.AlignmentFlag.AlignCenter)


class HScroll(QScrollArea):
    def wheelEvent(self, e):
        d = e.angleDelta().y() or e.angleDelta().x()
        sb = self.horizontalScrollBar()
        sb.setValue(sb.value() - d)
        e.accept()


class DailyList(QWidget):
    ROW = 50

    def __init__(self):
        super().__init__()
        self.m = None
        self.setMinimumHeight(self.ROW * 7 + 8)

    def set_model(self, m):
        self.m = m
        n = len(m["days"]) if m else 7
        self.setMinimumHeight(self.ROW * n + 8)
        self.update()

    def paintEvent(self, e):
        if not self.m:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        days = self.m["days"]
        is_f = self.m.get("is_f")
        gmin = min(d["tmin"] for d in days)
        gmax = max(d["tmax"] for d in days)
        span = (gmax - gmin) or 1
        W = self.width()
        white = QColor(255, 255, 255)
        soft = QColor(255, 255, 255, 190)
        bar_x0, bar_x1 = 214, W - 56
        for i, d in enumerate(days):
            y = 4 + i * self.ROW
            if i > 0:
                p.setPen(QPen(QColor(255, 255, 255, 34), 1))
                p.drawLine(QPointF(10, y), QPointF(W - 10, y))
            name = tr("today") if i == 0 else tr("days")[d["d"].weekday()]
            draw_text(p, QRectF(12, y, 96, self.ROW), name,
                      qfont(14, QFont.Weight.DemiBold if i == 0 else QFont.Weight.Normal), white)
            draw_weather_icon(p, QRectF(104, y + 8, 34, 34), d["code"], True)
            if d["pop"] >= 10:
                draw_text(p, QRectF(140, y, 40, self.ROW), f"{int(d['pop'])}%", qfont(12, QFont.Weight.DemiBold),
                          QColor(150, 210, 255))
            draw_text(p, QRectF(bar_x0 - 46, y, 40, self.ROW), fmt_t(d["tmin"]), qfont(14), soft,
                      Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            draw_text(p, QRectF(bar_x1 + 8, y, 44, self.ROW), fmt_t(d["tmax"]), qfont(14, QFont.Weight.DemiBold),
                      white)
            cy = y + self.ROW / 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 40))
            p.drawRoundedRect(QRectF(bar_x0, cy - 3, bar_x1 - bar_x0, 6), 3, 3)
            sx = bar_x0 + (d["tmin"] - gmin) / span * (bar_x1 - bar_x0)
            ex = bar_x0 + (d["tmax"] - gmin) / span * (bar_x1 - bar_x0)
            if ex - sx < 6:
                ex = sx + 6
            g = QLinearGradient(sx, 0, ex, 0)
            g.setColorAt(0, temp_color(d["tmin"], is_f))
            g.setColorAt(1, temp_color(d["tmax"], is_f))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(sx, cy - 3, ex - sx, 6), 3, 3)
            if i == 0:
                t = self.m["cur"]["temp"]
                tx = bar_x0 + (max(gmin, min(gmax, t)) - gmin) / span * (bar_x1 - bar_x0)
                p.setPen(QPen(QColor(0, 0, 0, 90), 2))
                p.setBrush(white)
                p.drawEllipse(QPointF(tx, cy), 5, 5)


class Tile(QWidget):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.title = self.value = self.sub = ""
        self.extra = None
        self.setMinimumSize(160, 122)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set(self, title, value, sub, extra=None):
        self.title, self.value, self.sub, self.extra = title, value, sub, extra
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        glass_card(p, self.rect(), 16)
        W, H = self.width(), self.height()
        has_side = self.kind in ("wind", "sun", "hum", "cloud")
        tw = W - (78 if has_side else 24)
        draw_text(p, QRectF(14, 10, W - 28, 18), self.title, qfont(11, QFont.Weight.DemiBold),
                  QColor(255, 255, 255, 175))
        draw_text(p, QRectF(14, 32, tw, 34), self.value, qfont(23, QFont.Weight.DemiBold), QColor(255, 255, 255))
        bar = self.kind in ("uv", "aqi")
        if bar:
            sf = qfont(12)
            txt = QFontMetrics(sf).elidedText(self.sub, Qt.TextElideMode.ElideRight, int(W - 28))
            draw_text(p, QRectF(14, H - 46, W - 28, 22), txt, sf, QColor(255, 255, 255, 205))
        else:
            draw_text(p, QRectF(14, H - 44, tw, 36), self.sub, qfont(12), QColor(255, 255, 255, 205),
                      Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap)
        ex = self.extra
        if self.kind == "wind" and ex is not None:
            c = QPointF(W - 40, 62)
            r = 26
            p.setPen(QPen(QColor(255, 255, 255, 90), 1.5))
            p.setBrush(QColor(255, 255, 255, 20))
            p.drawEllipse(c, r, r)
            for k in range(8):
                a = math.radians(k * 45)
                l1 = r - (6 if k % 2 == 0 else 3)
                p.drawLine(QPointF(c.x() + math.sin(a) * l1, c.y() - math.cos(a) * l1),
                           QPointF(c.x() + math.sin(a) * r, c.y() - math.cos(a) * r))
            draw_text(p, QRectF(c.x() - 10, c.y() - r - 2, 20, 14), tr("compass")[0], qfont(10, QFont.Weight.Bold),
                      QColor(255, 255, 255, 220), Qt.AlignmentFlag.AlignCenter, shadow=False)
            a = math.radians((ex + 180) % 360)  # βέλος προς τα πού πάει ο άνεμος
            tip = QPointF(c.x() + math.sin(a) * (r - 6), c.y() - math.cos(a) * (r - 6))
            tail = QPointF(c.x() - math.sin(a) * (r - 8), c.y() + math.cos(a) * (r - 8))
            pen = QPen(QColor(255, 255, 255), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(tail, tip)
            left = QPointF(tip.x() - math.sin(a - 0.5) * 9, tip.y() + math.cos(a - 0.5) * 9)
            right = QPointF(tip.x() - math.sin(a + 0.5) * 9, tip.y() + math.cos(a + 0.5) * 9)
            p.setBrush(QColor(255, 255, 255))
            p.drawPolygon(QPolygonF([tip, left, right]))
        elif self.kind == "sun" and ex:
            rise, sset, now = ex
            box = QRectF(W - 74, 40, 62, 62)
            p.setPen(QPen(QColor(255, 255, 255, 80), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(box, 0, 180 * 16)
            p.setPen(QPen(QColor(255, 255, 255, 90), 1))
            p.drawLine(QPointF(box.left() - 4, box.center().y()), QPointF(box.right() + 4, box.center().y()))
            if rise and sset:
                tot = (sset - rise).total_seconds() or 1
                f = (now - rise).total_seconds() / tot
                if 0 <= f <= 1:
                    ang = math.pi * (1 - f)
                    pt = QPointF(box.center().x() + math.cos(ang) * box.width() / 2,
                                 box.center().y() - math.sin(ang) * box.height() / 2)
                    draw_sun(p, pt, 6)
        elif self.kind == "hum" and ex is not None:
            box = QRectF(W - 54, 34, 30, 68)
            p.setPen(QPen(QColor(255, 255, 255, 90), 1.5))
            p.setBrush(QColor(255, 255, 255, 20))
            p.drawRoundedRect(box, 10, 10)
            fh = box.height() * max(0, min(100, ex)) / 100
            p.setPen(Qt.PenStyle.NoPen)
            g = QLinearGradient(0, box.bottom(), 0, box.top())
            g.setColorAt(0, QColor(70, 160, 255, 230)); g.setColorAt(1, QColor(140, 220, 255, 230))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(box.x() + 3, box.bottom() - fh + 3 if fh > 6 else box.bottom() - 6,
                                     box.width() - 6, max(3, fh - 6)), 7, 7)
        elif self.kind == "cloud" and ex is not None:
            draw_cloud(p, QRectF(W - 70, 44, 58, 40), alpha=int(70 + 185 * max(0, min(100, ex)) / 100))
        elif bar and ex is not None:
            bx0, bx1, by = 14, W - 14, H - 14
            g = QLinearGradient(bx0, 0, bx1, 0)
            if self.kind == "uv":
                for pos, col in [(0, "#3fbf5a"), (0.27, "#e7d43a"), (0.5, "#f39c2c"), (0.73, "#e74c3c"), (1, "#9b59b6")]:
                    g.setColorAt(pos, QColor(col))
                f = min(1.0, (ex or 0) / 11.0)
            else:
                for pos, col in [(0, "#50f0e6"), (0.2, "#50ccaa"), (0.4, "#f0e641"), (0.6, "#ff5050"),
                                 (0.8, "#960032"), (1, "#7d2181")]:
                    g.setColorAt(pos, QColor(col))
                f = min(1.0, (ex or 0) / 100.0)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawRoundedRect(QRectF(bx0, by - 3, bx1 - bx0, 6), 3, 3)
            p.setPen(QPen(QColor(0, 0, 0, 120), 2))
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QPointF(bx0 + f * (bx1 - bx0), by), 5, 5)


class SectionTitle(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setStyleSheet("color: rgba(255,255,255,0.78); font-size: 12px; font-weight: 700; "
                           "letter-spacing: 1px; background: transparent; padding-left: 4px;")


class Card(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setStyleSheet("QFrame#card { background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.19);"
                           " border-radius: 18px; }")


class Background(QWidget):
    def __init__(self):
        super().__init__()
        self.c1, self.c2 = theme_colors(2, True)

    def set_theme(self, code, is_day):
        self.c1, self.c2 = theme_colors(code, is_day)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width() * 0.35, self.height())
        g.setColorAt(0, self.c1)
        g.setColorAt(1, self.c2)
        p.fillRect(self.rect(), g)
        rg = QRadialGradient(QPointF(self.width() * 0.85, -40), self.width() * 0.6)
        rg.setColorAt(0, QColor(255, 255, 255, 40))
        rg.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(self.rect(), rg)


# =================================================================
#  9. Κύριο παράθυρο
# =================================================================
def uv_level(u):
    if u is None:
        return tr("na")
    i = 0 if u < 3 else 1 if u < 6 else 2 if u < 8 else 3 if u < 11 else 4
    return tr("uv_levels")[i]


def aqi_level(a):
    if a is None:
        return tr("na")
    i = 0 if a < 20 else 1 if a < 40 else 2 if a < 60 else 3 if a < 80 else 4 if a <= 100 else 5
    return tr("aqi_levels")[i]


def compass(deg):
    if deg is None:
        return ""
    return tr("compass")[int((deg % 360 + 22.5) // 45) % 8]


class MainWindow(QMainWindow):
    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self.geo = None
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setWindowIcon(app_icon())
        self.resize(1200, 880)
        self.setMinimumSize(920, 600)

        self.bg = Background()
        self.setCentralWidget(self.bg)
        root = QVBoxLayout(self.bg)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(10)

        # --- Header ---
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        title = QLabel(f"☁  {APP_NAME}")
        title.setStyleSheet("color: white; font-size: 17px; font-weight: 700; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch(1)
        self.search = QLineEdit()
        self.search.setObjectName("glass")
        self.search.setPlaceholderText(tr("search_ph"))
        self.search.setMinimumWidth(330)
        self.search.returnPressed.connect(self.do_search)
        hdr.addWidget(self.search)
        self.btn_search = self._btn("🔍  " + tr("search"), self.do_search)
        hdr.addWidget(self.btn_search)
        self.btn_recent = self._btn("★", self.show_recent)
        self.btn_recent.setToolTip(tr("locations"))
        hdr.addWidget(self.btn_recent)
        hdr.addSpacing(10)
        b = self._btn("⟳", ctrl.refresh); b.setToolTip(tr("refresh")); hdr.addWidget(b)
        b = self._btn("⚙", ctrl.open_settings); b.setToolTip(tr("settings")); hdr.addWidget(b)
        b = self._btn(tr("lang_toggle"), ctrl.toggle_language); b.setToolTip(tr("lang")); hdr.addWidget(b)
        b = self._btn("ⓘ", ctrl.show_about); b.setToolTip(tr("about")); hdr.addWidget(b)
        root.addLayout(hdr)

        # --- Scroll περιεχόμενο ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setAutoFillBackground(False)
        content = QWidget()
        content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        cols = QHBoxLayout(content)
        cols.setContentsMargins(0, 4, 4, 4)
        cols.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(10)
        right = QVBoxLayout()
        right.setSpacing(10)
        cols.addLayout(left, 63)
        cols.addLayout(right, 37)

        self.hero = Hero()
        left.addWidget(self.hero)

        left.addWidget(SectionTitle(tr("hourly")))
        hc = Card()
        hcl = QVBoxLayout(hc)
        hcl.setContentsMargins(6, 6, 6, 4)
        self.hourly = HourlyChart()
        hs = HScroll()
        hs.setWidget(self.hourly)
        hs.setWidgetResizable(False)
        hs.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hs.setFixedHeight(self.hourly.height() + 14)
        hs.viewport().setAutoFillBackground(False)
        self.hourly.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        hcl.addWidget(hs)
        left.addWidget(hc)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.tiles = {}
        kinds = ["feels", "hum", "wind", "press", "cloud", "uv", "sun", "aqi"]
        for i, k in enumerate(kinds):
            t = Tile(k)
            self.tiles[k] = t
            grid.addWidget(t, i // 4, i % 4)
        left.addLayout(grid)
        left.addStretch(1)

        right.addWidget(SectionTitle(tr("daily")))
        dc = Card()
        dcl = QVBoxLayout(dc)
        dcl.setContentsMargins(6, 4, 6, 4)
        self.daily = DailyList()
        dcl.addWidget(self.daily)
        right.addWidget(dc)
        right.addStretch(1)

        # --- Footer ---
        ftr = QHBoxLayout()
        self.status = QLabel("")
        self.status.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 12px; background: transparent;")
        ftr.addWidget(self.status)
        ftr.addStretch(1)
        cred = QLabel(f"{tr('data_by')}   ·   {APP_TEAM} — {APP_AUTHOR}   ·   v{APP_VERSION}")
        cred.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 11px; background: transparent;")
        ftr.addWidget(cred)
        root.addLayout(ftr)

    def _btn(self, text, slot):
        b = QPushButton(text)
        b.setObjectName("glass")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    def set_status(self, text):
        self.status.setText(text)

    def set_model(self, m):
        if not m:
            return
        c = m["cur"]
        self.bg.set_theme(c["code"], c["is_day"])
        self.hero.set_model(m)
        self.hourly.set_model(m)
        self.daily.set_model(m)
        d0 = m["days"][0] if m["days"] else {}
        # Αισθητή
        diff = (c["feels"] or c["temp"]) - c["temp"]
        sub = tr("feels_warmer") if diff > 1.5 else tr("feels_colder") if diff < -1.5 else tr("feels_same")
        self.tiles["feels"].set(tr("t_feels"), fmt_t(c["feels"]), sub)
        self.tiles["hum"].set(tr("t_hum"), f"{int(c['hum'] or 0)}%", f"{tr('dew')} {fmt_t(c['dew'])}", c["hum"])
        self.tiles["wind"].set(tr("t_wind"), f"{round(c['wind'] or 0)} {m['wunit']}",
                               f"{compass(c['wdir'])} · {tr('gusts')} {round(c['gust'] or 0)}", c["wdir"])
        self.tiles["press"].set(tr("t_press"), f"{round(c['press'] or 0)} hPa", tr("sea_level"))
        vis = c["vis"]
        vis_s = f"{vis / 1000:.1f} km" if vis is not None and vis < 10000 else (
            f"{round(vis / 1000)} km" if vis is not None else tr("na"))
        self.tiles["cloud"].set(tr("t_cloud"), f"{int(c['cloud'] or 0)}%", f"{tr('visibility')} {vis_s}", c["cloud"])
        uv = d0.get("uv")
        self.tiles["uv"].set(tr("t_uv"), f"{uv:.0f}" if uv is not None else tr("na"), uv_level(uv), uv)
        rise, sset = d0.get("sunrise"), d0.get("sunset")
        self.tiles["sun"].set(tr("t_sun"), rise.strftime("%H:%M") if rise else tr("na"),
                              f"{tr('sunset')} {sset.strftime('%H:%M') if sset else tr('na')}",
                              (rise, sset, c["time"]))
        a = m.get("air")
        if a and a.get("aqi") is not None:
            pm = f" · PM2.5 {a['pm25']:.0f}" if a.get("pm25") is not None else ""
            self.tiles["aqi"].set(tr("t_aqi"), f"{int(a['aqi'])}", aqi_level(a["aqi"]) + pm, a["aqi"])
        else:
            self.tiles["aqi"].set(tr("t_aqi"), tr("na"), "", None)

    # --- Αναζήτηση τοποθεσίας ---
    def do_search(self):
        txt = self.search.text().strip()
        if len(txt) < 2:
            self.show_recent()
            return
        if self.geo and self.geo.isRunning():
            return
        self.btn_search.setText(tr("searching"))
        self.geo = GeoSearch(txt, I18n.lang)
        self.geo.results.connect(self._on_results)
        self.geo.failed.connect(lambda e: self._on_results(None))
        self.geo.start()

    def _on_results(self, res):
        self.btn_search.setText("🔍  " + tr("search"))
        menu = make_menu(self)
        if not res:
            a = menu.addAction(tr("err_net") if res is None else tr("no_results"))
            a.setEnabled(False)
        else:
            for loc in res:
                label = ", ".join([x for x in (loc["name"], loc["admin1"], loc["country"]) if x])
                act = menu.addAction(label)
                act.triggered.connect(lambda _=False, l=loc: self._choose(l))
        menu.setMinimumWidth(self.search.width())
        menu.popup(self.search.mapToGlobal(QPoint(0, self.search.height() + 4)))

    def _choose(self, loc):
        self.search.clear()
        self.ctrl.set_location(loc)

    def show_recent(self):
        menu = make_menu(self)
        self.ctrl.fill_locations_menu(menu)
        menu.popup(self.btn_recent.mapToGlobal(QPoint(0, self.btn_recent.height() + 4)))

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        self.ctrl.on_main_closed()


# =================================================================
#  10. Flyout (μονό κλικ)
# =================================================================
class Flyout(QWidget):
    W, H = 372, 346

    def __init__(self, ctrl):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.NoDropShadowWindowHint)
        self.ctrl = ctrl
        self.m = None
        self.closed_at = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)
        self.btn_open = QPushButton("⤢  " + tr("open_app"), self)
        self.btn_open.setObjectName("glass")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.setGeometry(18, self.H - 58, self.W - 36 - 58, 40)
        self.btn_open.clicked.connect(self._open)
        self.btn_ref = QPushButton("⟳", self)
        self.btn_ref.setObjectName("glass")
        self.btn_ref.setToolTip(tr("refresh"))
        self.btn_ref.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ref.setGeometry(self.W - 18 - 50, self.H - 58, 50, 40)
        self.btn_ref.clicked.connect(ctrl.refresh)

    def _open(self):
        self.hide()
        self.ctrl.show_main()

    def set_model(self, m):
        self.m = m
        self.update()

    def hideEvent(self, e):
        self.closed_at = time.monotonic()
        super().hideEvent(e)

    def mousePressEvent(self, e):
        if e.position().y() < 170 and e.button() == Qt.MouseButton.LeftButton:
            self._open()
        else:
            super().mousePressEvent(e)

    def show_near_tray(self, tray_geom):
        anchor = tray_geom.center() if tray_geom.isValid() and not tray_geom.isEmpty() else QCursor.pos()
        scr = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        av = scr.availableGeometry()
        full = scr.geometry()
        w, h, gap = self.W, self.H, 8
        x = anchor.x() - w // 2
        y = anchor.y() - h // 2
        if av.bottom() < full.bottom() and anchor.y() > av.bottom():      # taskbar κάτω
            y = av.bottom() - h - gap
        elif av.top() > full.top() and anchor.y() < av.top():             # taskbar πάνω
            y = av.top() + gap
        elif av.left() > full.left() and anchor.x() < av.left():          # taskbar αριστερά
            x = av.left() + gap
        elif av.right() < full.right() and anchor.x() > av.right():       # taskbar δεξιά
            x = av.right() - w - gap
        else:
            y = av.bottom() - h - gap
        x = max(av.left() + gap, min(x, av.right() - w - gap))
        y = max(av.top() + gap, min(y, av.bottom() - h - gap))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        code, day = (self.m["cur"]["code"], self.m["cur"]["is_day"]) if self.m else (2, True)
        c1, c2 = theme_colors(code, day)
        g = QLinearGradient(0, 0, self.W * 0.4, self.H)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.setBrush(g)
        p.drawRoundedRect(r, 18, 18)
        rg = QRadialGradient(QPointF(self.W * 0.9, 0), self.W * 0.7)
        rg.setColorAt(0, QColor(255, 255, 255, 45))
        rg.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rg)
        p.drawRoundedRect(r, 18, 18)
        white = QColor(255, 255, 255)
        soft = QColor(255, 255, 255, 200)
        if not self.m:
            draw_text(p, QRectF(0, 0, self.W, self.H - 60), tr("loading"), qfont(16), white,
                      Qt.AlignmentFlag.AlignCenter)
            return
        m, c = self.m, self.m["cur"]
        draw_text(p, QRectF(20, 12, self.W - 120, 26), m["loc"].get("name", ""), qfont(16, QFont.Weight.DemiBold), white)
        draw_text(p, QRectF(self.W - 120, 12, 100, 26), c["time"].strftime("%H:%M"), qfont(12), soft,
                  Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        draw_weather_icon(p, QRectF(14, 44, 104, 104), c["code"], c["is_day"])
        draw_text(p, QRectF(126, 40, 230, 66), fmt_t(c["temp"]), qfont(58, QFont.Weight.Light), white)
        draw_text(p, QRectF(128, 104, 230, 22), wmo_text(c["code"]), qfont(15, QFont.Weight.DemiBold), white)
        d0 = m["days"][0] if m["days"] else None
        line = f"{tr('feels')} {fmt_t(c['feels'])}"
        if d0:
            line += f"  ·  {fmt_t(d0['tmax'])} / {fmt_t(d0['tmin'])}"
        draw_text(p, QRectF(128, 126, 236, 20), line, qfont(12), soft)
        draw_text(p, QRectF(128, 146, 236, 18),
                  f"💧 {int(c['hum'] or 0)}%   ·   💨 {round(c['wind'] or 0)} {m['wunit']} {compass(c['wdir'])}",
                  qfont(12), soft)
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.drawLine(QPointF(18, 172), QPointF(self.W - 18, 172))
        hrs = m["hours"][:7]
        if hrs:
            cw = (self.W - 24) / len(hrs)
            for i, h in enumerate(hrs):
                x = 12 + i * cw
                lbl = tr("now") if i == 0 else h["t"].strftime("%H")
                draw_text(p, QRectF(x, 178, cw, 18), lbl,
                          qfont(11, QFont.Weight.DemiBold if i == 0 else QFont.Weight.Normal), soft,
                          Qt.AlignmentFlag.AlignCenter)
                draw_weather_icon(p, QRectF(x + cw / 2 - 16, 198, 32, 32), h["code"], h["is_day"])
                draw_text(p, QRectF(x, 232, cw, 20), fmt_t(h["temp"]), qfont(14, QFont.Weight.DemiBold), white,
                          Qt.AlignmentFlag.AlignCenter)
                if h["pop"] >= 10:
                    draw_text(p, QRectF(x, 252, cw, 16), f"{int(h['pop'])}%", qfont(10, QFont.Weight.DemiBold),
                              QColor(160, 215, 255), Qt.AlignmentFlag.AlignCenter)


# =================================================================
#  11. Ρυθμίσεις
# =================================================================
class SettingsDialog(QDialog):
    def __init__(self, s, parent=None):
        super().__init__(parent)
        self.setObjectName("settings")
        self.setWindowTitle(f"{tr('settings')} – {APP_NAME}")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(18)

        self.lang = QComboBox(); self.lang.addItem("Ελληνικά", "el"); self.lang.addItem("English", "en")
        self.lang.setCurrentIndex(0 if s["lang"] == "el" else 1)
        self.tu = QComboBox(); self.tu.addItem("Κελσίου (°C)" if I18n.lang == "el" else "Celsius (°C)", "celsius")
        self.tu.addItem("Φαρενάιτ (°F)" if I18n.lang == "el" else "Fahrenheit (°F)", "fahrenheit")
        self.tu.setCurrentIndex(0 if s["temp_unit"] == "celsius" else 1)
        self.wu = QComboBox()
        for lbl, v in [("km/h", "kmh"), ("m/s", "ms"), ("mph", "mph"), ("knots (kn)", "kn")]:
            self.wu.addItem(lbl, v)
        self.wu.setCurrentIndex(max(0, self.wu.findData(s["wind_unit"])))
        self.iv = QSpinBox(); self.iv.setRange(5, 180); self.iv.setSingleStep(5)
        self.iv.setValue(int(s["interval_min"])); self.iv.setSuffix(tr("minutes"))
        self.tm = QComboBox(); self.tm.addItem(tr("tray_temp"), "temp"); self.tm.addItem(tr("tray_icon"), "icon")
        self.tm.setCurrentIndex(0 if s["tray_mode"] == "temp" else 1)
        form.addRow(tr("lang"), self.lang)
        form.addRow(tr("temp_unit"), self.tu)
        form.addRow(tr("wind_unit"), self.wu)
        form.addRow(tr("interval"), self.iv)
        form.addRow(tr("tray_show"), self.tm)
        lay.addLayout(form)
        lay.addSpacing(8)
        self.auto = QCheckBox(tr("autostart")); self.auto.setChecked(bool(s["autostart"]))
        self.auto.setEnabled(IS_WIN)
        self.rain = QCheckBox(tr("rain_notify")); self.rain.setChecked(bool(s["rain_notify"]))
        lay.addWidget(self.auto)
        lay.addWidget(self.rain)
        lay.addSpacing(10)
        bb = QDialogButtonBox()
        ok = bb.addButton(tr("save"), QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = bb.addButton(tr("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        lay.addWidget(bb)

    def values(self):
        return {"lang": self.lang.currentData(), "temp_unit": self.tu.currentData(),
                "wind_unit": self.wu.currentData(), "interval_min": self.iv.value(),
                "tray_mode": self.tm.currentData(), "autostart": self.auto.isChecked(),
                "rain_notify": self.rain.isChecked()}


# =================================================================
#  12. Controller (tray, χρονόμετρα, δεδομένα)
# =================================================================
class Controller(QObject):
    def __init__(self, app, start_hidden=False):
        super().__init__()
        self.app = app
        self.s = load_settings()
        I18n.lang = self.s.get("lang", "el")
        self.model = None
        self.raw = self.aq = None
        self.fetcher = None
        self.main = None
        self.flyout = None
        self.last_ok = 0.0
        self.last_rain_alert = 0.0
        self.suppress_until = 0.0

        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.activated.connect(self.on_tray)
        self.tray.messageClicked.connect(self.show_main)

        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.single_click)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(int(self.s["interval_min"]) * 60_000)

        self.retry_timer = QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self.refresh)

        self.build_menu()
        self.flyout = Flyout(self)
        self.load_cache()
        self.tray.show()
        self.refresh()
        if not start_hidden:
            self.show_main()

    # ---------- Tray clicks ----------
    def on_tray(self, reason):
        R = QSystemTrayIcon.ActivationReason
        now = time.monotonic()
        if reason == R.Trigger:
            if now < self.suppress_until:
                return
            self.click_timer.start(QApplication.doubleClickInterval())
        elif reason == R.DoubleClick:
            self.click_timer.stop()
            self.suppress_until = now + 0.35
            self.flyout.hide()
            self.show_main()
        elif reason == R.MiddleClick:
            self.refresh()

    def single_click(self):
        if self.flyout.isVisible():
            self.flyout.hide()
            return
        # αν μόλις έκλεισε από το ίδιο κλικ -> λειτουργία toggle
        if time.monotonic() - self.flyout.closed_at < QApplication.doubleClickInterval() / 1000 + 0.25:
            return
        self.flyout.set_model(self.model)
        self.flyout.show_near_tray(self.tray.geometry())
        if time.time() - self.last_ok > 10 * 60:
            self.refresh()

    # ---------- Μενού ----------
    def build_menu(self):
        old = self.tray.contextMenu()
        m = make_menu()
        a = m.addAction("⤢  " + tr("open_app")); a.triggered.connect(self.show_main)
        f = a.font(); f.setBold(True); a.setFont(f)
        m.addAction("⟳  " + tr("refresh")).triggered.connect(self.refresh)
        self.loc_menu = make_menu(m)
        self.loc_menu.setTitle("📍  " + tr("locations"))
        self.loc_menu.aboutToShow.connect(lambda: self.fill_locations_menu(self.loc_menu))
        m.addMenu(self.loc_menu)
        m.addSeparator()
        m.addAction("⚙  " + tr("settings")).triggered.connect(self.open_settings)
        m.addAction("ⓘ  " + tr("about")).triggered.connect(self.show_about)
        m.addSeparator()
        m.addAction("✕  " + tr("exit")).triggered.connect(self.quit)
        self.tray.setContextMenu(m)
        self._menu = m
        if old is not None:
            old.deleteLater()

    def fill_locations_menu(self, menu):
        menu.clear()
        cur = self.s["location"]
        grp = QActionGroup(menu)
        for loc in self.s.get("recent", []):
            label = ", ".join([x for x in (loc.get("name"), loc.get("country")) if x])
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(abs(loc["lat"] - cur["lat"]) < 1e-3 and abs(loc["lon"] - cur["lon"]) < 1e-3)
            grp.addAction(act)
            act.triggered.connect(lambda _=False, l=loc: self.set_location(l))
        menu.addSeparator()
        menu.addAction("🔍  " + tr("search") + "…").triggered.connect(self._focus_search)

    def _focus_search(self):
        self.show_main()
        self.main.search.setFocus()

    # ---------- Παράθυρα ----------
    def show_main(self):
        if self.main is None:
            self.main = MainWindow(self)
            self.main.set_model(self.model)
            if self.model is None:
                self.main.set_status(tr("loading"))
        if self.main.isMinimized():
            self.main.showNormal()
        self.main.show()
        self.main.raise_()
        self.main.activateWindow()

    def on_main_closed(self):
        if self.s.get("first_close_hint", True):
            self.tray.showMessage(APP_NAME, tr("running_tray"), app_icon(), 6000)
            self.s["first_close_hint"] = False
            save_settings(self.s)

    def rebuild_ui(self):
        was_visible = self.main is not None and self.main.isVisible()
        geo = self.main.saveGeometry() if self.main else None
        if self.main:
            self.main.hide()
            self.main.deleteLater()
            self.main = None
        self.flyout.hide()
        self.flyout.deleteLater()
        self.flyout = Flyout(self)
        self.build_menu()
        if self.raw:
            self.model = parse_model(self.raw, self.aq, self.s["location"], self.s)
        self.update_all()
        if was_visible:
            self.show_main()
            if geo:
                self.main.restoreGeometry(geo)

    def toggle_language(self):
        self.s["lang"] = "en" if self.s["lang"] == "el" else "el"
        I18n.lang = self.s["lang"]
        save_settings(self.s)
        self.rebuild_ui()

    def open_settings(self):
        parent = self.main if (self.main and self.main.isVisible()) else None
        dlg = SettingsDialog(self.s, parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        units_changed = v["temp_unit"] != self.s["temp_unit"] or v["wind_unit"] != self.s["wind_unit"]
        lang_changed = v["lang"] != self.s["lang"]
        if v["autostart"] != self.s["autostart"]:
            set_autostart(v["autostart"])
        self.s.update(v)
        save_settings(self.s)
        I18n.lang = self.s["lang"]
        self.refresh_timer.start(int(self.s["interval_min"]) * 60_000)
        if lang_changed:
            self.rebuild_ui()
        else:
            self.update_all()
        if units_changed:
            self.refresh(force=True)

    def show_about(self):
        box = QMessageBox(self.main if (self.main and self.main.isVisible()) else None)
        box.setWindowTitle(tr("about"))
        box.setIconPixmap(app_icon().pixmap(72, 72))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(tr("about_text").format(app=APP_NAME, ver=APP_VERSION, author=APP_AUTHOR, team=APP_TEAM))
        box.exec()

    def quit(self):
        self.tray.hide()
        if self.fetcher and self.fetcher.isRunning():
            self.fetcher.wait(3000)
        self.app.quit()

    # ---------- Δεδομένα ----------
    def set_location(self, loc):
        loc = {k: loc.get(k) for k in ("name", "admin1", "country", "lat", "lon")}
        self.s["location"] = loc
        rec = [r for r in self.s.get("recent", [])
               if not (abs(r["lat"] - loc["lat"]) < 1e-3 and abs(r["lon"] - loc["lon"]) < 1e-3)]
        self.s["recent"] = [loc] + rec[:7]
        save_settings(self.s)
        self.model = None
        self.update_all()
        self.refresh(force=True)

    def refresh(self, force=False):
        if self.fetcher and self.fetcher.isRunning():
            if not force:
                return
            try:
                self.fetcher.done.disconnect()
                self.fetcher.failed.disconnect()
            except Exception:
                pass
        if self.main:
            self.main.set_status("⟳  " + tr("loading"))
        self.fetcher = Fetcher(self.s["location"], self.s)
        self.fetcher.done.connect(self.on_data)
        self.fetcher.failed.connect(self.on_fail)
        self.fetcher.start()

    def on_data(self, raw, aq):
        try:
            self.model = parse_model(raw, aq, self.s["location"], self.s)
        except Exception as e:
            self.on_fail(f"parse: {e}")
            return
        self.raw, self.aq = raw, aq
        self.last_ok = time.time()
        self.retry_timer.stop()
        self.save_cache()
        self.update_all()
        if self.main:
            self.main.set_status(f"✓  {tr('updated')} {datetime.now().strftime('%H:%M')}")
        self.check_rain()

    def on_fail(self, err):
        if self.main:
            self.main.set_status("⚠  " + tr("err_net"))
        if self.model is None:
            self.tray.setToolTip(f"{APP_NAME}\n{tr('err_net')}")
        self.retry_timer.start(60_000)

    def update_all(self):
        m = self.model
        self.tray.setIcon(QIcon(tray_pixmap(m, self.s.get("tray_mode", "temp"))))
        if m:
            c = m["cur"]
            tip = (f"{m['loc'].get('name', '')}\n{fmt_t(c['temp'])}  {wmo_text(c['code'])}\n"
                   f"{tr('feels')} {fmt_t(c['feels'])} · 💧{int(c['hum'] or 0)}%")
            self.tray.setToolTip(tip[:127])
        else:
            self.tray.setToolTip(f"{APP_NAME}\n{tr('loading')}")
        if self.flyout:
            self.flyout.set_model(m)
        if self.main:
            self.main.set_model(m)

    def check_rain(self):
        if not self.s.get("rain_notify") or not self.model:
            return
        if time.time() - self.last_rain_alert < 3 * 3600:
            return
        m = self.model
        if wmo_kind(m["cur"]["code"]) in ("rain", "drizzle", "showers", "thunder", "snow"):
            return
        for h in m["hours"][1:4]:
            if (h["pop"] or 0) >= 70:
                self.tray.showMessage(tr("rain_t"),
                                      tr("rain_msg").format(p=int(h["pop"]), h=h["t"].strftime("%H:%M"),
                                                            c=m["loc"].get("name", "")),
                                      QSystemTrayIcon.MessageIcon.Information, 8000)
                self.last_rain_alert = time.time()
                break

    def save_cache(self):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"loc": self.s["location"], "units": [self.s["temp_unit"], self.s["wind_unit"]],
                           "raw": self.raw, "aq": self.aq}, f, ensure_ascii=False)
        except Exception:
            pass

    def load_cache(self):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                c = json.load(f)
            loc = self.s["location"]
            if (abs(c["loc"]["lat"] - loc["lat"]) < 1e-3 and abs(c["loc"]["lon"] - loc["lon"]) < 1e-3
                    and c.get("units") == [self.s["temp_unit"], self.s["wind_unit"]]):
                self.raw, self.aq = c["raw"], c.get("aq")
                self.model = parse_model(self.raw, self.aq, loc, self.s)
        except Exception:
            self.model = None
        self.update_all()


# =================================================================
#  13. main
# =================================================================
def main():
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nikkpap.TrayCast")
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    app.setStyleSheet(QSS)

    # Μόνο ένα αντίγραφο: αν τρέχει ήδη, του λέμε να ανοίξει το παράθυρο
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return 0
    QLocalServer.removeServer(INSTANCE_KEY)
    server = QLocalServer()
    server.listen(INSTANCE_KEY)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "System tray is not available on this system.")
        return 1

    ctrl = Controller(app, start_hidden="--tray" in sys.argv)

    def _on_conn():
        c = server.nextPendingConnection()
        if c:
            c.readyRead.connect(lambda: (c.readAll(), ctrl.show_main()))

    server.newConnection.connect(_on_conn)
    app._ctrl = ctrl
    app._server = server
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
