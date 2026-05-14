import sys
import os
import json
import subprocess
import requests
import re
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QHBoxLayout, 
                             QComboBox, QTextEdit, QDialog, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator

# Konfiguration - Marcel (Oberhausen)
base_path = r"C:\Users\Marcel\Guardian-Suite"
CURRENT_VERSION = "0.1.31"
VERSION_URL = "https://raw.githubusercontent.com/Gangarak/Guardian-Suite-Dist/main/version.json"
UPDATE_URL = "https://raw.githubusercontent.com/Gangarak/Guardian-Suite-Dist/main/main.py"

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
        self.processes = {"HUD": None, "Dashboard": None}
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
        self.add_mod_btn(layout, "DASHBOARD STARTEN", "dashboard.py", "Dashboard")
        self.add_mod_btn(layout, "HUD STARTEN", "hud.py", "HUD")

    def add_row(self, layout, label, min_v, max_v):
        row = QHBoxLayout(); row.addWidget(QLabel(label))
        edit = QLineEdit(); edit.setFixedWidth(60); edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        edit.setValidator(QIntValidator(min_v, max_v))
        edit.setStyleSheet("color: #00ff99; background: #000; border: 1px solid #00ff99; padding: 5px;")
        row.addStretch(); row.addWidget(edit); layout.addLayout(row); return edit

    def add_mod_btn(self, layout, txt, file, key):
        btn = QPushButton(txt); btn.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")
        btn.clicked.connect(lambda: self.toggle(key, file, btn)); layout.addWidget(btn)

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

    def toggle(self, key, file, btn):
        path = os.path.join(base_path, file)
        if self.processes[key] is None or self.processes[key].poll() is not None:
            self.processes[key] = subprocess.Popen([sys.executable, path], creationflags=subprocess.CREATE_NO_WINDOW)
            btn.setText(f"{key} STOPPEN")
            btn.setStyleSheet("border: 1px solid #ff4444; padding: 15px; font-weight: bold;")
        else:
            self.processes[key].terminate(); self.processes[key] = None
            btn.setText(f"{key} STARTEN")
            btn.setStyleSheet("border: 1px solid #00ff99; padding: 15px; font-weight: bold;")

if __name__ == "__main__":
    app = QApplication(sys.argv); w = GuardianSuite(); w.show(); sys.exit(app.exec())
