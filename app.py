
import sys
import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QComboBox, QTabWidget, QTextEdit, 
                             QProgressBar, QFrame, QMessageBox, QGroupBox)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QFont, QIcon
from pynput import keyboard
from datetime import datetime
import time
import traceback
import platform
import speech_recognition as sr

class SerialThread(QThread):
    """Handles non-blocking serial communication with Arduino."""
    data_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, port):
        super().__init__()
        self.ser = None
        self.port = port
        self.running = True
    
    def run(self):
        try:
            self.ser = serial.Serial(self.port, 9600, timeout=1, dsrdtr=False)
            self.data_received.emit("Connected to Arduino")
            while self.running:
                if self.ser.in_waiting > 0:
                    try:
                        data = self.ser.readline().decode('utf-8').strip()
                        if data:
                            self.data_received.emit(data)
                    except Exception as e:
                        self.error_occurred.emit(f"Serial read error: {str(e)}\nPlease check Arduino connection and restart the application.")
                self.msleep(50)
        except Exception as e:
            self.error_occurred.emit(f"Failed to open serial port {self.port}: {str(e)}\nPlease verify the port and restart the application.")
    
    def send(self, command):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(command.encode('utf-8'))
                return True
            except Exception as e:
                self.error_occurred.emit(f"Serial write error: {str(e)}\nPlease check Arduino connection and restart the application.")
                return False
        return False
    
    def close(self):
        self.running = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except:
                pass
        self.quit()
        self.wait()

class VoiceThread(QThread):
    """Voice recognition for rover control with status updates."""
    voice_detected = pyqtSignal(str)
    status_updated = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, serial_thread):
        super().__init__()
        self.serial_thread = serial_thread
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.running = True
    
    def run(self):
        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                while self.running:
                    try:
                        self.status_updated.emit("Listening...")
                        audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=3)
                        self.status_updated.emit("Processing...")
                        text = self.recognizer.recognize_google(audio).lower()
                        command_map = {
                            'forward': 'F', 'backward': 'B', 'back': 'B', 'left': 'L', 
                            'right': 'R', 'spray': 'P', 'stop': 'S'
                        }
                        cmd = None
                        for key, value in command_map.items():
                            if key in text:
                                cmd = value
                                break
                        if cmd:
                            if self.serial_thread.send(cmd):
                                self.status_updated.emit(f"Executing: {text} ({cmd})")
                                self.voice_detected.emit(f"[{datetime.now().strftime('%H:%M:%S')}] Voice: {text} ({cmd})")
                        else:
                            self.status_updated.emit("Listening...")
                            self.voice_detected.emit(f"[{datetime.now().strftime('%H:%M:%S')}] Unrecognized: {text}")
                    except sr.WaitTimeoutError:
                        self.status_updated.emit("Listening...")
                    except sr.UnknownValueError:
                        self.status_updated.emit("Listening...")
                        self.voice_detected.emit(f"[{datetime.now().strftime('%H:%M:%S')}] Could not understand audio")
                    except sr.RequestError as e:
                        self.error_occurred.emit(f"Voice recognition error: {str(e)}\nPlease check internet connection and restart.")
                        break
                    time.sleep(0.1)  # Reduce CPU usage
        except Exception as e:
            self.error_occurred.emit(f"Voice thread error: {str(e)}\nPlease restart the application.")
        
        self.cleanup()
    
    def cleanup(self):
        self.running = False
        self.quit()
        self.wait()

class AgnidevaControlCentre(QMainWindow):
    """Professional control center for Arjun P A Agnideva Rover."""
    
    def __init__(self):
        super().__init__()
        self.serial_thread = None
        self.voice_thread = None
        self.listener = None
        self.current_mode = 'N'
        self.last_cmd_time = 0
        self.active_keys = set()
        try:
            self.init_ui()
        except Exception as e:
            self.show_error(f"UI initialization failed: {str(e)}\nPlease restart the application.")
    
    def init_ui(self):
        self.setWindowTitle('Arjun P A Agnideva Control Centre')
        self.setGeometry(100, 100, 1000, 700)
        self.setStyleSheet("""
            QMainWindow { background-color: #121212; color: #ffffff; }
            QGroupBox { 
                background-color: #1e1e1e; 
                border: 1px solid #3a3a3a; 
                border-radius: 8px; 
                margin-top: 10px; 
                font-weight: bold;
            }
            QGroupBox::title { 
                color: #bbdefb; 
                subcontrol-origin: margin; 
                subcontrol-position: top left; 
                padding: 5px;
            }
            QPushButton { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #0288d1, stop:1 #0277bd);
                border: none; 
                padding: 12px 24px; 
                border-radius: 8px; 
                font-size: 14px; 
                font-weight: bold; 
                color: white;
            }
            QPushButton:hover { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #039be5, stop:1 #0288d1); 
            }
            QPushButton:pressed { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 #0277bd, stop:1 #01579b); 
            }
            QPushButton:disabled { background: #424242; }
            QLabel { font-size: 13px; color: #e0e0e0; }
            QComboBox { 
                background-color: #1e1e1e; 
                border: 1px solid #3a3a3a; 
                padding: 8px; 
                border-radius: 6px; 
                color: white; 
                font-size: 13px;
            }
            QComboBox::drop-down { border: none; }
            QTabWidget::pane { 
                border: 1px solid #3a3a3a; 
                background: #1e1e1e; 
                border-radius: 8px;
            }
            QTabWidget::tab-bar { alignment: center; }
            QTabWidget QTabBar::tab { 
                background: #2d2d2d; 
                padding: 12px 20px; 
                margin: 4px; 
                color: #bbdefb; 
                border-radius: 6px; 
                font-size: 13px;
            }
            QTabWidget QTabBar::tab:selected { 
                background: #0288d1; 
                color: white; 
            }
            QTextEdit { 
                background: #1a1a1a; 
                border: 1px solid #3a3a3a; 
                border-radius: 6px; 
                color: #00ff00; 
                font-family: 'Consolas'; 
                font-size: 12px; 
                padding: 8px;
            }
            QProgressBar { 
                border: 1px solid #3a3a3a; 
                border-radius: 6px; 
                background: #1a1a1a; 
                text-align: center; 
                color: white; 
                font-size: 12px;
            }
            QProgressBar::chunk { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #4CAF50, stop:1 #2e7d32); 
                border-radius: 4px;
            }
        """)
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel('🚀 Arjun P A Agnideva Control Centre')
        header.setFont(QFont('Segoe UI', 18, QFont.Bold))
        header.setStyleSheet("color: #bbdefb; padding: 10px; background: #1e1e1e; border-radius: 8px;")
        header.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header)
        
        # Connection Panel
        connect_group = QGroupBox("🔌 Connection")
        connect_layout = QHBoxLayout(connect_group)
        
        self.port_label = QLabel('Select Port:')
        connect_layout.addWidget(self.port_label)
        
        self.port_combo = QComboBox()
        self.refresh_ports()
        connect_layout.addWidget(self.port_combo)
        connect_layout.addStretch()
        
        self.connect_btn = QPushButton('Connect')
        self.connect_btn.setIcon(QIcon.fromTheme('network-connect'))
        self.connect_btn.clicked.connect(self.connect_serial)
        connect_layout.addWidget(self.connect_btn)
        
        self.disconnect_btn = QPushButton('Disconnect')
        self.disconnect_btn.setIcon(QIcon.fromTheme('network-disconnect'))
        self.disconnect_btn.clicked.connect(self.disconnect_serial)
        self.disconnect_btn.setEnabled(False)
        connect_layout.addWidget(self.disconnect_btn)
        
        main_layout.addWidget(connect_group)
        
        # Status Bar
        self.status_label = QLabel('Status: Ready to connect')
        self.status_label.setFont(QFont('Segoe UI', 12, QFont.Bold))
        self.status_label.setStyleSheet("padding: 10px; background: #1e1e1e; border-radius: 8px; color: #bbdefb;")
        main_layout.addWidget(self.status_label)
        
        # Dashboard
        self.dashboard = QTabWidget()
        self.setup_tabs()
        main_layout.addWidget(self.dashboard)
        
        # Status Panel
        status_group = QGroupBox("📊 Rover Status")
        status_layout = QHBoxLayout(status_group)
        
        soil_frame = QFrame()
        soil_layout = QVBoxLayout(soil_frame)
        soil_layout.addWidget(QLabel('🌱 Soil Moisture'))
        self.soil_bar = QProgressBar()
        self.soil_bar.setRange(0, 1023)
        self.soil_bar.setValue(0)
        self.soil_bar.setFormat('%v / 1023')
        self.soil_bar.setToolTip('Soil moisture level (0=dry, 1023=wet)')
        soil_layout.addWidget(self.soil_bar)
        status_layout.addWidget(soil_frame)
        
        dist_frame = QFrame()
        dist_layout = QVBoxLayout(dist_frame)
        dist_layout.addWidget(QLabel('📏 Distance'))
        self.dist_label = QLabel('-- cm')
        self.dist_label.setToolTip('Distance to nearest obstacle')
        dist_layout.addWidget(self.dist_label)
        status_layout.addWidget(dist_frame)
        
        mode_frame = QFrame()
        mode_layout = QVBoxLayout(mode_frame)
        mode_layout.addWidget(QLabel('⚙️ Mode'))
        self.mode_label = QLabel('Disconnected')
        self.mode_label.setStyleSheet("font-weight: bold; color: #0288d1; font-size: 14px;")
        mode_layout.addWidget(self.mode_label)
        status_layout.addWidget(mode_frame)
        
        status_layout.addStretch()
        main_layout.addWidget(status_group)
        
        # Log Window
        log_group = QGroupBox("📜 System Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(100)
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group)
        
        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        self.timer.start(1000)
        
        self.dashboard.hide()
    
    def setup_tabs(self):
        normal_tab = QWidget()
        normal_layout = QVBoxLayout(normal_tab)
        normal_layout.setSpacing(10)
        
        normal_info = QLabel('🎮 Normal Mode\nControl the rover using WASD keys or Space for pump')
        normal_info.setFont(QFont('Segoe UI', 12))
        normal_info.setStyleSheet("padding: 10px; background: #1e1e1e; border-radius: 6px;")
        normal_layout.addWidget(normal_info)
        
        self.normal_status = QTextEdit()
        self.normal_status.setReadOnly(True)
        self.normal_status.setMaximumHeight(120)
        normal_layout.addWidget(self.normal_status)
        
        self.dashboard.addTab(normal_tab, '🎮 Normal')
        
        voice_tab = QWidget()
        voice_layout = QVBoxLayout(voice_tab)
        voice_layout.setSpacing(10)
        
        voice_info = QLabel('🎙️ Voice Mode\nSay: Forward, Backward, Left, Right, Spray, Stop')
        voice_info.setFont(QFont('Segoe UI', 12))
        voice_info.setStyleSheet("padding: 10px; background: #1e1e1e; border-radius: 6px;")
        voice_layout.addWidget(voice_info)
        
        self.voice_status_label = QLabel('Status: Not active')
        self.voice_status_label.setStyleSheet("padding: 10px; background: #1e1e1e; border-radius: 6px; font-size: 13px;")
        voice_layout.addWidget(self.voice_status_label)
        
        self.voice_btn = QPushButton('🎙️ Start Voice Control')
        self.voice_btn.clicked.connect(self.toggle_voice)
        voice_layout.addWidget(self.voice_btn)
        
        self.voice_status = QTextEdit()
        self.voice_status.setReadOnly(True)
        self.voice_status.setMaximumHeight(120)
        voice_layout.addWidget(self.voice_status)
        
        voice_layout.addStretch()
        self.dashboard.addTab(voice_tab, '🎙️ Voice')
        
        auto_tab = QWidget()
        auto_layout = QVBoxLayout(auto_tab)
        auto_layout.setSpacing(10)
        
        auto_info = QLabel('🔥 Auto Mode\nAutonomous flame detection and extinguishing')
        auto_info.setFont(QFont('Segoe UI', 12))
        auto_info.setStyleSheet("padding: 10px; background: #1e1e1e; border-radius: 6px;")
        auto_layout.addWidget(auto_info)
        
        self.auto_btn = QPushButton('🚀 Activate Auto Mode')
        self.auto_btn.clicked.connect(lambda: self.switch_mode('A'))
        auto_layout.addWidget(self.auto_btn)
        
        self.auto_status = QLabel('Ready to scan for flames...')
        self.auto_status.setStyleSheet("padding: 10px; font-size: 13px;")
        auto_layout.addWidget(self.auto_status)
        
        auto_layout.addStretch()
        self.dashboard.addTab(auto_tab, '🔥 Auto')
    
    def show_error(self, message):
        """Display error message and prompt restart."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_text.append(f"[{timestamp}] ERROR: {message}")
        QMessageBox.critical(self, "Error", f"{message}")
        self.disconnect_serial()
    
    def refresh_ports(self):
        try:
            self.port_combo.clear()
            system = platform.system().lower()
            ports = []
            for p in serial.tools.list_ports.comports():
                device = p.device.lower()
                if ('arduino' in p.description.lower() or
                    (system == 'windows' and 'com' in device) or
                    (system in ('linux', 'darwin') and ('tty' in device or 'cu' in device))):
                    ports.append(p.device)
            if not ports:
                ports = [p.device for p in serial.tools.list_ports.comports()]
            self.port_combo.addItems(ports or ['No ports found'])
        except Exception as e:
            self.show_error(f"Failed to list ports: {str(e)}\nPlease restart the application.")
    
    def connect_serial(self):
        try:
            if self.serial_thread and self.serial_thread.isRunning():
                self.show_error("Already connected to a port!\nPlease disconnect first or restart the application.")
                return
            port = self.port_combo.currentText()
            if not port or 'No ports' in port:
                self.show_error("No valid port selected.\nPlease select a port and restart the application.")
                return
            self.status_label.setText("Status: Connecting...")
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.log_text.append(f"[{timestamp}] Connecting to {port}")
            self.serial_thread = SerialThread(port)
            self.serial_thread.data_received.connect(self.handle_serial_data)
            self.serial_thread.error_occurred.connect(self.show_error)
            self.serial_thread.start()
            QTimer.singleShot(2000, self.check_connection_status)
        except Exception as e:
            self.show_error(f"Connection failed: {str(e)}\nPlease restart the application.")
    
    def check_connection_status(self):
        try:
            if self.serial_thread and self.serial_thread.isRunning() and "Connected" in self.status_label.text():
                timestamp = datetime.now().strftime('%H:%M:%S')
                self.log_text.append(f"[{timestamp}] Connected to {self.port_combo.currentText()}")
                self.connect_btn.setEnabled(False)
                self.disconnect_btn.setEnabled(True)
                self.dashboard.show()
                self.switch_mode('N')
                self.start_key_listener()
            else:
                self.show_error("Connection failed.\nPlease check Arduino connection and restart the application.")
        except Exception as e:
            self.show_error(f"Connection check failed: {str(e)}\nPlease restart the application.")
    
    def disconnect_serial(self):
        try:
            if self.serial_thread:
                self.serial_thread.close()
                self.serial_thread = None
            if self.voice_thread:
                self.voice_thread.cleanup()
                self.voice_thread = None
                self.voice_btn.setText('🎙️ Start Voice Control')
                self.voice_status_label.setText('Status: Not active')
            if self.listener:
                self.listener.stop()
                self.listener = None
            self.status_label.setText("Status: Disconnected")
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.log_text.append(f"[{timestamp}] Disconnected")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.dashboard.hide()
            self.mode_label.setText('None')
            self.refresh_ports()
        except Exception as e:
            self.show_error(f"Disconnect failed: {str(e)}\nPlease restart the application.")
    
    def handle_serial_data(self, data):
        try:
            timestamp = datetime.now().strftime('%H:%M:%S')
            if 'Error' in data:
                self.show_error(data)
                return
            if 'Mode:' in data:
                mode = data.split(':')[1].strip()
                self.current_mode = mode
                self.mode_label.setText(mode)
                self.auto_status.setText(f'Auto Mode: {"Active" if mode == "A" else "Inactive"}')
                self.log_text.append(f"[{timestamp}] Mode set to {mode}")
            elif data.startswith('Soil:'):
                try:
                    soil = int(data.split(':')[1])
                    self.soil_bar.setValue(soil)
                    moisture_percent = int((1023 - soil) / 1023 * 100)
                    self.soil_bar.setToolTip(f"{moisture_percent}% moisture")
                    self.log_text.append(f"[{timestamp}] Soil Moisture: {soil} ({moisture_percent}%)")
                except:
                    self.log_text.append(f"[{timestamp}] Invalid soil data")
            elif data.startswith('Dist:'):
                try:
                    dist = data.split(':')[1].strip()
                    self.dist_label.setText(f"{dist} cm")
                except:
                    pass
            elif data == "Connected to Arduino":
                self.status_label.setText("Status: ✅ Connected")
                self.log_text.append(f"[{timestamp}] {data}")
            else:
                self.log_text.append(f"[{timestamp}] Received: {data}")
        except Exception as e:
            self.show_error(f"Serial data processing failed: {str(e)}\nPlease restart the application.")
    
    def switch_mode(self, mode):
        try:
            if self.serial_thread and self.serial_thread.send(mode):
                self.current_mode = mode
                self.mode_label.setText(mode)
                timestamp = datetime.now().strftime('%H:%M:%S')
                if mode == 'V' and not self.voice_thread:
                    self.voice_status.append(f"[{timestamp}] Voice mode activated")
                elif mode == 'A':
                    self.auto_status.setText('🔥 Scanning for flames...')
                    self.normal_status.append(f"[{timestamp}] Auto Mode activated")
                elif mode == 'N':
                    self.normal_status.append(f"[{timestamp}] Normal Mode activated")
                    if self.voice_thread:
                        self.toggle_voice()
        except Exception as e:
            self.show_error(f"Mode switch failed: {str(e)}\nPlease restart the application.")
    
    def toggle_voice(self):
        try:
            if self.voice_thread and self.voice_thread.isRunning():
                self.voice_thread.cleanup()
                self.voice_thread = None
                self.voice_btn.setText('🎙️ Start Voice Control')
                self.voice_status_label.setText('Status: Not active')
                self.switch_mode('N')
                timestamp = datetime.now().strftime('%H:%M:%S')
                self.voice_status.append(f"[{timestamp}] Voice control stopped")
            else:
                if self.serial_thread.send('V'):
                    self.voice_thread = VoiceThread(self.serial_thread)
                    self.voice_thread.voice_detected.connect(
                        lambda msg: self.voice_status.append(msg)
                    )
                    self.voice_thread.status_updated.connect(
                        lambda msg: self.voice_status_label.setText(f"Status: {msg}")
                    )
                    self.voice_thread.error_occurred.connect(self.show_error)
                    self.voice_thread.start()
                    self.voice_btn.setText('⏹️ Stop Voice Control')
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    self.voice_status.append(f"[{timestamp}] Voice control started")
        except Exception as e:
            self.show_error(f"Voice mode toggle failed: {str(e)}\nPlease restart the application.")
    
    def start_key_listener(self):
        try:
            def on_press(key):
                if self.current_mode != 'N' or not self.serial_thread:
                    return True
                try:
                    cmd = ''
                    if key == keyboard.Key.up or (hasattr(key, 'char') and key.char.lower() == 'w'): cmd = 'F'
                    elif key == keyboard.Key.down or (hasattr(key, 'char') and key.char.lower() == 's'): cmd = 'B'
                    elif key == keyboard.Key.left or (hasattr(key, 'char') and key.char.lower() == 'a'): cmd = 'L'
                    elif key == keyboard.Key.right or (hasattr(key, 'char') and key.char.lower() == 'd'): cmd = 'R'
                    elif key == keyboard.Key.space: cmd = 'P'
                    if cmd:
                        self.active_keys.add(cmd)
                        self.send_key_command()
                except:
                    pass
                return True
            
            def on_release(key):
                if self.current_mode != 'N' or not self.serial_thread:
                    return True
                try:
                    cmd = ''
                    if key == keyboard.Key.up or (hasattr(key, 'char') and key.char.lower() == 'w'): cmd = 'F'
                    elif key == keyboard.Key.down or (hasattr(key, 'char') and key.char.lower() == 's'): cmd = 'B'
                    elif key == keyboard.Key.left or (hasattr(key, 'char') and key.char.lower() == 'a'): cmd = 'L'
                    elif key == keyboard.Key.right or (hasattr(key, 'char') and key.char.lower() == 'd'): cmd = 'R'
                    elif key == keyboard.Key.space: cmd = 'P'
                    if cmd in self.active_keys:
                        self.active_keys.remove(cmd)
                        self.send_key_command()
                except:
                    pass
                return True
            
            self.listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self.listener.start()
        except Exception as e:
            self.show_error(f"Keyboard listener failed: {str(e)}\nPlease restart the application.")
    
    def send_key_command(self):
        priority_cmds = ['F', 'B', 'L', 'R', 'P']
        cmd = 'S'
        for p_cmd in priority_cmds:
            if p_cmd in self.active_keys:
                cmd = p_cmd
                break
        if self.serial_thread.send(cmd):
            timestamp = datetime.now().strftime('%H:%M:%S')
            self.normal_status.append(f"[{timestamp}] WASD: {cmd}")
    
    def update_status(self):
        try:
            if not self.serial_thread:
                self.dist_label.setText('-- cm')
                return
            if self.current_mode in ['A', 'N', 'V']:
                self.serial_thread.send('D')  # Request distance update
            if time.time() - self.last_cmd_time > 5:
                self.serial_thread.send('S')
                self.last_cmd_time = time.time()
        except Exception as e:
            self.show_error(f"Status update failed: {str(e)}\nPlease restart the application.")
    
    def closeEvent(self, event):
        try:
            self.disconnect_serial()
            event.accept()
        except Exception as e:
            self.show_error(f"Application close failed: {str(e)}\nPlease force quit and restart.")
            event.accept()

if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        app.setFont(QFont('Segoe UI', 10))
        window = AgnidevaControlCentre()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        QMessageBox.critical(None, "Fatal Error", f"Application failed to start: {str(e)}\nPlease restart the application.")
        print(f"Fatal error: {str(e)}")
        print(traceback.format_exc())
