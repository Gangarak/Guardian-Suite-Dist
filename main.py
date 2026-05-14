import sys
import os
import json
import subprocess
import requests
import re
import time
import psutil
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QHBoxLayout, 
                             QComboBox, QTextEdit, QDialog, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPoint
from PyQt6.QtGui import QIntValidator, QPainter, QColor, QPen, QFont

# Dynamischer Pfad für EXE-Betrieb
if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = r"C:\Users\Marcel\Guardian-Suite"

CURRENT_VERSION = "0.1.35"
VERSION_URL = "https://raw.githubusercontent.com/Gangarak/Guardian-Suite-Dist/main/version.json"
UPDATE_URL = "https://raw.githubusercontent.com/Gangarak/Guardian-Suite-Dist/main/main.py"

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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Hintergrund-Ring
        pen = QPen(QColor(40, 40, 40))
        pen.setWidth(12)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(QRectF(20, 20, 140, 140), -225 * 16, 270 * 16)
        
        # Aktiver Wert-Ring
        if self.value > 0:
            pen.setColor(self.current_color)
            painter.setPen(pen)
            span = int(min(float(self.value), 100.0) * 270 / 100)
            painter.drawArc(QRectF(20, 20, 140, 140), -225 * 16, -span * 16)
            
        painter.setPen(self.current_color)
        painter.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 55, 180, 40), Qt.AlignmentFlag.AlignCenter, f"{int(self.value)}")
        
        painter.setFont(QFont("Segoe UI", 11))
        painter.drawText(QRectF(0, 95, 180, 25), Qt.AlignmentFlag.AlignCenter, self.unit_text)
        
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 185, 180, 30), Qt.AlignmentFlag.AlignCenter, self.label_text)

class DashboardWindow(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #050505;")
        self.setFixedSize(800, 280)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        self.cpu_g = CircularGauge("CPU LAST", "%")
        self.gpu_g = CircularGauge("GPU TEMP", "°C")
        self.ram_g = CircularGauge("RAM LAST", "%")
        self.net_g = CircularGauge("INTERNET", "MB/s")
        
        for g in [self.cpu_g, self.gpu_g, self.ram_g, self.net_g]:
            layout.addWidget(g)
            
        psutil.cpu_percent()
        self.last_net = psutil.net_io_counters().bytes_recv
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.dragPos = QPoint()

    def refresh(self):
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        gpu = 55  # Platzhalter für GPU
        now_net = psutil.net_io_counters().bytes_recv
        net_val = round((now_net - self.last_net) / (1024 * 1024), 1)
        self.last_net = now_net
        
        limits = self.main_app.get_current_limits()
        self.cpu_g.set_value(cpu, alert=(cpu > limits['cpu']))
        self.ram_g.set_value(ram, alert=(ram > limits['ram']))
        self.gpu_g.set_value(gpu, alert=(gpu > limits['gpu']))
        self.net_g.set_value(net_val)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.dragPos = e.globalPosition().toPoint()
            
    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + e.globalPosition().toPoint() - self.dragPos)
            self.dragPos = e.globalPosition().toPoint()

class HUDOverlay(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(280, 130)
        
        layout = QVBoxLayout(self)
        self.container = QWidget()
        self.container.setStyleSheet("background-color: rgba(5, 5, 5, 200); border: 1px solid #00ff99; border-radius: 8px;")
        grid = QVBoxLayout(self.container)
        
        self.l_cpu = self.create_label("CPU: 0%")
        self.l_gpu = self.create_label("GPU: 55°C")
        self.l_ram = self.create_label("RAM: 0%")
        self.l_net = self.create_label("NET: 0.0 MB/s")
        
        for l in [self.l_cpu, self.l_gpu, self.l_ram, self.l_net]:
            grid.addWidget(l)
        layout.addWidget(self.container)
        
        psutil.cpu_percent()
        self.last_net = psutil.net_io_counters().bytes_recv
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1000)
        self.move(10, 10)

    def create_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #00ff99; font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; border: none;")
        return lbl

    def update_stats(self):
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        gpu = 55
        now_net = psutil.net_io_counters().bytes_recv
        net_val = round((now_net - self.last_net) / (1024 * 1024), 1)
        self.last_net = now_net
        
        limits = self.main_app.get_current_limits()
        
        self.update_label(self.l_cpu, f"CPU: {cpu}%", cpu > limits['cpu'])
        self.update_label(self.l_ram, f"RAM: {ram}%", ram > limits['ram'])
        self.update_label(self.l_gpu, f"GPU: {gpu}°C", gpu > limits['gpu'])
        self.l_net.setText(f"NET: {net_val} MB/s")

    def update_label(self, lbl, text, alert):
        color = "#ff4444" if alert else "#00ff99"
        lbl.setText(text)
        lbl.setStyleSheet(f"color: {color}; font-family: 'Segoe UI'; font-size: 13px; font-weight: bold; border: none;")

class GuardianSuite(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_path = os.path.join(base_path, "profiles.json")
        self.dash_window = None
        self.hud_overlay = None
        self.load_config()
        self.setWindowTitle(f"Guardian Suite v{CURRENT_VERSION}")
        self.setFixedSize(400, 850) 
        self.init_ui()

    def load_config(self):
        default = {"Standard": {"cpu": 80, "gpu": 70, "ram": 95}}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f: self.profiles = json.load(f)
            except: self.profiles = default
        else: self.profiles = default

    def get_current_limits(self):
        try:
            return {
                "cpu": int(self.in_cpu.text()),
                "gpu": int(self.in_gpu.text()),
                "ram": int(self.in_ram.text())
            }
        except:
            return {"cpu": 80, "gpu": 70, "ram": 95}

    def init_ui(self):
        self.setStyleSheet("QMainWindow { background-color: #050505; } QWidget { color: #e0e0e0; font-family: 'Segoe UI'; }")
        central = QWidget(); self.setCentralWidget(central); layout = QVBoxLayout(central)
        layout.setContentsMargins(25, 25, 25, 25); layout.setSpacing(15)
        
        header = QLabel("GUARDIAN SUITE")
        header.setStyleSheet("font-size: 28px; color: #00ff99; font-weight: 900;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(header)
        
        top_row = QHBoxLayout()
        btn_upd = QPushButton("💾 UPDATE CHECK"); btn_upd.clicked.connect(self.check_for_updates)
        btn_fdb = QPushButton("📣 FEEDBACK"); btn_fdb.clicked.connect(self.send_feedback)
        for b in [btn_upd, btn_fdb]: 
            b.setStyleSheet("background: #1a1a1a; border: 1px solid #333; padding: 8px;")
            top_row.addWidget(b)
        layout.addLayout(top_row)

        layout.addWidget(QLabel("PROFIL VERWALTUNG:"))
        self.profile_box = QComboBox(); self.profile_box.addItems(self.profiles.keys())
        self.profile_box.currentIndexChanged.connect(self.switch_profile); layout.addWidget(self.profile_box)
        
        self.in_cpu = self.add_row(layout, "CPU LIMIT %", 1, 100)
        self.in_gpu = self.add_row(layout, "GPU ALARM °C", 30, 110)
        self.in_ram = self.add_row(layout, "RAM LIMIT %", 1, 100)
        self.switch_profile()

        btn_save = QPushButton("KONFIGURATION SPEICHERN")
        btn_save.setStyleSheet("background: #00331a; border: 1px solid #00ff99; padding: 12px; font-weight: bold;")
        btn_save.clicked.connect(self.save_profile); layout.addWidget(btn_save)

        self.status = QLabel("System bereit")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("color: #00ff99; font-style: italic;"); layout.addWidget(self.status)

        layout.addStretch()
        
        self.btn_dash = QPushButton("DASHBOARD STARTEN")
        self.btn_dash.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")
        self.btn_dash.clicked.connect(self.toggle_dashboard)
        layout.addWidget(self.btn_dash)

        self.btn_hud = QPushButton("HUD OVERLAY AKTIVIEREN")
        self.btn_hud.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")
        self.btn_hud.clicked.connect(self.toggle_hud)
        layout.addWidget(self.btn_hud)

    def add_row(self, layout, label, min_v, max_v):
        row = QHBoxLayout(); row.addWidget(QLabel(label))
        edit = QLineEdit(); edit.setFixedWidth(60); edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        edit.setValidator(QIntValidator(min_v, max_v))
        edit.setStyleSheet("color: #00ff99; background: #000; border: 1px solid #00ff99; padding: 5px;")
        row.addStretch(); row.addWidget(edit); layout.addLayout(row); return edit

    def toggle_dashboard(self):
        if self.dash_window is None:
            self.dash_window = DashboardWindow(self); self.dash_window.show()
            self.btn_dash.setText("DASHBOARD STOPPEN"); self.btn_dash.setStyleSheet("border: 1px solid #ff4444; padding: 15px; font-weight: bold;")
        else:
            self.dash_window.close(); self.dash_window = None
            self.btn_dash.setText("DASHBOARD STARTEN"); self.btn_dash.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")

    def toggle_hud(self):
        if self.hud_overlay is None:
            self.hud_overlay = HUDOverlay(self); self.hud_overlay.show()
            self.btn_hud.setText("HUD DEAKTIVIEREN"); self.btn_hud.setStyleSheet("border: 1px solid #ff4444; padding: 15px; font-weight: bold;")
        else:
            self.hud_overlay.close(); self.hud_overlay = None
            self.btn_hud.setText("HUD OVERLAY AKTIVIEREN"); self.btn_hud.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")

def check_for_updates(self):
        self.status.setText("Prüfe Version...")
        # Header hinzufügen, um wie ein Browser auszusehen (verhindert Blockaden)
        headers = {'User-Agent': 'Mozilla/5.0'}
        try:
            # t= Zeitstempel verhindert, dass Windows eine alte Version aus dem Cache lädt
            r = requests.get(f"{VERSION_URL}?t={int(time.time())}", headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                remote_v = data.get("version", "")
                if remote_v != CURRENT_VERSION:
                    self.status.setText(f"Update v{remote_v} verfügbar!")
                    if QMessageBox.question(self, "Update verfügbar", f"Version {remote_v} ist da. Jetzt installieren?") == QMessageBox.StandardButton.Yes:
                        self.download_and_install()
                else:
                    self.status.setText(f"v{CURRENT_VERSION} ist aktuell.")
            else:
                self.status.setText(f"Server-Fehler: {r.status_code}")
        except Exception as e:
            print(f"Update Fehler: {e}")
            self.status.setText("Keine Verbindung zum Server")
          
    def download_and_install(self):
        try:
            r = requests.get(UPDATE_URL, timeout=15)
            if r.status_code == 200:
                new_path = os.path.join(base_path, "main_new.py")
                with open(new_path, "wb") as f: f.write(r.content)
                self.trigger_updater()
        except: pass

    def trigger_updater(self):
        batch_path = os.path.join(base_path, "updater.bat")
        py_exe = sys.executable
        with open(batch_path, "w") as f:
            f.write(f'@echo off\ntimeout /t 2\nmove /y "{base_path}\\main_new.py" "{base_path}\\main.py"\nstart "" "{py_exe}" "{base_path}\\main.py"\nexit\n')
        subprocess.Popen([batch_path], shell=True); self.close(); sys.exit()

    def send_feedback(self):
        dlg = QDialog(self); dlg.setWindowTitle("Feedback"); dlg.setFixedSize(300, 200)
        layout = QVBoxLayout(dlg); edit = QTextEdit(); layout.addWidget(edit)
        btn = QPushButton("Senden"); btn.clicked.connect(dlg.accept); layout.addWidget(btn)
        if dlg.exec():
            msg = edit.toPlainText().strip()
            if msg:
                webhook = "https://discord.com/api/webhooks/1504479025781936339/NvoI5gDJnYqFZgpE2_TXgXQqEG8q9Ofs4SU5k1ziQfbfY7F8du-pIYKoctw8gYPGUQfm"
                try: requests.post(webhook, json={"content": f"**Feedback v{CURRENT_VERSION}:**\n> {msg}"})
                except: pass

    def switch_profile(self):
        p = self.profiles.get(self.profile_box.currentText(), {"cpu": 80, "gpu": 70, "ram": 95})
        self.in_cpu.setText(str(p.get("cpu", 80))); self.in_gpu.setText(str(p.get("gpu", 70))); self.in_ram.setText(str(p.get("ram", 95)))

    def save_profile(self):
        name = self.profile_box.currentText()
        self.profiles[name] = {"cpu": int(self.in_cpu.text()), "gpu": int(self.in_gpu.text()), "ram": int(self.in_ram.text())}
        with open(self.config_path, "w") as f: json.dump(self.profiles, f, indent=4)
        self.status.setText("Profil gesichert.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = GuardianSuite()
    w.show()
    sys.exit(app.exec())
