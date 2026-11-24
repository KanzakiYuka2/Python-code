#!/usr/bin/env python3
"""Rebuild an A-scan and B-scan from OmniPC 'Export All A-scans' TXT.

Usage:
  py -m pip install numpy matplotlib
  py omnipc_txt_to_images.py "20261117_AO1_Bscan1_2026_11_19 09h13m20s.txt"
  py omnipc_txt_to_images.py "file.txt" --index 28 --scan 14

This visualizes exported amplitude vs time. It does not reproduce the
OmniPC display exactly, calibrate ultrasonic depths, or replace the original.
"""
import argparse
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider

# Enter the name of a TXT file saved in the same folder as this script.
TXT_FILENAME = '20261117_AO1_Bscan1_2026_11_19 09h13m20s.txt'


def load_omnipc_export(path: Path):
    with path.open('r', encoding='utf-8-sig', errors='replace') as f:
        metadata = {}
        for _ in range(22):
            line = f.readline().strip()
            if ' = ' in line:
                key, value = line.split(' = ', 1)
                metadata[key] = value

        scan_n = int(metadata['Scan Qty.(sample)'])
        index_n = int(metadata['Index Qty. (sample)'])
        sound_n = int(metadata['USound Qty. (sample)'])
        time_ns = np.fromstring(f.readline().strip(), sep='\t')
        if len(time_ns) != sound_n:
            raise ValueError('Ultrasonic time-axis length does not match metadata.')
        amplitude = np.full((index_n, scan_n, sound_n), np.nan, dtype=np.float32)
        valid = np.zeros((index_n, scan_n), dtype=bool)

        # OmniPC export order: first all scan positions for Index 0,
        # then all scan positions for Index 1, etc.
        for idx in range(index_n):
            for scan in range(scan_n):
                line = f.readline()
                if not line:
                    raise ValueError(f'Export ends before index={idx}, scan={scan}.')
                # Unmeasured positions contain the placeholder ---.
                if line.lstrip().startswith('---'):
                    continue
                values = np.fromstring(line.strip(), sep='\t', dtype=np.float32)
                if len(values) != sound_n:
                    raise ValueError(
                        f'Bad sample count at index={idx}, scan={scan}: '
                        f'{len(values)} instead of {sound_n}'
                    )
                amplitude[idx, scan] = values
                valid[idx, scan] = True

    scan_positions = float(metadata['ScanStart (mm)']) + np.arange(scan_n) * float(metadata['Scan Resol. (mm)'])
    index_positions = float(metadata['IndexStart (mm)']) + np.arange(index_n) * float(metadata['Index Resol. (mm)'])
    time_us = time_ns / 1000.0
    return metadata, scan_positions, index_positions, time_us, amplitude, valid


def closest_index(array, value):
    return int(np.argmin(np.abs(array - value)))


def show_all_ascans(time_us, amplitude, valid, index_positions, scan_positions, i, s):
    """Browse every measurement position without drawing thousands of curves at once."""
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.subplots_adjust(bottom=0.28)
    line, = ax.plot(time_us, amplitude[i, s], linewidth=1.5)
    ax.set(xlabel='Ultrasonic time (microseconds)', ylabel='Amplitude (%)')
    ax.set_xlim(time_us[0], time_us[-1])
    ax.grid(alpha=0.22)
    index_slider = Slider(fig.add_axes([0.18, 0.13, 0.7, 0.03]), 'Index number',
                          0, max(len(index_positions) - 1, 1), valinit=i, valstep=1)
    scan_slider = Slider(fig.add_axes([0.18, 0.06, 0.7, 0.03]), 'Scan number',
                         0, max(len(scan_positions) - 1, 1), valinit=s, valstep=1)

    def update(_):
        idx = min(int(index_slider.val), len(index_positions) - 1)
        scan = min(int(scan_slider.val), len(scan_positions) - 1)
        line.set_ydata(amplitude[idx, scan])
        status = '' if valid[idx, scan] else ' (no recorded data)'
        ax.set_title(f'A-scan | Index {index_positions[idx]:g} mm, '
                     f'Scan {scan_positions[scan]:g} mm{status}')
        if valid[idx, scan]:
            ax.relim()
            ax.autoscale_view(scalex=False, scaley=True)
        fig.canvas.draw_idle()

    index_slider.on_changed(update)
    scan_slider.on_changed(update)
    update(None)
    plt.show()


def main():
    ap = argparse.ArgumentParser(description='Convert OmniPC exported A-scans into PNG plots.')
    ap.add_argument('txt', nargs='?', help='Path to exported TXT file (overrides TXT_FILENAME)')
    ap.add_argument('--index', type=float, default=None, help='Index coordinate in mm (default: middle available index)')
    ap.add_argument('--scan', type=float, default=None, help='Scan coordinate in mm (default: middle available scan)')
    ap.add_argument('--output', help='Output directory (default: folder containing TXT)')
    args = ap.parse_args()
    path = (Path(args.txt).expanduser().resolve() if args.txt
            else Path(__file__).resolve().parent / TXT_FILENAME)
    if not path.exists():
        ap.error(f'File not found: {path}')
    out_dir = Path(args.output).expanduser().resolve() if args.output else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata, scan_positions, index_positions, time_us, amp, valid = load_omnipc_export(path)
    if not valid.any():
        raise ValueError('No numeric A-scans were found (the export contains only ---).')

    i_available = np.flatnonzero(valid.any(axis=1))
    i = closest_index(index_positions, args.index) if args.index is not None else i_available[len(i_available)//2]
    if not valid[i].any():
        raise ValueError(f'No recorded scans at Index={index_positions[i]:g} mm.')
    s_available = np.flatnonzero(valid[i])
    s = closest_index(scan_positions, args.scan) if args.scan is not None else s_available[len(s_available)//2]
    if not valid[i, s]:
        raise ValueError(f'No recorded A-scan at Index={index_positions[i]:g}, Scan={scan_positions[s]:g} mm.')

    base = path.stem
    # A-scan: one measurement position, waveform over ultrasonic time.
    fig, ax = plt.subplots(figsize=(10, 4.6), layout='constrained')
    ax.plot(time_us, amp[i, s], linewidth=1.8)
    ax.set(xlabel='Ultrasonic time (microseconds)', ylabel='Amplitude (%)',
           title=f'A-scan | Index {index_positions[i]:g} mm, Scan {scan_positions[s]:g} mm')
    ax.set_xlim(time_us[0], time_us[-1])
    ax.grid(alpha=0.22)
    a_file = out_dir / f'{base}_A_scan.png'
    fig.savefig(a_file, dpi=170)
    plt.close(fig)

    # B-scan: many A-scans side-by-side along one scan direction.
    # Only show the range that actually contains scans; omitted positions stay missing.
    s_lo, s_hi = int(s_available.min()), int(s_available.max())
    b = np.ma.masked_invalid(amp[i, s_lo:s_hi+1].T)
    scan_res = float(metadata['Scan Resol. (mm)'])
    t_step = (time_us[1] - time_us[0]) if len(time_us) > 1 else 0.01
    fig, ax = plt.subplots(figsize=(10, 5.2), layout='constrained')
    im = ax.imshow(b, cmap='viridis', aspect='auto', interpolation='nearest',
        origin='upper', extent=[
            scan_positions[s_lo]-scan_res/2,
            scan_positions[s_hi]+scan_res/2,
            time_us[-1]+t_step/2,
            time_us[0]-t_step/2,
        ])
    ax.set(xlabel='Scan position (mm)', ylabel='Ultrasonic time (microseconds)',
           title=f'B-scan (from A-scan export) | Index {index_positions[i]:g} mm')
    fig.colorbar(im, ax=ax, label='Amplitude (%)')
    b_file = out_dir / f'{base}_B_scan.png'
    fig.savefig(b_file, dpi=170)
    plt.close(fig)

    print('Input:', path.name)
    print('Header:', metadata['Scan Qty.(sample)'], 'scan positions x', metadata['Index Qty. (sample)'], 'index positions x', metadata['USound Qty. (sample)'], 'time samples')
    print('Recorded A-scans:', int(valid.sum()), '/', valid.size)
    print('Selected: index=', index_positions[i], 'mm, scan=', scan_positions[s], 'mm')
    print('Saved:', a_file)
    print('Saved:', b_file)
    print('Note: depth conversion requires calibrated ultrasonic velocity and probe/wedge delays.')
    print('Use the sliders to browse all A-scans; close the window to finish.')
    show_all_ascans(time_us, amp, valid, index_positions, scan_positions, i, s)


if __name__ == '__main__':
    main()
