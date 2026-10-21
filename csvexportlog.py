import serial
import time
import re
import csv
import os
from pathlib import Path
from datetime import datetime
from collections import deque

import matplotlib.pyplot as plt


# ============================================================
# User settings
# ここを主に変更する
# ============================================================

# 使用するCOMポート
# Tera Termやデバイスマネージャーで確認したCOM番号に合わせる
SERIAL_PORT = "COM3"

# ASM340のRS232C通信設定
# マニュアル設定：9600 / 8bit / parity none / stop bit 1
BAUDRATE = 9600

# CSV保存フォルダ
# このPythonファイルと同じ場所に asm340_logs フォルダが作られる
LOG_DIR = Path("asm340_logs")

# グラフに表示する最大点数
# ASM340が約1秒に1点出力する場合：
# 1800  → 約30分
# 3600  → 約1時間
# 7200  → 約2時間
# 21600 → 約6時間
# CSVにはMAX_POINTSを超えても全部保存される
MAX_POINTS = 7200

# グラフ更新頻度
# 10なら、10個の有効データごとにグラフ更新
# 長時間測定では毎回更新しない方が安定
PLOT_UPDATE_INTERVAL = 5

# CSV flush頻度
# 10なら、10行ごとにCSVファイルへ書き込みを反映
CSV_FLUSH_INTERVAL = 5

# ターミナル表示頻度
# 10なら、10行ごとに現在値を表示
CONSOLE_PRINT_INTERVAL = 5

# serialの読み取り待ち時間
# データが来ないとき、1秒でタイムアウト
SERIAL_TIMEOUT = 1

# 縦軸を固定するか
# TrueならY_MIN〜Y_MAXで固定
FIX_Y_LIMIT = True

# グラフの縦軸範囲
# log scaleなので0以下は不可
Y_MIN = 1e-11
Y_MAX = 1e-5


# ============================================================
# Regex patterns
# ASM340 Spreadsheet mode の文字列から値を取り出すための設定
# ============================================================

# ASM340 Spreadsheet mode の出力例：
# HS TEST ON S=9.00E-07 P=4.40E+02 15:38:51 PASS
#
# S=... がリークレート
# P=... が入口圧力
# 15:38:51 がASM340側の時刻
# PASS / FAIL が判定結果

leak_pattern = re.compile(
    r"S\s*=\s*([+-]?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)"
)

pressure_pattern = re.compile(
    r"P\s*=\s*([+-]?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)"
)

time_pattern = re.compile(
    r"\b(\d{2}:\d{2}:\d{2})\b"
)


# ============================================================
# ASM340の1行データを解析する関数
# ============================================================

def parse_asm340_line(line: str):
    """
    ASM340 Spreadsheet mode の1行から必要な値を取り出す。

    Parameters
    ----------
    line : str
        ASM340から受信した1行の文字列

    Returns
    -------
    leak_rate : float or None
        リークレート。単位はASM340側の設定に依存するが、
        通常は mbar L/s として扱う。
    pressure : float or None
        入口圧力。通常は mbar。
    asm_time : str
        ASM340側の表示時刻。例 "15:38:51"
    result : str
        "PASS", "FAIL", または空文字
    """

    leak_match = leak_pattern.search(line)
    pressure_match = pressure_pattern.search(line)
    time_match = time_pattern.search(line)

    leak_rate = float(leak_match.group(1)) if leak_match else None
    pressure = float(pressure_match.group(1)) if pressure_match else None
    asm_time = time_match.group(1) if time_match else ""

    if "PASS" in line:
        result = "PASS"
    elif "FAIL" in line:
        result = "FAIL"
    else:
        result = ""

    return leak_rate, pressure, asm_time, result


# ============================================================
# CSVファイルを開く関数
# ============================================================

def open_single_csv():
    """
    実行開始時に1つだけCSVファイルを作成する。

    日付が変わってもCSVを分割しない。
    つまり、24時間以上測定しても同じCSVに保存される。

    ファイル名例：
    asm340_logs/asm340_log_20260614_153000.csv
    """

    # 保存フォルダがなければ作成
    LOG_DIR.mkdir(exist_ok=True)

    # 測定開始時刻をファイル名に入れる
    start_datetime = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = LOG_DIR / f"asm340_log_{start_datetime}.csv"

    # 新規作成
    csv_file = open(filename, mode="w", newline="", encoding="utf-8")
    writer = csv.writer(csv_file)

    # CSVヘッダー
    writer.writerow([
        "pc_datetime",          # PC側の日時
        "elapsed_s",            # 測定開始からの経過時間 [s]
        "asm_time",             # ASM340側の時刻
        "leak_rate_mbar_l_s",   # リークレート
        "inlet_pressure_mbar",  # 入口圧力
        "result",               # PASS / FAIL
        "raw_line"              # ASM340から来た元データ
    ])

    # ヘッダーをすぐ保存
    csv_file.flush()

    return csv_file, writer, filename


# ============================================================
# グラフを準備する関数
# ============================================================

def setup_plot():
    """
    リアルタイムグラフの初期設定。

    今回は長時間測定を想定しているため、
    markerは付けず、線だけにして軽くしている。
    """

    # interactive mode ON
    plt.ion()

    fig, ax = plt.subplots()

    # markerを付けると長時間で重くなりやすいので線だけ
    leak_plot, = ax.plot([], [])

    ax.set_title("ASM340 Real-time Leak Rate")
    ax.set_xlabel("Elapsed time [s]")
    ax.set_ylabel("Leak rate [Pa m^3/s]")

    # 縦軸をログスケールに固定
    ax.set_yscale("log")

    # 縦軸範囲を固定
    if FIX_Y_LIMIT:
        ax.set_ylim(Y_MIN, Y_MAX)

    ax.grid(True, which="both")

    return fig, ax, leak_plot


# ============================================================
# メイン処理
# ============================================================

def main():
    ser = None
    csv_file = None

    try:
        # ------------------------------------------------------------
        # Serial portを開く
        # ------------------------------------------------------------
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=SERIAL_TIMEOUT,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

        print(f"{SERIAL_PORT} に接続しました。")
        print("ASM340 Spreadsheet mode のデータを記録します。")
        print("日付が変わっても、同じCSVファイルに保存し続けます。")
        print("終了するには Ctrl + C を押してください。")
        print()

        # ------------------------------------------------------------
        # CSVファイル作成
        # ------------------------------------------------------------
        csv_file, writer, csv_filename = open_single_csv()
        print(f"CSV保存先: {csv_filename}")
        print()

        # ------------------------------------------------------------
        # グラフ用データ保存領域
        # dequeを使うことで、古いデータは自動で消える
        # CSVには全データを保存するが、グラフ表示はMAX_POINTSぶんだけ
        # ------------------------------------------------------------
        times = deque(maxlen=MAX_POINTS)
        leak_rates = deque(maxlen=MAX_POINTS)

        # ------------------------------------------------------------
        # グラフ初期化
        # ------------------------------------------------------------
        fig, ax, leak_plot = setup_plot()

        # ------------------------------------------------------------
        # カウンタ類
        # ------------------------------------------------------------
        start_time = time.time()
        data_count = 0
        valid_plot_count = 0
        wait_count = 0

        # ------------------------------------------------------------
        # メインループ
        # ------------------------------------------------------------
        while True:
            # ASM340から1行読み取る
            raw_bytes = ser.readline()

            # データが来ない場合
            if not raw_bytes:
                wait_count += 1

                # 毎秒表示すると邪魔なので、30回に1回だけ表示
                if wait_count % 30 == 0:
                    print("データ待ち...")

                continue

            # データが来たら待ちカウントをリセット
            wait_count = 0

            # bytes → string
            raw_line = raw_bytes.decode("ascii", errors="ignore").strip()

            # 空行ならスキップ
            if not raw_line:
                continue

            # 現在時刻と経過時間
            now = datetime.now()
            elapsed_time = time.time() - start_time

            # ASM340の文字列から値を取り出す
            leak_rate, pressure, asm_time, result = parse_asm340_line(raw_line)

            data_count += 1

            # --------------------------------------------------------
            # CSVに保存
            # leak_rateがNoneでもraw_lineは保存する
            # これにより、解析失敗行も後で確認できる
            # --------------------------------------------------------
            writer.writerow([
                now.isoformat(timespec="seconds"),
                f"{elapsed_time:.3f}",
                asm_time,
                leak_rate,
                pressure,
                result,
                raw_line
            ])

            # 定期的にCSVをflush
            if data_count % CSV_FLUSH_INTERVAL == 0:
                csv_file.flush()

            # さらに定期的にディスクへ確実に書き込む
            # 長時間測定中にPCが落ちた場合のデータ損失を減らす
            if data_count % 60 == 0:
                os.fsync(csv_file.fileno())

            # --------------------------------------------------------
            # ターミナル表示
            # 毎行表示すると長時間測定で重くなるので間引く
            # --------------------------------------------------------
            if data_count % CONSOLE_PRINT_INTERVAL == 0:
                print(
                    f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"leak={leak_rate}, pressure={pressure}, result={result}"
                )

            # --------------------------------------------------------
            # グラフ更新
            # log scaleでは0以下を表示できないため、
            # leak_rateが正の値のときだけグラフに入れる
            # --------------------------------------------------------
            if leak_rate is not None and leak_rate > 0:
                times.append(elapsed_time)
                leak_rates.append(leak_rate)
                valid_plot_count += 1

                # グラフ更新は毎回ではなく、一定回数ごとに行う
                if valid_plot_count % PLOT_UPDATE_INTERVAL == 0:

                    # グラフウィンドウが閉じられていない場合のみ更新
                    # 閉じられてもCSV記録は続く
                    if plt.fignum_exists(fig.number):
                        leak_plot.set_data(list(times), list(leak_rates))

                        # 念のため毎回ログスケールに戻す
                        ax.set_yscale("log")

                        # 縦軸範囲を固定
                        if FIX_Y_LIMIT:
                            ax.set_ylim(Y_MIN, Y_MAX)

                        # データ範囲を再計算
                        ax.relim()

                        # X軸だけ自動調整
                        # Y軸は固定しているので scaley=False
                        ax.autoscale_view(
                            scalex=True,
                            scaley=not FIX_Y_LIMIT
                        )

                        # グラフ描画更新
                        plt.pause(0.01)

    # ------------------------------------------------------------
    # Serial port関連エラー
    # ------------------------------------------------------------
    except serial.SerialException as e:
        print("シリアル接続エラー:")
        print(e)
        print("COM番号、USB-RS232アダプタ、Tera Termが開いたままになっていないか確認してください。")

    # ------------------------------------------------------------
    # Ctrl + C で停止した場合
    # ------------------------------------------------------------
    except KeyboardInterrupt:
        print("\n停止しました。")

    # ------------------------------------------------------------
    # 終了処理
    # Ctrl + Cでもエラーでも、できるだけCSVとCOMポートを閉じる
    # ------------------------------------------------------------
    finally:
        # CSVを閉じる
        try:
            if csv_file is not None:
                csv_file.flush()
                os.fsync(csv_file.fileno())
                csv_file.close()
                print("CSVを保存しました。")
        except Exception as e:
            print("CSV終了処理中にエラー:")
            print(e)

        # Serial portを閉じる
        try:
            if ser is not None and ser.is_open:
                ser.close()
                print("シリアルポートを閉じました。")
        except Exception as e:
            print("シリアルポート終了処理中にエラー:")
            print(e)


# ============================================================
# Pythonファイルとして直接実行されたときだけ main() を実行
# ============================================================

if __name__ == "__main__":
    main()