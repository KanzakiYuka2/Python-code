# -*- coding: utf-8 -*-
"""CFRP 2-D random fiber RVE for Abaqus/CAE 2016 (Python 2.7).

Run from the Abaqus/CAE GUI: File > Run Script, OR:
    abaqus cae noGUI=cfrp_rve_abaqus2016.py

Creates 2D resin sheets with impermeable circular fiber holes, DC2D3
meshes, steady-state mass diffusion cases, and an Abaqus job for each Vf.
The fibers are aligned perpendicular to the model plane; the model
therefore evaluates transverse diffusion (not along the fiber axes).

IMPORTANT: The random geometry is a hard-core *finite* window made by
randomizing an initial square grid. It is NOT a periodic RVE. No-flux
conditions on left/right edges introduce boundary-size effects.
Run multiple random seeds and a cell-size convergence study.

This code was statically checked but cannot be run/tested against Abaqus
in this environment. Inspect the .cae models before submitting jobs.
"""
from abaqus import mdb
from abaqusConstants import (
    TWO_D_PLANAR, DEFORMABLE_BODY, ON, OFF,
    TRI, FREE, STANDARD, FICK, ISOTROPIC, STEADY_STATE,
    ANALYSIS, PERCENTAGE, DC2D3,
)
import mesh
import math
import random
import os
import csv
import json

# =============================================================
# USER SETTINGS -- millimetre, second, kilogram
# =============================================================
VFS = (0.00, 0.30, 0.40, 0.50, 0.60)
RANDOM_SEEDS = (11,)             # e.g. (11, 21, 31) for repeats
GRID_SIDE = 4                    # 4 x 4 = 16 fibers (Student Edition)
FIBER_RADIUS_MM = 0.0035        # fixed physical radius: 7 um diameter
REFERENCE_VF_FOR_ZERO = 0.50
MIN_FIBER_GAP_MM = 0.00010
BOUNDARY_GAP_MM = 0.00010
RANDOM_WALK_STEPS = 3500
MESH_SIZE_MM = 0.0019           # use a mesh convergence test later
MAX_NODES = 950                # 2016 Student limit is commonly 1000
MATRIX_D_MM2_S = 2.17e-4       # PEEK 2 mm re-test: 2.17e-10 m2/s
MATRIX_SOL_KG_MM3 = 5.887e-13  # with p_ref = 101325 Pa
NNC_TOP = 106325.0 / 101325.0
NNC_BOTTOM = 0.0
OUT_OF_PLANE_MM = 1.0
RUN_JOBS = False                # initially write .inp files only
WRITE_INPUT = True
OUTPUT_DIR = os.path.abspath('cfrp_rve_results')
PROJECT_FILE = 'cfrp_rve_vf_sweep.cae'


def feasible_move(x, y, centers, index, cell_side, radius):
    wall = radius + BOUNDARY_GAP_MM
    if x <= wall or x >= cell_side - wall:
        return False
    if y <= wall or y >= cell_side - wall:
        return False
    min_sep_sq = (2.0 * radius + MIN_FIBER_GAP_MM)**2
    for j, other in enumerate(centers):
        if j == index:
            continue
        dx = x - other[0]
        dy = y - other[1]
        if dx * dx + dy * dy <= min_sep_sq:
            return False
    return True


def generate_centers(vf, seed):
    """Randomized hard-disc layout with fixed physical fiber radius."""
    n = GRID_SIDE * GRID_SIDE
    if vf <= 0.0:
        vf_for_size = REFERENCE_VF_FOR_ZERO
    else:
        vf_for_size = vf
    r = FIBER_RADIUS_MM
    cell_side = math.sqrt(n * math.pi * r * r / vf_for_size)
    pitch = cell_side / GRID_SIDE
    if pitch <= 2.0 * r + MIN_FIBER_GAP_MM:
        raise ValueError('Vf is too high for this packing and fixed radius')
    rng = random.Random(int(seed))
    centers = []
    for iy in range(GRID_SIDE):
        for ix in range(GRID_SIDE):
            centers.append(((ix + 0.5) * pitch, (iy + 0.5) * pitch))
    if vf <= 0.0:
        return cell_side, []

    # Small initial perturbations are guaranteed collision-free.
    delta = min(0.30 * (pitch - 2.0 * r - MIN_FIBER_GAP_MM),
                0.30 * (pitch / 2.0 - r - BOUNDARY_GAP_MM))
    if delta <= 0:
        raise ValueError('Insufficient room between fiber and cell boundary')
    for j in range(n):
        x, y = centers[j]
        for attempt in range(100):
            xx = x + rng.uniform(-delta, delta)
            yy = y + rng.uniform(-delta, delta)
            if feasible_move(xx, yy, centers, j, cell_side, r):
                centers[j] = (xx, yy)
                break
    # Monte Carlo random moves destroy regular row/column ordering,
    # subject to hard-core no-overlap and side-wall exclusion.
    move_scale = max(0.22 * (pitch - 2.0 * r), 0.00004)
    for step in range(RANDOM_WALK_STEPS):
        j = rng.randrange(n)
        x, y = centers[j]
        xx = x + rng.uniform(-move_scale, move_scale)
        yy = y + rng.uniform(-move_scale, move_scale)
        if feasible_move(xx, yy, centers, j, cell_side, r):
            centers[j] = (xx, yy)
    return cell_side, centers


def write_preview_svg(path, cell_side, centers, vf):
    """SVG viewable in a web browser, no external Python libraries."""
    w = 600.0
    scale = w / cell_side
    r_px = FIBER_RADIUS_MM * scale
    f = open(path, 'w')
    f.write('<svg xmlns="http://www.w3.org/2000/svg" width="650" height="690" viewBox="0 0 650 690">\n')
    f.write('<rect x="20" y="20" width="600" height="600" fill="#e5f2fc" stroke="#24466c" stroke-width="2"/>\n')
    for (x, y) in centers:
        f.write('<circle cx="%.5f" cy="%.5f" r="%.5f" fill="#67717f" stroke="#303b4d" stroke-width="1"/>\n' %
                (20 + x * scale, 620 - y * scale, r_px))
    f.write('<text x="20" y="650" font-size="18">Vf=%.1f%%, %d fibers, cell side=%.4f mm</text>\n' %
            (100 * vf, len(centers), cell_side))
    f.write('</svg>\n')
    f.close()


def make_case(model_name, vf, seed):
    L, centers = generate_centers(vf, seed)
    model = mdb.Model(name=model_name)
    model.setValues(absoluteZero=-273.15)
    sketch = model.ConstrainedSketch(name='RVE_Profile', sheetSize=10.0 * L)
    sketch.rectangle(point1=(0.0, 0.0), point2=(L, L))
    for (x, y) in centers:
        sketch.CircleByCenterPerimeter(
            center=(x, y), point1=(x + FIBER_RADIUS_MM, y))
    part = model.Part(name='Matrix_Only', dimensionality=TWO_D_PLANAR,
                      type=DEFORMABLE_BODY)
    # The inner closed circles are physical holes: no fiber elements.
    part.BaseShell(sketch=sketch)
    del model.sketches['RVE_Profile']

    mat = model.Material(name='PEEK_MATRIX')
    mat.Diffusivity(type=ISOTROPIC, law=FICK,
                    table=((MATRIX_D_MM2_S, 0.0),))
    mat.Solubility(table=((MATRIX_SOL_KG_MM3,),))
    model.HomogeneousSolidSection(name='MatrixSection',
                                  material='PEEK_MATRIX', thickness=OUT_OF_PLANE_MM)
    part.Set(name='ALL_RESIN', faces=part.faces[:])
    part.SectionAssignment(region=part.sets['ALL_RESIN'],
                           sectionName='MatrixSection')

    # An unstructured triangle mesh handles the multi-hole geometry.
    part.setMeshControls(regions=part.faces[:], elemShape=TRI, technique=FREE)
    part.setElementType(regions=part.faces[:],
                        elemTypes=(mesh.ElemType(elemCode=DC2D3,
                                                 elemLibrary=STANDARD),))
    part.seedPart(size=MESH_SIZE_MM, deviationFactor=0.1, minSizeFactor=0.15)
    part.generateMesh()
    n_nodes = len(part.nodes)
    if n_nodes > MAX_NODES:
        raise RuntimeError('%s has %d nodes (limit %d). Increase MESH_SIZE_MM.' %
                           (model_name, n_nodes, MAX_NODES))

    assembly = model.rootAssembly
    inst = assembly.Instance(name='RESIN-1', part=part, dependent=ON)
    assembly.regenerate()
    eps = 1.0e-7 * L
    top_edges = inst.edges.getByBoundingBox(xMin=-eps, yMin=L-eps,
                                             xMax=L+eps, yMax=L+eps)
    bot_edges = inst.edges.getByBoundingBox(xMin=-eps, yMin=-eps,
                                             xMax=L+eps, yMax=eps)
    if not top_edges or not bot_edges:
        raise RuntimeError('Could not select TOP/BOTTOM boundary edges')
    assembly.Set(name='TOP', edges=top_edges)
    assembly.Set(name='BOTTOM', edges=bot_edges)
    # Nodes for RFL extraction after the mesh is generated.
    bottom_nodes = inst.nodes.getByBoundingBox(
        xMin=-eps, yMin=-eps, xMax=L+eps, yMax=eps)
    if not bottom_nodes:
        raise RuntimeError('No BOTTOM nodes found')
    assembly.Set(name='OUTLET_NODES', nodes=bottom_nodes)
    top_nodes = inst.nodes.getByBoundingBox(
        xMin=-eps, yMin=L-eps, xMax=L+eps, yMax=L+eps)
    assembly.Set(name='INLET_NODES', nodes=top_nodes)

    model.MassDiffusionStep(name='Steady', previous='Initial',
                            response=STEADY_STATE, timePeriod=1.0,
                            initialInc=0.1, maxNumInc=100)
    model.ConcentrationBC(name='NNC_TOP', createStepName='Steady',
                          region=assembly.sets['TOP'], magnitude=NNC_TOP)
    model.ConcentrationBC(name='NNC_BOTTOM', createStepName='Steady',
                          region=assembly.sets['BOTTOM'], magnitude=NNC_BOTTOM)
    # No explicit BC on holes/side walls = zero normal diffusion flux.
    model.FieldOutputRequest(name='DiffusionFields', createStepName='Steady',
                             variables=('NNC', 'RFL', 'MFL'))

    job_name = model_name.replace('MODEL_', 'RVE_')
    job = mdb.Job(name=job_name, model=model_name, type=ANALYSIS,
                  memory=70, memoryUnits=PERCENTAGE, numCpus=1)
    if WRITE_INPUT:
        job.writeInput(consistencyChecking=OFF)
    return L, centers, n_nodes, job_name


def main():
    if not os.path.isdir(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    os.chdir(OUTPUT_DIR)
    rows = []
    metadata = []
    for vf in VFS:
        for seed in RANDOM_SEEDS:
            vf_tag = int(round(vf * 100))
            model_name = 'MODEL_VF%02d_S%d' % (vf_tag, seed)
            print('Building %s ...' % model_name)
            try:
                L, centers, n_nodes, job_name = make_case(model_name, vf, seed)
                svg_file = model_name + '.svg'
                write_preview_svg(svg_file, L, centers, vf)
                meta = dict(model=model_name, job=job_name, vf_target=vf,
                            vf_actual=len(centers)*math.pi*FIBER_RADIUS_MM**2/L**2,
                            L_mm=L, radius_mm=FIBER_RADIUS_MM,
                            n_fibers=len(centers), n_nodes=n_nodes, seed=seed,
                            out_of_plane_mm=OUT_OF_PLANE_MM, centers_mm=centers)
                metadata.append(meta)
                rows.append((model_name, job_name, vf, meta['vf_actual'],
                             L, len(centers), n_nodes, 'OK'))
                if RUN_JOBS:
                    mdb.jobs[job_name].submit(consistencyChecking=OFF)
                    mdb.jobs[job_name].waitForCompletion()
            except Exception as exc:
                rows.append((model_name, '', vf, '', '', '', '', str(exc)))
                print('FAILED %s: %s' % (model_name, exc))

    mdb.saveAs(pathName=os.path.join(OUTPUT_DIR, PROJECT_FILE))
    f = open('rve_manifest.csv', 'wb')
    writer = csv.writer(f)
    writer.writerow(('model', 'job', 'vf_target', 'vf_actual',
                     'L_mm', 'n_fibers', 'n_nodes', 'status'))
    writer.writerows(rows)
    f.close()
    f = open('rve_geometry.json', 'w')
    json.dump(metadata, f, indent=2)
    f.close()
    print('Finished. Output directory: ' + OUTPUT_DIR)
    print('Inspect geometry, mesh, and boundary sets before analyzing.')


if __name__ == '__main__':
    main()
