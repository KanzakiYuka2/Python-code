# -*- coding: utf-8 -*-
"""Extract effective transverse diffusion from Abaqus steady-state RVE jobs.
Run from the directory containing the ODB files and rve_geometry.json:
    abaqus python cfrp_rve_postprocess.py
Or set OUTPUT_DIR below to an absolute path.

Uses absolute RFL totals at the bottom node set.  The RFL sign convention
is checked using inlet/outlet mass conservation.  The result represents
2D transverse RVE homogenization, not a direct experimental t50.
"""
from odbAccess import openOdb
import os
import json
import csv
import math

OUTPUT_DIR = os.path.abspath('cfrp_rve_results')
MATRIX_D_MM2_S = 2.17e-4
MATRIX_SOL_KG_MM3 = 5.887e-13
NNC_TOP = 106325.0 / 101325.0
NNC_BOTTOM = 0.0


def sum_rfl(odb, frame, set_name):
    aset = odb.rootAssembly.nodeSets[set_name.upper()]
    result = frame.fieldOutputs['RFL'].getSubset(region=aset)
    vals = result.values
    if not vals:
        raise RuntimeError('No RFL values in ' + set_name)
    total = 0.0
    for v in vals:
        d = v.data
        if isinstance(d, (tuple, list)):
            total += float(d[0])
        else:
            total += float(d)
    return total, len(vals)


def main():
    os.chdir(OUTPUT_DIR)
    f = open('rve_geometry.json', 'r')
    geometries = json.load(f)
    f.close()
    output = []
    for case in geometries:
        job = case['job']
        odb_path = job + '.odb'
        if not os.path.exists(odb_path):
            print('Missing ODB: ' + odb_path)
            continue
        odb = openOdb(path=os.path.abspath(odb_path), readOnly=True)
        try:
            frame = odb.steps['Steady'].frames[-1]
            outlet, n_out = sum_rfl(odb, frame, 'OUTLET_NODES')
            inlet, n_in = sum_rfl(odb, frame, 'INLET_NODES')
            abs_out = abs(outlet)
            L = float(case['L_mm'])
            vf = float(case['vf_actual'])
            depth = float(case['out_of_plane_mm'])
            # For a fully-resin 2D slab with same height and width:
            # m_dot = D*s*(phi_top-phi_bottom)*(width*depth)/height.
            # Here width == height == L.
            ref_mdot = MATRIX_D_MM2_S * MATRIX_SOL_KG_MM3 * \
                abs(NNC_TOP-NNC_BOTTOM) * (L * depth) / L
            p_ratio = abs_out / ref_mdot
            s_ratio = 1.0 - vf  # insoluble, impermeable fibers
            d_ratio = p_ratio / s_ratio
            d_eff = MATRIX_D_MM2_S * d_ratio * 1.0e-6  # m2/s
            # Compare total influx/outflux: should be equal and opposite.
            mismatch = abs(inlet+outlet) / max(abs(inlet), abs(outlet), 1e-30)
            output.append((job, vf, case['n_fibers'], L,
                           abs_out, inlet, outlet,
                           p_ratio, s_ratio, d_ratio, d_eff,
                           mismatch, n_in, n_out))
            print('%s Vf=%.2f P/Pm=%.4f D/Dm=%.4f imbalance=%.3g' %
                  (job, vf, p_ratio, d_ratio, mismatch))
        except Exception as exc:
            print('FAILED %s: %s' % (job, exc))
        finally:
            odb.close()
    f = open('rve_effective_properties.csv', 'wb')
    writer = csv.writer(f)
    writer.writerow(('job', 'vf_actual', 'n_fibers', 'cell_side_mm',
                     'outlet_mass_flow_kg_s', 'rfl_in_signed_kg_s',
                     'rfl_out_signed_kg_s', 'P_eff_over_P_matrix',
                     'S_eff_over_S_matrix', 'D_eff_over_D_matrix',
                     'D_eff_m2_s', 'mass_imbalance_relative',
                     'n_inlet_nodes', 'n_outlet_nodes'))
    writer.writerows(output)
    f.close()
    print('Saved: rve_effective_properties.csv')


if __name__ == '__main__':
    main()
