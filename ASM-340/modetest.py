import serial
import time

SERIAL_PORT = "COM3"

ser = serial.Serial(
    port=SERIAL_PORT,
    baudrate=9600,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    timeout=2,
    xonxoff=False,
    rtscts=False,
    dsrdtr=False,
)

def send_command(cmd):
    ser.reset_input_buffer()
    ser.write((cmd + "\r").encode("ascii"))
    ser.flush()
    time.sleep(0.2)
    data = ser.read(100)
    return data.decode("ascii", errors="ignore")

try:
    print("Sending ?RDY ...")
    print("Response:", repr(send_command("?RDY")))

    print("Sending ?MD ...")
    print("Response:", repr(send_command("?MD")))

    print("Sending ?UN ...")
    print("Response:", repr(send_command("?UN")))

finally:
    ser.close()