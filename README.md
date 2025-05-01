# NitroSensual `1.0`

**NitroSensual** is a Windows fan control and monitoring app for Acer Nitro laptops and similar systems, might even work for Predator series. It provides bloatless GUI for controlling CPU and GPU fan speeds, and displays real-time temperature readings using LibreHardwareMonitor.

## Features

- Control CPU and GPU fan speeds (requires NitroSense in Custom mode)
- View real-time CPU and GPU temperatures
- Automatic admin privilege elevation for registry access
- No manual setup for hardware monitoring: the required `LibreHardwareMonitorLib.dll` is automatically downloaded and resolved on first run
- Clean PyQt5 interface

## How It Works

- **Fan control**: NitroSensual writes to the NitroSense registry keys and communicates with the PredatorSense service to set fan speeds.

- **Temperature monitoring**: Uses [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) via its DLL to read CPU and GPU temperatures. The DLL is automatically downloaded and extracted if not present.

## Installation

A ready-to-use Windows binary is available in the [Releases](https://github.com/KRWCLASSIC/NitroSensual/releases) tab.

## Usage

Double click and use GUI to control your fans!

> CLI Support will be added in the near future!

## Notes

- **LibreHardwareMonitorLib.dll** is used for temperature monitoring. The app will automatically download and extract it if missing.

- You must enable "Custom" mode in NitroSense for fan control to work.
