import serial.tools.list_ports

ports = serial.tools.list_ports.comports()

if not ports:
    print("COMポートが見つかりません。USB-RS232アダプタを確認してください。")
else:
    print("見つかったCOMポート:")
    for port in ports:
        print(f"{port.device} - {port.description}")
    