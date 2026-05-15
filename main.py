import sys, os, json, subprocess, requests, time, psutil, urllib3
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QHBoxLayout, 
                             QComboBox, QTextEdit, QDialog, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPoint
from PyQt6.QtGui import QIntValidator, QPainter, QColor, QPen, QFont

# Unterdrückt SSL-Warnungen
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Pfad-Logik für den EXE-Betrieb
if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
    exe_path = sys.executable
else:
    base_path = os.path.dirname(os.path.abspath(__file__))
    exe_path = None

# KONFIGURATION
CURRENT_VERSION = "0.1.38"
VERSION_URL = "https://raw.githubusercontent.com/Gangarak/Guardian-Suite-Dist/main/version.json"
UPDATE_URL_EXE = "https://raw.githubusercontent.com/Gangarak/Guardian-Suite-Dist/main/GuardianSuite.exe"

def get_gpu_load():
    try:
        cmd = 'nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits'
        out = subprocess.check_output(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=0.5)
        return int(out.decode().strip().split('\n')[0])
    except: return 0

class CircularGauge(QWidget):
    def __init__(self, label, unit, color="#00ff99"):
        super().__init__(); self.value = 0; self.label_text = label; self.unit_text = unit
        self.default_color = QColor(color); self.current_color = self.default_color; self.setFixedSize(180, 220)
    def set_value(self, val, alert=False):
        self.value = val; self.current_color = QColor("#ff4444") if alert else self.default_color; self.update()
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(40, 40, 40)); pen.setWidth(12); p.setPen(pen)
        p.drawArc(QRectF(20, 20, 140, 140), -225 * 16, 270 * 16)
        if self.value > 0:
            pen.setColor(self.current_color); p.setPen(pen)
            span = int(min(float(self.value), 100.0) * 270 / 100); p.drawArc(QRectF(20, 20, 140, 140), -225 * 16, -span * 16)
        p.setPen(self.current_color); p.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        p.drawText(QRectF(0, 55, 180, 40), Qt.AlignmentFlag.AlignCenter, f"{int(self.value)}")
        p.setFont(QFont("Segoe UI", 11)); p.drawText(QRectF(0, 95, 180, 25), Qt.AlignmentFlag.AlignCenter, self.unit_text)
        p.setPen(QColor("#ffffff")); p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.drawText(QRectF(0, 185, 180, 30), Qt.AlignmentFlag.AlignCenter, self.label_text)

class DashboardWindow(QWidget):
    def __init__(self, main_app):
        super().__init__(); self.main_app = main_app; self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #050505;"); self.setFixedSize(800, 280); layout = QHBoxLayout(self)
        self.cpu_g = CircularGauge("CPU LAST", "%"); self.gpu_g = CircularGauge("GPU LAST", "%")
        self.ram_g = CircularGauge("RAM LAST", "%"); self.net_g = CircularGauge("INTERNET", "MB/s")
        for g in [self.cpu_g, self.gpu_g, self.ram_g, self.net_g]: layout.addWidget(g)
        self.last_net = psutil.net_io_counters().bytes_recv; self.timer = QTimer(); self.timer.timeout.connect(self.refresh); self.timer.start(1000); self.dragPos = QPoint()
    def refresh(self):
        cpu = psutil.cpu_percent(); ram = psutil.virtual_memory().percent; gpu = get_gpu_load()
        net = round((psutil.net_io_counters().bytes_recv - self.last_net) / (1024 * 1024), 1)
        self.last_net = psutil.net_io_counters().bytes_recv; lim = self.main_app.get_current_limits()
        self.cpu_g.set_value(cpu, cpu > lim['cpu']); self.ram_g.set_value(ram, ram > lim['ram'])
        self.gpu_g.set_value(gpu, gpu > lim['gpu']); self.net_g.set_value(net)
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: self.dragPos = e.globalPosition().toPoint()
    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton: self.move(self.pos() + e.globalPosition().toPoint() - self.dragPos); self.dragPos = e.globalPosition().toPoint()

class HUDOverlay(QWidget):
    def __init__(self, main_app):
        super().__init__(); self.main_app = main_app
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); self.setFixedSize(280, 130); layout = QVBoxLayout(self)
        self.container = QWidget(); self.container.setStyleSheet("background-color: rgba(5, 5, 5, 220); border: 1px solid #00ff99; border-radius: 8px;")
        grid = QVBoxLayout(self.container); self.l_cpu = QLabel("CPU: 0%"); self.l_gpu = QLabel("GPU: 0%"); self.l_ram = QLabel("RAM: 0%"); self.l_net = QLabel("NET: 0.0 MB/s")
        for l in [self.l_cpu, self.l_gpu, self.l_ram, self.l_net]: grid.addWidget(l)
        layout.addWidget(self.container); self.last_net = psutil.net_io_counters().bytes_recv; self.timer = QTimer(); self.timer.timeout.connect(self.update_stats); self.timer.start(1000); self.move(10, 10)
    def update_stats(self):
        cpu = psutil.cpu_percent(); ram = psutil.virtual_memory().percent; gpu = get_gpu_load()
        net = round((psutil.net_io_counters().bytes_recv - self.last_net) / (1024 * 1024), 1); self.last_net = psutil.net_io_counters().bytes_recv
        lim = self.main_app.get_current_limits()
        for lbl, txt, val, limit in [(self.l_cpu, "CPU", cpu, lim['cpu']), (self.l_ram, "RAM", ram, lim['ram']), (self.l_gpu, "GPU", gpu, lim['gpu'])]:
            color = "#ff4444" if val > limit else "#00ff99"
            lbl.setText(f"{txt}: {val}%"); lbl.setStyleSheet(f"color: {color}; font-weight: bold; border: none;")
        self.l_net.setText(f"NET: {net} MB/s"); self.l_net.setStyleSheet("color: #00ff99; font-weight: bold; border: none;")

class GuardianSuite(QMainWindow):
    def __init__(self):
        super().__init__(); self.config_path = os.path.join(base_path, "profiles.json"); self.dash_window = None; self.hud_overlay = None
        self.load_config(); self.setWindowTitle(f"Guardian Suite v{CURRENT_VERSION}"); self.setFixedSize(400, 850); self.init_ui()
    
    def load_config(self):
        d = {"Standard": {"cpu": 80, "gpu": 70, "ram": 95}}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f: self.profiles = json.load(f)
            except: self.profiles = d
        else: self.profiles = d

    def get_current_limits(self):
        try: return {"cpu": int(self.in_cpu.text()), "gpu": int(self.in_gpu.text()), "ram": int(self.in_ram.text())}
        except: return {"cpu": 80, "gpu": 70, "ram": 95}

    def init_ui(self):
        self.setStyleSheet("QMainWindow { background-color: #050505; } QWidget { color: #e0e0e0; font-family: 'Segoe UI'; }")
        central = QWidget(); self.setCentralWidget(central); layout = QVBoxLayout(central); layout.setContentsMargins(25, 25, 25, 25); layout.setSpacing(15)
        h = QLabel("GUARDIAN SUITE"); h.setStyleSheet("font-size: 28px; color: #00ff99; font-weight: 900;"); h.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(h)
        tr = QHBoxLayout(); b_upd = QPushButton("💾 UPDATE CHECK"); b_upd.clicked.connect(self.check_for_updates); b_fdb = QPushButton("📣 FEEDBACK"); b_fdb.clicked.connect(self.send_feedback)
        for b in [b_upd, b_fdb]: b.setStyleSheet("background: #1a1a1a; border: 1px solid #333; padding: 8px;"); tr.addWidget(b)
        layout.addLayout(tr); layout.addWidget(QLabel("PROFIL VERWALTUNG:"))
        self.profile_box = QComboBox(); self.profile_box.addItems(self.profiles.keys()); self.profile_box.currentIndexChanged.connect(self.switch_profile); layout.addWidget(self.profile_box)
        self.in_cpu = self.add_row(layout, "CPU LIMIT %"); self.in_gpu = self.add_row(layout, "GPU LIMIT %"); self.in_ram = self.add_row(layout, "RAM LIMIT %"); self.switch_profile()
        b_save = QPushButton("KONFIGURATION SPEICHERN"); b_save.setStyleSheet("background: #00331a; border: 1px solid #00ff99; padding: 12px; font-weight: bold;"); b_save.clicked.connect(self.save_profile); layout.addWidget(b_save)
        self.status = QLabel("System bereit"); self.status.setAlignment(Qt.AlignmentFlag.AlignCenter); self.status.setStyleSheet("color: #00ff99; font-style: italic;"); layout.addWidget(self.status); layout.addStretch()
        self.b_dash = QPushButton("DASHBOARD STARTEN"); self.b_dash.clicked.connect(self.toggle_dashboard); self.b_hud = QPushButton("HUD OVERLAY AKTIVIEREN"); self.b_hud.clicked.connect(self.toggle_hud)
        for b in [self.b_dash, self.b_hud]: b.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;"); layout.addWidget(b)

    def add_row(self, layout, label):
        row = QHBoxLayout(); row.addWidget(QLabel(label)); edit = QLineEdit(); edit.setFixedWidth(60); edit.setAlignment(Qt.AlignmentFlag.AlignCenter); edit.setValidator(QIntValidator(1, 100)); edit.setStyleSheet("color: #00ff99; background: #000; border: 1px solid #00ff99; padding: 5px;"); row.addStretch(); row.addWidget(edit); layout.addLayout(row); return edit

    def toggle_dashboard(self):
        if self.dash_window is None: self.dash_window = DashboardWindow(self); self.dash_window.show(); self.b_dash.setText("DASHBOARD STOPPEN"); self.b_dash.setStyleSheet("border: 1px solid #ff4444; padding: 15px; font-weight: bold;")
        else: self.dash_window.close(); self.dash_window = None; self.b_dash.setText("DASHBOARD STARTEN"); self.b_dash.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")

    def toggle_hud(self):
        if self.hud_overlay is None: self.hud_overlay = HUDOverlay(self); self.hud_overlay.show(); self.b_hud.setText("HUD DEAKTIVIEREN"); self.b_hud.setStyleSheet("border: 1px solid #ff4444; padding: 15px; font-weight: bold;")
        else: self.hud_overlay.close(); self.hud_overlay = None; self.b_hud.setText("HUD OVERLAY AKTIVIEREN"); self.b_hud.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")

    def check_for_updates(self):
        self.status.setText("Prüfe GitHub...")
        try:
            r = requests.get(f"{VERSION_URL}?t={int(time.time())}", timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json(); remote_v = data.get("version", "")
                if remote_v != CURRENT_VERSION:
                    if QMessageBox.question(self, "Update", f"v{remote_v} verfügbar. Installieren?") == QMessageBox.StandardButton.Yes: self.download_and_install()
                else: self.status.setText(f"v{CURRENT_VERSION} aktuell.")
            else: self.status.setText(f"HTTP Fehler: {r.status_code}")
        except: self.status.setText("Verbindung fehlgeschlagen")

    def download_and_install(self):
        if not getattr(sys, 'frozen', False):
            self.status.setText("Update nur als EXE möglich.")
            return
        self.status.setText("Lade Update...")
        try:
            r = requests.get(UPDATE_URL_EXE, timeout=60, verify=False, stream=True)
            if r.status_code == 200:
                new_exe = os.path.join(base_path, "GuardianSuite_new.exe")
                with open(new_exe, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                self.status.setText("Download fertig!")
                QTimer.singleShot(1000, lambda: self.apply_update_and_exit(new_exe))
            else:
                self.status.setText(f"Download-Fehler: {r.status_code}")
        except Exception as e:
            self.status.setText("Fehler beim Laden.")

    def apply_update_and_exit(self, new_exe_path):
        batch_path = os.path.join(base_path, "apply_update.bat")
        current_exe = exe_path
        batch_content = f'''@echo off
timeout /t 2 /nobreak > nul
taskkill /F /IM GuardianSuite.exe /T > nul 2>&1
del /f /q "{current_exe}"
ren "{new_exe_path}" "GuardianSuite.exe"
start "" "GuardianSuite.exe"
del "%~f0"
exit
'''
        try:
            with open(batch_path, "w") as f: f.write(batch_content)
            subprocess.Popen([batch_path], shell=True)
            self.close(); sys.exit()
        except: self.status.setText("Batch-Fehler!")

    def send_feedback(self):
        dlg = QDialog(self); dlg.setWindowTitle("Feedback"); dlg.setFixedSize(300, 200); l = QVBoxLayout(dlg); e = QTextEdit(); l.addWidget(e); b = QPushButton("Senden"); b.clicked.connect(dlg.accept); l.addWidget(b)
        if dlg.exec():
            msg = e.toPlainText().strip()
            if msg:
                try: requests.post("https://discord.com/api/webhooks/1504479025781936339/NvoI5gDJnYqFZgpE2_TXgXQqEG8q9Ofs4SU5k1ziQfbfY7F8du-pIYKoctw8gYPGUQfm", json={"content": f"**Feedback v{CURRENT_VERSION}:**\n> {msg}"}, verify=False)
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
