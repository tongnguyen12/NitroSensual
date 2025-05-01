from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QSlider, QPushButton, QMessageBox, QGroupBox, QDialog
)
from PyQt5.QtCore import Qt, QTimer
from elevate import elevate
import urllib.request
import win32file
import tempfile
import zipfile
import winreg
import struct
import clr
import sys
import os

elevate()

# Helper to read current fan percentage from registry
def read_fan_percentage(fan_type: str) -> int:
    key_path = r"SOFTWARE\\OEM\\NitroSense\\FanControl"
    value_name = "CPUFanPercentage" if fan_type == "cpu" else "GPU1FanPercentage"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
            return int(value)
    except Exception:
        return -1  # Could not read

# Helper to write fan percentage to registry
def write_registry(fan_type: str, percent: int):
    key_path = r"SOFTWARE\\OEM\\NitroSense\\FanControl"
    value_name = "CPUFanPercentage" if fan_type == "cpu" else "GPU1FanPercentage"
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as key:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, percent)

# Helper to apply fan speed via named pipe
def apply_fan_speed(fan_type: str, percent: int):
    fan_group_type = 1 if fan_type == "cpu" else 4
    data = (percent << 8) | fan_group_type
    packet = struct.pack("<HBIQ", 16, 1, 8, data)
    try:
        handle = win32file.CreateFile(
            r"\\.\pipe\PredatorSense_service_namedpipe",
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0,
            None,
            win32file.OPEN_EXISTING,
            0,
            None
        )
        win32file.WriteFile(handle, packet)
        resp = win32file.ReadFile(handle, 9)[1]
        win32file.CloseHandle(handle)
        return True, resp.hex()
    except Exception as e:
        return False, str(e)

def unblock_file_if_needed(filepath):
    # Unblock file if it has a zone identifier (Windows only)
    if os.name == 'nt' and os.path.exists(filepath):
        ads = filepath + ":Zone.Identifier"
        if os.path.exists(ads):
            try:
                os.remove(ads)
            except Exception as e:
                print(f"Could not remove Zone.Identifier: {e}")

class ProgressDialog(QDialog):
    def __init__(self, message):
        super().__init__()
        self.setWindowTitle("Please Wait")
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        layout = QVBoxLayout()
        label = QLabel(message)
        layout.addWidget(label)
        self.setLayout(layout)
        self.setFixedSize(350, 80)

def ensure_lhm_dll(show_progress=False):
    dll_name = "LibreHardwareMonitorLib.dll"
    dll_path = os.path.abspath(dll_name)
    progress = None
    app = QApplication.instance()
    if not os.path.exists(dll_path):
        print("LibreHardwareMonitorLib.dll not found, downloading...")
        if show_progress and app is not None:
            progress = ProgressDialog("Resolving LibreHardwareMonitorLib.dll, please wait...")
            progress.show()
            app.processEvents()
        url = "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.4/LibreHardwareMonitor-net472.zip"
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "lhm.zip")
            print(f"Downloading {url} ...")
            urllib.request.urlretrieve(url, zip_path)
            print("Download complete. Extracting DLL...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    if member.endswith(dll_name):
                        zip_ref.extract(member, tmpdir)
                        src = os.path.join(tmpdir, member)
                        # Copy DLL to current directory
                        with open(src, 'rb') as fsrc, open(dll_path, 'wb') as fdst:
                            fdst.write(fsrc.read())
                        print(f"Extracted {dll_name} to current directory.")
                        break
        if progress:
            progress.close()
    return dll_path

def get_lhm_temps():
    try:
        dll_path = ensure_lhm_dll(show_progress=True)
        unblock_file_if_needed(dll_path)
        clr.AddReference(dll_path)
        from LibreHardwareMonitor import Hardware  # type: ignore

        computer = Hardware.Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = True
        computer.Open()

        cpu_temp = None
        gpu_temp = None

        for hardware in computer.Hardware:
            hardware.Update()
            if hardware.HardwareType == Hardware.HardwareType.Cpu:
                for sensor in hardware.Sensors:
                    if sensor.SensorType == Hardware.SensorType.Temperature and "package" in sensor.Name.lower():
                        cpu_temp = sensor.Value
            if hardware.HardwareType == Hardware.HardwareType.GpuNvidia or hardware.HardwareType == Hardware.HardwareType.GpuAmd:
                for sensor in hardware.Sensors:
                    if sensor.SensorType == Hardware.SensorType.Temperature and "core" in sensor.Name.lower():
                        gpu_temp = sensor.Value

        computer.Close()
        return cpu_temp, gpu_temp
    except Exception as e:
        print(e)
        return None, None

class FanControlWidget(QWidget):
    def __init__(self, fan_type: str, refresh_callback=None):
        super().__init__()
        self.fan_type = fan_type
        self.refresh_callback = refresh_callback
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout()
        self.label = QLabel(f"{self.fan_type.upper()} Fan Speed:")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(read_fan_percentage(self.fan_type))
        self.value_label = QLabel(f"{self.slider.value()}%")
        self.slider.valueChanged.connect(lambda v: self.value_label.setText(f"{v}%"))
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_fan_speed)
        layout.addWidget(self.label)
        layout.addWidget(self.slider)
        layout.addWidget(self.value_label)
        layout.addWidget(self.apply_btn)
        self.setLayout(layout)

    def apply_fan_speed(self):
        percent = self.slider.value()
        try:
            write_registry(self.fan_type, percent)
            ok, msg = apply_fan_speed(self.fan_type, percent)
            if ok:
                QMessageBox.information(self, "Fan Set", f"Set {self.fan_type.upper()} fan to {percent}% (applied)")
            else:
                QMessageBox.warning(self, "Fan Error", f"Failed to apply: {msg}")
            if self.refresh_callback:
                self.refresh_callback()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to set fan: {e}")

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("NitroSensual")
        self.layout = QVBoxLayout()

        self.cpu_temp_label = QLabel()
        self.gpu_temp_label = QLabel()
        self.cpu_speed_label = QLabel()
        self.gpu_speed_label = QLabel()
        self.layout.addWidget(self.cpu_temp_label)
        self.layout.addWidget(self.gpu_temp_label)
        self.layout.addWidget(self.cpu_speed_label)
        self.layout.addWidget(self.gpu_speed_label)

        notice = QLabel(
            '<b>Notice:</b> Please enable <span style="color:red">"Custom"</span> mode in NitroSense for fan control to work!'
        )
        notice.setWordWrap(True)
        self.layout.addWidget(notice)

        cpu_group = QGroupBox("CPU Fan")
        cpu_layout = QVBoxLayout()
        cpu_layout.addWidget(FanControlWidget("cpu", refresh_callback=self.refresh_speeds))
        cpu_group.setLayout(cpu_layout)
        self.layout.addWidget(cpu_group)

        gpu_group = QGroupBox("GPU Fan")
        gpu_layout = QVBoxLayout()
        gpu_layout.addWidget(FanControlWidget("gpu", refresh_callback=self.refresh_speeds))
        gpu_group.setLayout(gpu_layout)
        self.layout.addWidget(gpu_group)

        self.setLayout(self.layout)
        self.resize(400, 200)

        # Timer for refreshing current speeds and temperature
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_speeds)
        self.timer.start(1000)
        self.refresh_speeds()

    def refresh_speeds(self):
        cpu_percent = read_fan_percentage("cpu")
        gpu_percent = read_fan_percentage("gpu")
        cpu_temp, gpu_temp = get_lhm_temps()
        cpu_temp_text = f"CPU Temp: {cpu_temp:.1f}°C" if cpu_temp is not None else "CPU Temp: ?"
        gpu_temp_text = f"GPU Temp: {gpu_temp:.1f}°C" if gpu_temp is not None else "GPU Temp: ?"
        cpu_text = f"CPU Fan Current Speed: {cpu_percent if cpu_percent >= 0 else '?'}%"
        gpu_text = f"GPU Fan Current Speed: {gpu_percent if gpu_percent >= 0 else '?'}%"
        self.cpu_temp_label.setText(cpu_temp_text)
        self.gpu_temp_label.setText(gpu_temp_text)
        self.cpu_speed_label.setText(cpu_text)
        self.gpu_speed_label.setText(gpu_text)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
