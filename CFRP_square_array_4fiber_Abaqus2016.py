# -*- coding: ascii -*-
"""CFRP 2D square-array unit cell for Abaqus/CAE 2016 (Python 2.7).

PURPOSE
  Generate a 2x2 square array of circular carbon-fiber domains within a
  PEEK matrix, with ALL five faces present (NO HOLES).

RUN
  Abaqus/CAE -> File -> Run Script -> select this file.

The script creates geometry, named sets, empty material definitions, section
assignments, and an assembly instance. It does NOT create a mesh, step, BC,
or job. Populate material diffusion properties before solving.

All dimensions are in mm; a 7-um fiber has diameter 0.007 mm.
"""

from abaqus import mdb, session
from abaqusConstants import (TWO_D_PLANAR, DEFORMABLE_BODY, CARTESIAN,
                             ON, OFF)
from math import pi, sqrt

# ============ EDIT THESE SETTINGS ============
VF = 0.50                    # Fiber volume fraction: 0.40, 0.50, 0.60 ...
FIBER_DIAMETER_MM = 0.007    # Carbon fiber diameter: 7 um
GRID_N = 2                   # 2x2 square array = 4 full fiber faces
MAKE_SECTIONS = True         # Separate PEEK/FIBER materials and sections
AUTO_SAVE_CAE = False        # True => save a new .cae file in working folder
# =============================================

# 0. Validate parameters. For this no-cut-circle square layout, the maximum
# geometrically possible Vf is pi/4 (close packing). A smaller upper limit
# avoids near-tangent geometry that is difficult to mesh.
if not (0.05 <= VF <= 0.70):
    raise ValueError('VF must be between 0.05 and 0.70 in this starter model.')
if FIBER_DIAMETER_MM <= 0:
    raise ValueError('FIBER_DIAMETER_MM must be positive.')
if GRID_N < 1:
    raise ValueError('GRID_N must be >= 1.')

radius = FIBER_DIAMETER_MM / 2.0
number_of_fibers = GRID_N * GRID_N
cell_side = sqrt(number_of_fibers * pi * radius**2 / VF)
pitch = cell_side / float(GRID_N)

# All circles must lie strictly inside the cell and must not overlap.
if pitch <= 2.0 * radius:
    raise ValueError('Overlapping/touching fibers: lower VF.')

centers = []
for j in range(GRID_N):
    for i in range(GRID_N):
        x = (i + 0.5) * pitch
        y = (j + 0.5) * pitch
        centers.append((x, y))

# Each execution creates its own uniquely named Abaqus model.
base = 'CFRP_SQUARE_%dF_Vf%02d' % (number_of_fibers, int(round(100*VF)))
model_name = base
k = 1
while model_name in mdb.models.keys():
    model_name = '%s_run%02d' % (base, k)
    k += 1
model = mdb.Model(name=model_name)

# 1. Create one filled square face.
sk = model.ConstrainedSketch(name='__square__',
                             sheetSize=max(0.1, 5.0 * cell_side))
sk.rectangle(point1=(0.0, 0.0), point2=(cell_side, cell_side))
p = model.Part(name='CFRP_UNIT_CELL', dimensionality=TWO_D_PLANAR,
               type=DEFORMABLE_BODY)
p.BaseShell(sketch=sk)
del model.sketches['__square__']

# 2. Partition (do NOT cut!) 4 circles out of the filled square face.
#    The circles remain solid 2D faces and can receive a carbon-fiber section.
sk = model.ConstrainedSketch(name='__partition_fibers__',
                             sheetSize=max(0.1, 5.0 * cell_side))
for cx, cy in centers:
    sk.CircleByCenterPerimeter(center=(cx, cy),
                               point1=(cx + radius, cy))
p.PartitionFaceBySketch(faces=p.faces[:], sketch=sk)
del model.sketches['__partition_fibers__']

# 3. Make one matrix set and one set per fiber.
#    The center of the entire cell is matrix, between the four fibers.
matrix_faces = p.faces.findAt(((0.5*cell_side, 0.5*cell_side, 0.0),))
p.Set(name='MATRIX', faces=matrix_faces)
fiber_faces = []
for i, (cx, cy) in enumerate(centers):
    name = 'FIBER_%02d' % (i+1)
    selected_faces = p.faces.findAt(((cx, cy, 0.0),))
    p.Set(name=name, faces=selected_faces)
    fiber_faces.append(selected_faces[0])

# Boundary edge sets, useful for future Mass Diffusion BCs.
p.Set(name='UPSTREAM',
      edges=p.edges.findAt(((0.5*cell_side, cell_side, 0.0),)))
p.Set(name='DOWNSTREAM',
      edges=p.edges.findAt(((0.5*cell_side, 0.0, 0.0),)))
p.Set(name='LEFT',
      edges=p.edges.findAt(((0.0, 0.5*cell_side, 0.0),)))
p.Set(name='RIGHT',
      edges=p.edges.findAt(((cell_side, 0.5*cell_side, 0.0),)))

# 4. Validate actual geometric coverage (not merely the circle count).
expected_faces = number_of_fibers + 1
if len(p.faces) != expected_faces:
    raise RuntimeError('Expected %d filled faces; got %d.' %
                       (expected_faces, len(p.faces)))

# Avoid sum(): the CAE execution namespace may provide a version that
# requires a sequence rather than a Python generator.
full_area = 0.0
for face in p.faces:
    full_area += face.getSize(printResults=OFF)
fiber_area = 0.0
for face in fiber_faces:
    fiber_area += face.getSize(printResults=OFF)
area_error = abs(full_area - cell_side**2) / (cell_side**2)
actual_vf = fiber_area / full_area
if area_error > 1.0e-4:
    raise RuntimeError('Geometry has missing area: relative error = %.4g' %
                       area_error)
if abs(actual_vf - VF) > 1.0e-4:
    raise RuntimeError('Fiber fraction mismatch: target %.6f / actual %.6f' %
                       (VF, actual_vf))

# 5. Optional separate material / section assignments.
#    These are IDENTIFIERS ONLY, not completed diffusion material properties.
#    Do not submit a Mass Diffusion job without adding suitable material data.
if MAKE_SECTIONS:
    model.Material(name='PEEK_MATRIX')
    model.Material(name='CARBON_FIBER')
    model.HomogeneousSolidSection(name='PEEK_SECTION',
                                  material='PEEK_MATRIX', thickness=1.0)
    model.HomogeneousSolidSection(name='FIBER_SECTION',
                                  material='CARBON_FIBER', thickness=1.0)
    p.SectionAssignment(region=p.sets['MATRIX'],
                        sectionName='PEEK_SECTION')
    for i in range(number_of_fibers):
        p.SectionAssignment(region=p.sets['FIBER_%02d' % (i+1)],
                            sectionName='FIBER_SECTION')

# 6. Assembly instance for later modeling.
a = model.rootAssembly
a.DatumCsysByDefault(CARTESIAN)
a.Instance(name='CFRP_UNIT_CELL-1', part=p, dependent=ON)

# 7. Show the new part.
if len(session.viewports.keys()) > 0:
    v = session.viewports[session.viewports.keys()[0]]
    v.setValues(displayedObject=p)
    v.view.fitView()

print('===============================================')
print('MODEL: %s' % model_name)
print('Square-array RVE with FULL fiber regions (no holes)')
print('Faces: %d [matrix=1, fibers=%d]' %
      (len(p.faces), number_of_fibers))
print('Fiber diameter: %.6f mm (%.2f um)' %
      (FIBER_DIAMETER_MM, FIBER_DIAMETER_MM*1000.0))
print('Cell side: %.10f mm (%.5f um)' %
      (cell_side, cell_side*1000.0))
print('Vf requested: %.5f  |  Vf verified: %.5f' %
      (VF, actual_vf))
print('Total face area / cell area: %.8f' %
      (full_area/(cell_side*cell_side)))
print('Model is geometry-only; no mesh/step/BC/job is generated.')
if MAKE_SECTIONS:
    print('PEEK and CARBON_FIBER materials/sections created (properties unset).')
print('===============================================')

if AUTO_SAVE_CAE:
    mdb.saveAs(pathName=model_name + '.cae')
    print('Saved CAE: ' + model_name + '.cae')
else:
    print('Not saved yet. In Abaqus choose File > Save As.')
