import sys, os, json, subprocess, requests, time, psutil, urllib3
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QHBoxLayout, 
                             QComboBox, QTextEdit, QDialog, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPoint
from PyQt6.QtGui import QIntValidator, QPainter, QColor, QPen, QFont

# Unterdrückt SSL-Warnungen für lokale Netzwerkumgebungen
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

# UPDATE ZIEL-VERSION
CURRENT_VERSION = "0.1.38"
VERSION_URL = "https://raw.githubusercontent.com/Gangarak/Guardian-Suite-Dist/main/version.json"
UPDATE_URL = "https://raw.githubusercontent.com/Gangarak/Guardian-Suite-Dist/main/main.py"

def get_gpu_load():
    try:
        # Direkte Abfrage über nvidia-smi (NVIDIA Grafikkarten)
        cmd = 'nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits'
        out = subprocess.check_output(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=0.5)
        return int(out.decode().strip().split('\n')[0])
    except:
        return 0

class CircularGauge(QWidget):
    def __init__(self, label, unit, color="#00ff99"):
        super().__init__()
        self.value = 0
        self.label_text = label
        self.unit_text = unit
        self.default_color = QColor(color)
        self.current_color = self.default_color
        self.setFixedSize(180, 220)

    def set_value(self, val, alert=False):
        self.value = val
        self.current_color = QColor("#ff4444") if alert else self.default_color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(40, 40, 40)); pen.setWidth(12); pen.setCapStyle(Qt.PenCapStyle.RoundCap); painter.setPen(pen)
        painter.drawArc(QRectF(20, 20, 140, 140), -225 * 16, 270 * 16)
        if self.value > 0:
            pen.setColor(self.current_color); painter.setPen(pen)
            span = int(min(float(self.value), 100.0) * 270 / 100)
            painter.drawArc(QRectF(20, 20, 140, 140), -225 * 16, -span * 16)
        painter.setPen(self.current_color); painter.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 55, 180, 40), Qt.AlignmentFlag.AlignCenter, f"{int(self.value)}")
        painter.setFont(QFont("Segoe UI", 11)); painter.drawText(QRectF(0, 95, 180, 25), Qt.AlignmentFlag.AlignCenter, self.unit_text)
        painter.setPen(QColor("#ffffff")); painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 185, 180, 30), Qt.AlignmentFlag.AlignCenter, self.label_text)

class DashboardWindow(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #050505;"); self.setFixedSize(800, 280)
        layout = QHBoxLayout(self); layout.setContentsMargins(10, 10, 10, 10)
        self.cpu_g = CircularGauge("CPU LAST", "%"); self.gpu_g = CircularGauge("GPU LAST", "%")
        self.ram_g = CircularGauge("RAM LAST", "%"); self.net_g = CircularGauge("INTERNET", "MB/s")
        for g in [self.cpu_g, self.gpu_g, self.ram_g, self.net_g]: layout.addWidget(g)
        self.last_net = psutil.net_io_counters().bytes_recv
        self.timer = QTimer(); self.timer.timeout.connect(self.refresh); self.timer.start(1000)
        self.dragPos = QPoint()

    def refresh(self):
        cpu = psutil.cpu_percent(); ram = psutil.virtual_memory().percent; gpu = get_gpu_load()
        net = round((psutil.net_io_counters().bytes_recv - self.last_net) / (1024 * 1024), 1)
        self.last_net = psutil.net_io_counters().bytes_recv
        lim = self.main_app.get_current_limits()
        self.cpu_g.set_value(cpu, cpu > lim['cpu']); self.ram_g.set_value(ram, ram > lim['ram'])
        self.gpu_g.set_value(gpu, gpu > lim['gpu']); self.net_g.set_value(net)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: self.dragPos = e.globalPosition().toPoint()
    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + e.globalPosition().toPoint() - self.dragPos)
            self.dragPos = e.globalPosition().toPoint()

class HUDOverlay(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); self.setFixedSize(280, 130)
        layout = QVBoxLayout(self)
        self.container = QWidget(); self.container.setStyleSheet("background-color: rgba(5, 5, 5, 220); border: 1px solid #00ff99; border-radius: 8px;")
        grid = QVBoxLayout(self.container)
        self.l_cpu = self.create_label("CPU: 0%"); self.l_gpu = self.create_label("GPU: 0%")
        self.l_ram = self.create_label("RAM: 0%"); self.l_net = self.create_label("NET: 0.0 MB/s")
        for l in [self.l_cpu, self.l_gpu, self.l_ram, self.l_net]: grid.addWidget(l)
        layout.addWidget(self.container)
        self.last_net = psutil.net_io_counters().bytes_recv
        self.timer = QTimer(); self.timer.timeout.connect(self.update_stats); self.timer.start(1000); self.move(10, 10)

    def create_label(self, text):
        return QLabel(text)

    def update_stats(self):
        cpu = psutil.cpu_percent(); ram = psutil.virtual_memory().percent; gpu = get_gpu_load()
        net = round((psutil.net_io_counters().bytes_recv - self.last_net) / (1024 * 1024), 1)
        self.last_net = psutil.net_io_counters().bytes_recv
        lim = self.main_app.get_current_limits()
        self.update_label(self.l_cpu, f"CPU: {cpu}%", cpu > lim['cpu'])
        self.update_label(self.l_ram, f"RAM: {ram}%", ram > lim['ram'])
        self.update_label(self.l_gpu, f"GPU: {gpu}%", gpu > lim['gpu'])
        self.l_net.setText(f"NET: {net} MB/s"); self.l_net.setStyleSheet("color: #00ff99; font-weight: bold; border: none;")

    def update_label(self, lbl, text, alert):
        color = "#ff4444" if alert else "#00ff99"
        lbl.setText(text); lbl.setStyleSheet(f"color: {color}; font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; border: none;")

class GuardianSuite(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_path = os.path.join(base_path, "profiles.json")
        self.dash_window = None; self.hud_overlay = None
        self.load_config(); self.setWindowTitle(f"Guardian Suite v{CURRENT_VERSION}"); self.setFixedSize(400, 850); self.init_ui()

    def load_config(self):
        default = {"Standard": {"cpu": 80, "gpu": 70, "ram": 95}}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f: self.profiles = json.load(f)
            except: self.profiles = default
        else: self.profiles = default

    def get_current_limits(self):
        try:
            return {"cpu": int(self.in_cpu.text()), "gpu": int(self.in_gpu.text()), "ram": int(self.in_ram.text())}
        except:
            return {"cpu": 80, "gpu": 70, "ram": 95}

    def init_ui(self):
        self.setStyleSheet("QMainWindow { background-color: #050505; } QWidget { color: #e0e0e0; font-family: 'Segoe UI'; }")
        central = QWidget(); self.setCentralWidget(central); layout = QVBoxLayout(central)
        layout.setContentsMargins(25, 25, 25, 25); layout.setSpacing(15)
        header = QLabel("GUARDIAN SUITE"); header.setStyleSheet("font-size: 28px; color: #00ff99; font-weight: 900;"); header.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(header)
        top_row = QHBoxLayout()
        btn_upd = QPushButton("💾 UPDATE CHECK"); btn_upd.clicked.connect(self.check_for_updates)
        btn_fdb = QPushButton("📣 FEEDBACK"); btn_fdb.clicked.connect(self.send_feedback)
        for b in [btn_upd, btn_fdb]: b.setStyleSheet("background: #1a1a1a; border: 1px solid #333; padding: 8px;"); top_row.addWidget(b)
        layout.addLayout(top_row); layout.addWidget(QLabel("PROFIL VERWALTUNG:"))
        self.profile_box = QComboBox(); self.profile_box.addItems(self.profiles.keys()); self.profile_box.currentIndexChanged.connect(self.switch_profile); layout.addWidget(self.profile_box)
        self.in_cpu = self.add_row(layout, "CPU LIMIT %", 1, 100); self.in_gpu = self.add_row(layout, "GPU LIMIT %", 1, 100); self.in_ram = self.add_row(layout, "RAM LIMIT %", 1, 100); self.switch_profile()
        btn_save = QPushButton("KONFIGURATION SPEICHERN"); btn_save.setStyleSheet("background: #00331a; border: 1px solid #00ff99; padding: 12px; font-weight: bold;"); btn_save.clicked.connect(self.save_profile); layout.addWidget(btn_save)
        self.status = QLabel("System bereit"); self.status.setAlignment(Qt.AlignmentFlag.AlignCenter); self.status.setStyleSheet("color: #00ff99; font-style: italic;"); layout.addWidget(self.status)
        layout.addStretch()
        self.btn_dash = QPushButton("DASHBOARD STARTEN"); self.btn_dash.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;"); self.btn_dash.clicked.connect(self.toggle_dashboard); layout.addWidget(self.btn_dash)
        self.btn_hud = QPushButton("HUD OVERLAY AKTIVIEREN"); self.btn_hud.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;"); self.btn_hud.clicked.connect(self.toggle_hud); layout.addWidget(self.btn_hud)

    def add_row(self, layout, label, min_v, max_v):
        row = QHBoxLayout(); row.addWidget(QLabel(label)); edit = QLineEdit(); edit.setFixedWidth(60); edit.setAlignment(Qt.AlignmentFlag.AlignCenter); edit.setValidator(QIntValidator(min_v, max_v)); edit.setStyleSheet("color: #00ff99; background: #000; border: 1px solid #00ff99; padding: 5px;"); row.addStretch(); row.addWidget(edit); layout.addLayout(row); return edit

    def toggle_dashboard(self):
        if self.dash_window is None: self.dash_window = DashboardWindow(self); self.dash_window.show(); self.btn_dash.setText("DASHBOARD STOPPEN"); self.btn_dash.setStyleSheet("border: 1px solid #ff4444; padding: 15px; font-weight: bold;")
        else: self.dash_window.close(); self.dash_window = None; self.btn_dash.setText("DASHBOARD STARTEN"); self.btn_dash.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")

    def toggle_hud(self):
        if self.hud_overlay is None: self.hud_overlay = HUDOverlay(self); self.hud_overlay.show(); self.btn_hud.setText("HUD DEAKTIVIEREN"); self.btn_hud.setStyleSheet("border: 1px solid #ff4444; padding: 15px; font-weight: bold;")
        else: self.hud_overlay.close(); self.hud_overlay = None; self.btn_hud.setText("HUD OVERLAY AKTIVIEREN"); self.btn_hud.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")

    def check_for_updates(self):
        self.status.setText("Prüfe GitHub...")
        try:
            ts = int(time.time())
            s = requests.Session(); s.trust_env = False
            r = s.get(f"{VERSION_URL}?nocache={ts}", timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json()
                remote_v = data.get("version", "")
                if remote_v != CURRENT_VERSION:
                    if QMessageBox.question(self, "Update", f"Version {remote_v} verfügbar! Jetzt installieren?") == QMessageBox.StandardButton.Yes:
                        self.download_and_install()
                else:
                    self.status.setText(f"v{CURRENT_VERSION} ist aktuell.")
            else:
                self.status.setText(f"HTTP Fehler {r.status_code}")
        except Exception as e:
            self.status.setText("Verbindung fehlgeschlagen")

    def download_and_install(self):
        try:
            ts = int(time.time())
            s = requests.Session(); s.trust_env = False
            r = s.get(f"{UPDATE_URL}?nocache={ts}", timeout=15, verify=False)
            if r.status_code == 200:
                with open(os.path.join(base_path, "main_new.py"), "wb") as f:
                    f.write(r.content)
                self.trigger_updater()
        except:
            self.status.setText("Download Fehler")

    def trigger_updater(self):
        b = os.path.join(base_path, "updater.bat")
        with open(b, "w") as f:
            # Der Batch-Updater wartet 2 Sekunden, ersetzt die Datei und startet sie neu
            f.write(f'@echo off\ntimeout /t 2\nmove /y "main_new.py" "main.py"\nstart "" "{sys.executable}" "main.py"\nexit\n')
        subprocess.Popen([b], shell=True); self.close(); sys.exit()

    def send_feedback(self):
        dlg = QDialog(self); dlg.setWindowTitle("Feedback"); dlg.setFixedSize(300, 200); l = QVBoxLayout(dlg); e = QTextEdit(); l.addWidget(e); b = QPushButton("Senden"); b.clicked.connect(dlg.accept); l.addWidget(b)
        if dlg.exec():
            msg = e.toPlainText().strip()
            if msg:
                try: 
                    s = requests.Session(); s.trust_env = False
                    s.post("https://discord.com/api/webhooks/1504479025781936339/NvoI5gDJnYqFZgpE2_TXgXQqEG8q9Ofs4SU5k1ziQfbfY7F8du-pIYKoctw8gYPGUQfm", json={"content": f"**Feedback v{CURRENT_VERSION}:**\n> {msg}"}, verify=False)
                except: pass

    def switch_profile(self):
        p = self.profiles.get(self.profile_box.currentText(), {"cpu": 80, "gpu": 70, "ram": 95})
        self.in_cpu.setText(str(p.get("cpu", 80))); self.in_gpu.setText(str(p.get("gpu", 70))); self.in_ram.setText(str(p.get("ram", 95)))

    def save_profile(self):
        n = self.profile_box.currentText(); self.profiles[n] = {"cpu": int(self.in_cpu.text()), "gpu": int(self.in_gpu.text()), "ram": int(self.in_ram.text())}
        with open(self.config_path, "w") as f: json.dump(self.profiles, f, indent=4)
        self.status.setText("Gesichert.")

if __name__ == "__main__":
    app = QApplication(sys.argv); w = GuardianSuite(); w.show(); sys.exit(app.exec())
