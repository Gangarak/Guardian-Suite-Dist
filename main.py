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

# Konfiguration - Marcel (Oberhausen)
base_path = r"C:\Users\Marcel\Guardian-Suite"
CURRENT_VERSION = "0.1.31"
VERSION_URL = "https://raw.githubusercontent.com/Gangarak/Guardian-Suite-Dist/main/version.json"
UPDATE_URL = "https://raw.githubusercontent.com/Gangarak/Guardian-Suite-Dist/main/main.py"

# --- DASHBOARD KOMPONENTEN ---

class CircularGauge(QWidget):
    """Die kreisförmige Anzeige aus dem Dashboard-Layout."""
    def __init__(self, label, unit, color="#00ff99"):
        super().__init__()
        self.value = 0
        self.label_text = label
        self.unit_text = unit
        self.color = QColor(color)
        self.setFixedSize(180, 220)

    def set_value(self, val):
        self.value = val
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Hintergrund-Kreis (Dunkel)
        pen = QPen(QColor(40, 40, 40))
        pen.setWidth(12)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(QRectF(20, 20, 140, 140), -225 * 16, 270 * 16)
        
        # Fortschritt (Neon-Grün)
        if self.value > 0:
            pen.setColor(self.color)
            painter.setPen(pen)
            span = int(min(float(self.value), 100.0) * 270 / 100)
            painter.drawArc(QRectF(20, 20, 140, 140), -225 * 16, -span * 16)
            
        # Text-Anzeigen
        painter.setPen(QColor("#00ff99"))
        painter.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 55, 180, 40), Qt.AlignmentFlag.AlignCenter, f"{int(self.value)}")
        painter.setFont(QFont("Segoe UI", 11))
        painter.drawText(QRectF(0, 95, 180, 25), Qt.AlignmentFlag.AlignCenter, self.unit_text)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 185, 180, 30), Qt.AlignmentFlag.AlignCenter, self.label_text)

class DashboardWindow(QWidget):
    """Das separate Dashboard-Fenster (Rahmenlos & Beweglich)."""
    def __init__(self):
        super().__init__()
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
        now_net = psutil.net_io_counters().bytes_recv
        self.cpu_g.set_value(psutil.cpu_percent())
        self.ram_g.set_value(psutil.virtual_memory().percent)
        self.net_g.set_value(round((now_net - self.last_net) / (1024 * 1024), 1))
        self.last_net = now_net
        self.gpu_g.set_value(55)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.dragPos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + e.globalPosition().toPoint() - self.dragPos)
            self.dragPos = e.globalPosition().toPoint()

# --- HAUPTPROGRAMM ---

class FeedbackDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Guardian Feedback")
        self.setFixedSize(350, 250)
        self.setStyleSheet("background-color: #0a0a0a; color: #fff; border: 1px solid #00ff99;")
        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Was können wir verbessern?")
        self.text_edit.setStyleSheet("background: #000; border: 1px solid #333; color: #00ff99; padding: 5px;")
        layout.addWidget(QLabel("FEEDBACK AN ENTWICKLER:"))
        layout.addWidget(self.text_edit)
        btn = QPushButton("SENDEN")
        btn.setStyleSheet("background: #00ff99; color: #000; font-weight: bold; padding: 10px;")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

class GuardianSuite(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_path = os.path.join(base_path, "profiles.json")
        self.dash_window = None
        self.load_config()
        self.setWindowTitle(f"Guardian Suite v{CURRENT_VERSION}")
        self.setFixedSize(400, 800) 
        self.init_ui()

    def load_config(self):
        default = {"Standard": {"cpu": 80, "gpu": 70, "ram": 95}}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f: self.profiles = json.load(f)
            except: self.profiles = default
        else: self.profiles = default

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
        
        # Dashboard Toggle Button
        self.btn_dash = QPushButton("DASHBOARD STARTEN")
        self.btn_dash.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")
        self.btn_dash.clicked.connect(self.toggle_dashboard)
        layout.addWidget(self.btn_dash)

    def add_row(self, layout, label, min_v, max_v):
        row = QHBoxLayout(); row.addWidget(QLabel(label))
        edit = QLineEdit(); edit.setFixedWidth(60); edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        edit.setValidator(QIntValidator(min_v, max_v))
        edit.setStyleSheet("color: #00ff99; background: #000; border: 1px solid #00ff99; padding: 5px;")
        row.addStretch(); row.addWidget(edit); layout.addLayout(row); return edit

    def toggle_dashboard(self):
        if self.dash_window is None:
            self.dash_window = DashboardWindow()
            self.dash_window.show()
            self.btn_dash.setText("DASHBOARD STOPPEN")
            self.btn_dash.setStyleSheet("border: 1px solid #ff4444; padding: 15px; font-weight: bold;")
        else:
            self.dash_window.close()
            self.dash_window = None
            self.btn_dash.setText("DASHBOARD STARTEN")
            self.btn_dash.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")

    def check_for_updates(self):
        self.status.setText("Prüfe Version...")
        try:
            r = requests.get(f"{VERSION_URL}?t={int(time.time())}", timeout=5)
            if r.status_code == 200:
                match = re.search(r'"version":\s*"([^"]+)"', r.text)
                if match:
                    remote_v = match.group(1).strip()
                    if remote_v != CURRENT_VERSION:
                        if QMessageBox.question(self, "Update", f"v{remote_v} verfügbar?") == QMessageBox.StandardButton.Yes:
                            self.download_and_install()
                    else: self.status.setText(f"Aktuell (v{CURRENT_VERSION})")
        except: self.status.setText("Verbindungsfehler")

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
        dlg = FeedbackDialog(self)
        if dlg.exec():
            msg = dlg.text_edit.toPlainText().strip()
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
