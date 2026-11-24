# -*- coding: utf-8 -*-
"""Abaqus/CAE XY Report (*.rpt) -> effective He permeability and diffusivity.

Run in ordinary Python 3 (VS Code / PowerShell), NOT Abaqus Python 2.7.

Abaqus: Visualization -> Report -> XY -> export a downstream RFL11 time
history curve. Prefer the SIGNED SUM of all downstream nodes in ONE instance.
This script also accepts multiple RFL11 node curves in ONE aligned table and
sums them before taking the absolute value.

The parameters below model the *centered square unit cell* as a 2D cross
section with one whole central fiber and four quarter corner fibers.
Do NOT reuse the geometry automatically for a different Part.
"""

from __future__ import print_function

import argparse
import csv
import math
import re
import statistics
from pathlib import Path

# ===========================================================================
# USER SETTINGS -- edit here, or override values using command line options
# ===========================================================================
RPT_PATH = str(Path(__file__).resolve().parent / 'Unit Cell Analysis' / 'UnitCell_analysis1.rpt')

# Centered square array: 1 whole center fiber + 4 quarter fibers = 2 fibers
FIBER_RADIUS_MM = 0.0035
NUMBER_EQUIVALENT_FIBERS = 2.0
VF = 0.50

# If the Actual Part dimensions differ, set both of these manually.
# None = infer square cell from Vf, radius, and equivalent fiber count.
CELL_HEIGHT_MM = None         # diffusion direction, y
CELL_WIDTH_MM = None          # x direction, perpendicular to diffusion
OUT_OF_PLANE_DEPTH_MM = 1.0  # IMPORTANT: verify section thickness in model

# Current PEEK 1-mm specimen-derived inputs (Abaqus mm-kg-s)
D_MATRIX_MM2_S = 1.1109e-4
S_MATRIX_KG_MM3 = 1.920522e-12

# Current *finite-storage* carbon-fiber model inputs
D_FIBER_MM2_S = 1.0e-12
S_FIBER_KG_MM3 = 1.0e-15

# The NNC boundary condition was defined as p_He / P_REF_PA.
P_REF_PA = 101325.0
P_HE_UP_PA = 106325.0
P_HE_DOWN_PA = 0.0
M_HE_KG_MOL = 0.004002602

# Assumes He concentration is Henry-linear in pressure.
# Plateau quality: percent change across the final 15% of the time window.
PLATEAU_MAX_CHANGE_PERCENT = 1.0
# For verification by the ideal 1D step-source solution.
T50_COEFFICIENT = 7.205374209720384
BARRER_SI = 3.346e-16  # 1 Barrer ~ 3.346e-16 mol/(m*s*Pa)
TEMPERATURE_K = 298.15

# ===========================================================================

FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?$")
INSTANCE_RE = re.compile(r"\bCFRP_RVE-\d+\b", flags=re.I)


def _as_float(token):
    token = token.strip().replace('D', 'E').replace('d', 'e')
    return float(token) if FLOAT_RE.match(token) else None


def read_abaqus_xy_report(path):
    """Read Abaqus Report > XY (*.rpt): aligned X,Y[,Y...] tables.

    Returns [(header, [X], [[Y_column_1], ...]), ...]. If the report
    contains unrelated variables, this function will not guess which are
    RFL11; the caller must validate selections.
    """
    p = Path(path)
    raw = p.read_bytes()
    text = None
    for encoding in ('utf-8-sig', 'cp932', 'latin-1'):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    lines = text.splitlines()
    blocks = []
    rows = []
    header_lines = []
    current_header = ''
    column_count = None

    def finish():
        nonlocal rows, current_header, column_count
        if len(rows) >= 2:
            times = [r[0] for r in rows]
            vals = [[r[j] for r in rows] for j in range(1, len(rows[0]))]
            blocks.append((current_header, times, vals))
        rows = []
        current_header = ''
        column_count = None

    for line in lines:
        stripped = line.strip()
        parts = stripped.replace(',', ' ').split()
        numbers = [_as_float(token) for token in parts]
        numeric = len(numbers) >= 2 and all(val is not None for val in numbers)
        if numeric:
            if not rows:
                current_header = '\n'.join(header_lines[-15:])
                column_count = len(numbers)
            elif len(numbers) != column_count:
                finish()
                current_header = '\n'.join(header_lines[-15:])
                column_count = len(numbers)
            rows.append(numbers)
        elif stripped:
            if rows:
                finish()
                header_lines = []
            header_lines.append(stripped)
        # Blank lines between ordinary rows are tolerated.
    finish()

    if not blocks:
        raise ValueError('No numerical X-Y table was found in RPT. '
                         'Export using Visualization > Report > XY.')
    return blocks, text


def select_rfl_columns(blocks, whole_text, expected_instance=None):
    """Keep only RFL11 columns; reject ambiguous mixed-variable exports."""
    instances = set(INSTANCE_RE.findall(whole_text))
    if len(instances) > 1:
        raise ValueError('RPT names multiple instances: %s. Export only '
                         'downstream RFL11 of ONE instance before conversion.'
                         % ', '.join(sorted(instances)))
    if expected_instance and instances and expected_instance not in instances:
        raise ValueError('Expected instance %s, RPT contains %s.' %
                         (expected_instance, ', '.join(sorted(instances))))

    usable = []
    # Abaqus can append the *same* table to an existing RPT file when Report
    # XY is used repeatedly. Skip duplicate TABLES only, NOT equal-valued
    # columns (symmetric distinct nodes can legitimately have equal RFL11).
    seen_table_signatures = set()
    duplicate_table_count = 0
    for header, times, columns in blocks:
        signature = (' '.join(header.split()), tuple(times),
                     tuple(tuple(column) for column in columns))
        if signature in seen_table_signatures:
            duplicate_table_count += 1
            continue
        seen_table_signatures.add(signature)
        header_u = header.upper()
        has_rfl = 'RFL11' in header_u
        has_other = ('NNC11' in header_u or 'CONC' in header_u or
                     'MFL1' in header_u or 'MFL2' in header_u)
        if has_rfl and has_other:
            raise ValueError('RPT header mixes RFL11 with NNC/CONC/MFL. '
                             'Export RFL11 curves ONLY and retry.')
        if not has_rfl and has_other:
            continue
        # A standard aligned Abaqus report has one X column. When reports
        # use X,Y,X,Y instead, the second X must NOT be summed as flux.
        x_headers = re.findall(r'(?<![A-Za-z0-9_])X(?![A-Za-z0-9_])', header, re.I)
        if len(columns) > 1 and len(x_headers) > 1:
            raise ValueError('RPT appears to have repeated X columns. '
                             'Export as ONE aligned XY table (one X column).')
        if len(columns) > 1 and not has_rfl:
            raise ValueError('RPT contains %d unlabeled Y columns. '
                             'Cannot safely sum. Export a single SUM curve '
                             'or RFL11-only report.' % len(columns))
        usable.append((times, columns))
    if not usable:
        raise ValueError('No usable RFL11 XY curves. Export downstream RFL11.')
    if len(usable) > 1 and not all('RFL11' in header.upper()
                                   for header, _, _ in blocks if
                                   'RFL11' in header.upper() or
                                   not any(k in header.upper() for k in
                                           ('NNC11', 'MFL1', 'MFL2', 'CONC'))):
        raise ValueError('Several different unlabeled XY tables were found. '
                         'Export ONE total RFL11 curve only, or export '
                         'individually labeled RFL11 nodal curves.')

    reference_t = usable[0][0]
    if any(reference_t[i + 1] <= reference_t[i] for i in range(len(reference_t) - 1)):
        raise ValueError('Time X values are not strictly increasing.')

    all_columns = []
    for times, columns in usable:
        if len(times) != len(reference_t) or any(
                abs(a - b) > 1e-7 * max(1., abs(a), abs(b))
                for a, b in zip(times, reference_t)):
            raise ValueError('RFL curves have different X values. '
                             'Re-export as one Abaqus XY report with aligned times.')
        all_columns.extend(columns)
    signed_sum = [sum(col[i] for col in all_columns)
                  for i in range(len(reference_t))]
    return (reference_t, signed_sum, len(all_columns), sorted(instances),
            duplicate_table_count)


def median(values):
    return statistics.median(values)


def interpolate_crossing(t, y, target):
    for k in range(1, len(t)):
        if y[k - 1] < target <= y[k]:
            delta_y = y[k] - y[k - 1]
            if delta_y == 0:
                return t[k]
            return t[k-1] + (target - y[k-1]) * (t[k]-t[k-1]) / delta_y
    return None


def area_and_geometry(args):
    auto_l = math.sqrt(NUMBER_EQUIVALENT_FIBERS * math.pi *
                       args.radius_mm**2 / args.vf) if args.vf > 0 else None
    height = args.height_mm if args.height_mm is not None else auto_l
    width = args.width_mm if args.width_mm is not None else auto_l
    if height is None or width is None:
        raise ValueError('Set --height-mm and --width-mm when Vf=0 or '
                         'geometry cannot be inferred.')
    if min(height, width, args.depth_mm) <= 0:
        raise ValueError('Cell dimensions and out-of-plane depth must be positive.')
    geo_vf = (NUMBER_EQUIVALENT_FIBERS * math.pi * args.radius_mm**2 /
              (height * width)) if args.vf > 0 else None
    return height, width, width*args.depth_mm, geo_vf


def analyze(times, signed_rfl, args, curve_count):
    if args.t0 != 0:
        shifted = [(t-args.t0, r) for t, r in zip(times, signed_rfl)
                   if t >= args.t0]
        if len(shifted) < 2:
            raise ValueError('Less than two RPT rows after t0 shift.')
        times = [item[0] for item in shifted]
        signed_rfl = [item[1] for item in shifted]
    if len(times) < 2:
        raise ValueError('At least two time points are needed.')
    height_mm, width_mm, area_mm2, geometrical_vf = area_and_geometry(args)
    flow = [abs(value) for value in signed_rfl]
    end_time = times[-1]
    span = end_time - times[0]
    late_start = end_time - 0.15*span
    late = [v for t, v in zip(times, flow) if t >= late_start]
    if len(late) < 3:
        late = flow[-min(5, len(flow)):]
    plateau = median(late)
    if plateau <= 0:
        raise ValueError('Final RFL11 sum is zero. Select active downstream '
                         'NNC-constrained nodes in the correct instance.')
    rel_change = abs(late[-1] - late[0]) / plateau * 100.
    normalized = [f/plateau for f in flow]

    delta_p = args.pup_pa - args.pdown_pa
    if delta_p <= 0:
        raise ValueError('Upstream He partial pressure must exceed downstream.')
    if not (0 <= args.vf < 1):
        raise ValueError('Vf must be between 0 and 1 (exclusive upper bound).')
    if args.s_matrix <= 0 or args.p_ref <= 0 or args.d_matrix <= 0:
        raise ValueError('Matrix solubility, reference pressure and D must be positive.')

    # P: kg/s -> mol/s, mm -> m, mm2 -> m2.
    P_si = (plateau / M_HE_KG_MOL * (height_mm*1e-3) /
            (area_mm2*1e-6 * delta_p))
    # Abaqus c = s * phi; phi = p/p_ref =>
    # S_molar_SI = (s [kg/mm3] * 1e9 [mm3/m3]) / (M [kg/mol] * p_ref [Pa]).
    s_eff_finite = ((1-args.vf)*args.s_matrix + args.vf*args.s_fiber)
    s_eff_impermeable = (1-args.vf)*args.s_matrix
    S_eff_finite_si = s_eff_finite*1e9 / (M_HE_KG_MOL*args.p_ref)
    S_eff_impermeable_si = s_eff_impermeable*1e9 / (M_HE_KG_MOL*args.p_ref)
    D_ps_finite_si = P_si / S_eff_finite_si
    D_ps_impermeable_si = P_si / S_eff_impermeable_si

    t50 = interpolate_crossing(times, flow, .5*plateau)
    D_t50_si = ((height_mm*1e-3)**2 / (T50_COEFFICIENT*t50)
                 if t50 is not None and t50 > 0 else None)

    # Apparent time-lag from area between unit line and J(t)/Jss.
    # Valid as D=L2/(6*theta) ONLY under homogeneous 1D step-boundary model.
    theta = None
    D_tlag_si = None
    if times[0] <= 1e-10 and len(times) >= 3:
        theta = sum((t1-t0)*(.5*((1-f0/plateau)+(1-f1/plateau)))
                    for t0, t1, f0, f1 in zip(times[:-1], times[1:],
                                              flow[:-1], flow[1:]))
        if theta > 0:
            D_tlag_si = (height_mm*1e-3)**2/(6*theta)

    s_matrix_si = args.s_matrix*1e9/(M_HE_KG_MOL*args.p_ref)
    P_matrix_si = args.d_matrix*1e-6*s_matrix_si
    reference_mass_flow = (args.d_matrix * args.s_matrix *
                           (delta_p/args.p_ref) * area_mm2 / height_mm)
    # Independent cross-check entirely in Abaqus mm-kg-s units:
    # m_dot = D_eff * s_eff * (Delta p / p_ref) * (A/L).
    phi_delta = delta_p / args.p_ref
    D_direct_si = (plateau * height_mm /
                   (area_mm2 * s_eff_finite * phi_delta)) * 1e-6
    if abs(D_direct_si / D_ps_finite_si - 1.) > 1e-9:
        raise ArithmeticError('P/S and direct Abaqus-flux D formula disagree.')
    # Optional leak-rate conversion, not area scaled to a larger specimen.
    gas_constant = 8.314462618
    Q_mse = plateau/M_HE_KG_MOL * gas_constant*args.temperature_k

    warnings = []
    if rel_change > args.plateau_tolerance:
        warnings.append('Last 15%% changed by %.3f%% (> %.3f%%): P and D(P/S) '
                        'are provisional, no reliable steady plateau.' %
                        (rel_change, args.plateau_tolerance))
    if len(times) < 15:
        warnings.append('Sparse time samples: t50 and time-lag may be inaccurate.')
    if t50 is None:
        warnings.append('The curve did not cross half the estimated plateau: '
                        'D(t50) unavailable.')
    if times[0] > 1e-9:
        warnings.append('First time > 0: time-lag integration not computed.')
    if abs(geometrical_vf-args.vf) > .01 if geometrical_vf is not None else False:
        warnings.append('Geometrical Vf based on radius/count differs from input Vf. '
                        'Check actual Centered Part dimensions.')
    if args.vf > 0 and args.s_fiber > 0:
        warnings.append('CARBON_FIBER has finite solubility; use D(P/S,finite) '
                        'for current numerical model, ideal nonabsorbing D for '
                        'a separate idealized model ONLY.')
    if t50 is not None:
        warnings.append('D(t50) is a 1D homogeneous apparent D; the heterogeneous '
                        '2D RVE does not necessarily obey that formula.')
    if args.height_mm is None or args.width_mm is None:
        warnings.append('Centered-cell x/y dimensions were INFERRED from '
                        'fiber radius = %.6g mm and Vf = %.4g. Verify actual '
                        'Part dimensions before interpreting t50 and D(t50).' %
                        (args.radius_mm, args.vf))
    warnings.append('Abaqus RFL must have kg/s units, and 2D out-of-plane '

                    'depth must match the actual Section/model formulation.')
    warnings.append('For t50 and time-lag, upstream NNC must jump to a constant '
                    'value at t=0 (not ramp gradually).')

    metrics = dict(
        rpt=str(args.rpt), n_time=len(times), n_curves=curve_count,
        t_end_s=end_time, height_mm=height_mm, width_mm=width_mm,
        depth_mm=args.depth_mm, area_mm2=area_mm2, vf=args.vf,
        geo_vf=geometrical_vf, p_ref_pa=args.p_ref, p_delta_pa=delta_p,
        s_matrix_kg_mm3=args.s_matrix, s_fiber_kg_mm3=args.s_fiber,
        D_matrix_mm2_s=args.d_matrix,
        plateau_kg_s=plateau, late_change_pct=rel_change,
        P_mol_m_s_pa=P_si, P_Barrer=P_si/BARRER_SI,
        S_eff_finite_mol_m3_pa=S_eff_finite_si,
        S_eff_nonabsorbing_mol_m3_pa=S_eff_impermeable_si,
        D_ps_finite_m2_s=D_ps_finite_si,
        D_ps_nonabsorbing_m2_s=D_ps_impermeable_si,
        t50_s=t50, D_t50_m2_s=D_t50_si,
        time_lag_s=theta, D_tlag_m2_s=D_tlag_si,
        P_matrix_mol_m_s_pa=P_matrix_si,
        permeability_ratio=P_si/P_matrix_si,
        diffusivity_ratio_finite=D_ps_finite_si/(args.d_matrix*1e-6),
        reference_matrix_mass_kg_s=reference_mass_flow,
        Q_Pa_m3_s=Q_mse)
    return times, signed_rfl, flow, normalized, metrics, warnings


def fmt(x, unit=''):
    if x is None:
        return 'not available'
    return '% .8e%s' % (x, (' '+unit) if unit else '')


def output_results(args, times, signed, flow, normalized, metrics, warnings):
    path = Path(args.rpt)
    prefix = Path(args.output_prefix) if args.output_prefix else path.with_name(path.stem + '_DP')
    prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = prefix.with_suffix('.csv')
    txt_path = prefix.with_suffix('.txt')
    png_path = prefix.with_suffix('.png')

    with csv_path.open('w', newline='', encoding='utf-8-sig') as fd:
        writer = csv.writer(fd)
        writer.writerow(['time_s', 'rfl11_signed_sum_kg_s',
                         'downstream_mass_flow_kg_s', 'normalized_flow',
                         'downstream_leak_rate_Pa_m3_s'])
        for t, r, mass, f in zip(times, signed, flow, normalized):
            q = mass/M_HE_KG_MOL*8.314462618*args.temperature_k
            writer.writerow([repr(t), '%.12e'%r, '%.12e'%mass,
                             '%.9g'%f, '%.12e'%q])
    lines = [
        'ABAQUS RPT: EFFECTIVE He PERMEABILITY / DIFFUSIVITY',
        '='*65,
        'Input RPT: %s' % metrics['rpt'],
        'Number of RFL curves summed: %s' % metrics['n_curves'],
        'Time samples: %s' % metrics['n_time'],
        'End time: %s' % fmt(metrics['t_end_s'], 's'),
        '',
        'ASSUMED GEOMETRY / CONDITIONS',
        'Cell y length: %s' % fmt(metrics['height_mm'], 'mm'),
        'Cell x width: %s' % fmt(metrics['width_mm'], 'mm'),
        'Out-of-plane depth: %s' % fmt(metrics['depth_mm'], 'mm'),
        'Total transport area: %s' % fmt(metrics['area_mm2'], 'mm2'),
        'Vf: %.6f' % metrics['vf'],
        'Calculated geometry Vf, if inferred from fibers: %s' % fmt(metrics['geo_vf']),
        'Delta He pressure: %s' % fmt(metrics['p_delta_pa'], 'Pa'),
        'Reference pressure: %s' % fmt(metrics['p_ref_pa'], 'Pa'),
        'Matrix Abaqus s: %s' % fmt(metrics['s_matrix_kg_mm3'], 'kg/mm3'),
        'Fiber Abaqus s: %s' % fmt(metrics['s_fiber_kg_mm3'], 'kg/mm3'),
        '',
        'RFL11 STEADY-STATE CHECK',
        'Estimated plateau mass flow: %s' % fmt(metrics['plateau_kg_s'], 'kg/s'),
        'Relative change in last 15%% of time: %.4f%%' % metrics['late_change_pct'],
        'Hypothetical resin-only reference flow: %s' %
            fmt(metrics['reference_matrix_mass_kg_s'], 'kg/s'),
        '',
        'RESULTS',
        'P_eff: %s' % fmt(metrics['P_mol_m_s_pa'], 'mol/(m*s*Pa)'),
        'P_eff: %s' % fmt(metrics['P_Barrer'], 'Barrer'),
        'P_eff / P_m: %.8f' % metrics['permeability_ratio'],
        'S_eff (current finite-storage two-phase model): %s' %
            fmt(metrics['S_eff_finite_mol_m3_pa'], 'mol/(m3*Pa)'),
        'D_eff(P/S, current two-phase s): %s' %
            fmt(metrics['D_ps_finite_m2_s'], 'm2/s'),
        'D_eff(P/S, current)/D_matrix: %.8f' % metrics['diffusivity_ratio_finite'],
        '',
        'S_eff (IDEAL nonabsorbing fiber assumption): %s' %
            fmt(metrics['S_eff_nonabsorbing_mol_m3_pa'], 'mol/(m3*Pa)'),
        'D_eff(P/S, IDEAL nonabsorbing fiber): %s' %
            fmt(metrics['D_ps_nonabsorbing_m2_s'], 'm2/s'),
        '',
        't50: %s' % fmt(metrics['t50_s'], 's'),
        'D_app(t50, 1D homogeneous): %s' % fmt(metrics['D_t50_m2_s'], 'm2/s'),
        'Time lag (integral): %s' % fmt(metrics['time_lag_s'], 's'),
        'D_app(time lag, 1D homogeneous): %s' %
            fmt(metrics['D_tlag_m2_s'], 'm2/s'),
        'Ideal gas leak-rate for THIS model area at %.2f K: %s' %
            (args.temperature_k, fmt(metrics['Q_Pa_m3_s'], 'Pa*m3/s')),
        '',
        'WARNINGS / INTERPRETATION',
    ]
    lines.extend('- ' + warning for warning in warnings)
    lines.append('')
    txt_path.write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))
    print('Saved:', csv_path)
    print('Saved:', txt_path)
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(times, normalized, linewidth=1.7)
        ax.axhline(.5, linestyle='--', linewidth=1, label='50% steady flow')
        ax.axhline(1, linestyle=':', linewidth=1, label='steady flow')
        if metrics['t50_s'] is not None:
            ax.axvline(metrics['t50_s'], linestyle='--', linewidth=1,
                       label='t50 = %.4g s' % metrics['t50_s'])
        ax.set_xlabel('Step time (s)')
        ax.set_ylabel('Downstream total flow / estimated plateau')
        ax.set_title('Abaqus downstream RFL11, normalized')
        ax.legend()
        ax.grid(True, alpha=.3)
        fig.tight_layout()
        fig.savefig(str(png_path), dpi=180)
        plt.close(fig)
        print('Saved:', png_path)
    except ImportError:
        print('matplotlib is unavailable: PNG skipped; CSV/TXT are complete.')


def main():
    parser = argparse.ArgumentParser(
        description='Compute CF/PEEK RVE permeability and apparent D from Abaqus XY RPT.')
    parser.add_argument('rpt', nargs='?', default=RPT_PATH,
                        help='Exported Abaqus XY-data .rpt path')
    parser.add_argument('--height-mm', type=float, default=CELL_HEIGHT_MM,
                        help='Actual RVE y-size (diffusion direction)')
    parser.add_argument('--width-mm', type=float, default=CELL_WIDTH_MM,
                        help='Actual RVE x-size')
    parser.add_argument('--depth-mm', type=float, default=OUT_OF_PLANE_DEPTH_MM,
                        help='2D out-of-plane thickness; verify in Abaqus')
    parser.add_argument('--radius-mm', type=float, default=FIBER_RADIUS_MM)
    parser.add_argument('--vf', type=float, default=VF)
    parser.add_argument('--d-matrix', type=float, default=D_MATRIX_MM2_S,
                        help='Matrix D in mm2/s')
    parser.add_argument('--s-matrix', type=float, default=S_MATRIX_KG_MM3,
                        help='Matrix s in kg/mm3')
    parser.add_argument('--s-fiber', type=float, default=S_FIBER_KG_MM3,
                        help='Fiber s in kg/mm3, current numerical model')
    parser.add_argument('--p-ref', type=float, default=P_REF_PA,
                        help='Abaqus NNC reference pressure in Pa')
    parser.add_argument('--pup-pa', type=float, default=P_HE_UP_PA,
                        help='Upstream He partial pressure in Pa')
    parser.add_argument('--pdown-pa', type=float, default=P_HE_DOWN_PA,
                        help='Downstream He partial pressure in Pa')
    parser.add_argument('--t0', type=float, default=0.0,
                        help='True upstream step-exposure start in report time (s)')
    parser.add_argument('--temperature-k', type=float, default=TEMPERATURE_K)
    parser.add_argument('--plateau-tolerance', type=float,
                        default=PLATEAU_MAX_CHANGE_PERCENT)
    parser.add_argument('--instance', default=None,
                        help='Expected instance name, e.g. CFRP_RVE-3')
    parser.add_argument('--output-prefix', default=None,
                        help='Output prefix; CSV/TXT/PNG created')
    args = parser.parse_args()

    if not Path(args.rpt).exists():
        parser.error('RPT not found: %s. Specify the real file path on the command '
                     'line or edit RPT_PATH near the top of the script.' % args.rpt)
    blocks, text = read_abaqus_xy_report(args.rpt)
    times, signed, curve_count, instances, duplicate_count = select_rfl_columns(
        blocks, text, args.instance)
    if duplicate_count:
        print('Ignored %d EXACTLY DUPLICATED XY report table(s).' %
              duplicate_count)
    times, signed, flow, normalized, metrics, warnings = analyze(
        times, signed, args, curve_count)
    if instances:
        print('Detected instance:', ', '.join(instances))
    output_results(args, times, signed, flow, normalized, metrics, warnings)


if __name__ == '__main__':
    main()
