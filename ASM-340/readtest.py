import serial
import time

SERIAL_PORT = "COM3"  # ここを自分のCOM番号に変更

try:
    ser = serial.Serial(
        port=SERIAL_PORT,
        baudrate=9600,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )

    print(f"{SERIAL_PORT} に接続しました。ASM340からのデータを待っています...")
    print("終了するには Ctrl + C を押してください。")

    while True:
        line = ser.readline().decode("ascii", errors="ignore").strip()

        if line:
            print(line)
        else:
            print("データ待ち...")
            time.sleep(1)

except serial.SerialException as e:
    print("シリアル接続エラー:")
    print(e)
    print("COM番号、USB-RS232アダプタ、Tera Termが開いたままになっていないか確認してください。")

except KeyboardInterrupt:
    print("\n停止しました。")

finally:
    try:
        ser.close()
        print("シリアルポートを閉じました。")
    except:
        pass