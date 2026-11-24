# -*- coding: ascii -*-
"""CFRP centered-square fiber RVE for Abaqus/CAE 2016 or later.

Run: Abaqus/CAE > File > Run Script. Dimensions are in mm.
The fiber axes are perpendicular to this 2D cross-section. A central fiber
and four quarter fibers at the corners form two fibers per periodic cell.
This is a centered-square fiber array, not a 3D BCC lattice of spheres.
Geometry and material/section placeholders only: no material properties,
mesh, analysis step, boundary conditions, or job are supplied.
"""
from abaqus import mdb, session
from abaqusConstants import TWO_D_PLANAR, DEFORMABLE_BODY, CARTESIAN, ON, OFF
from math import pi, sqrt

# Edit these values before running. All lengths are in mm.
VF = 0.50
FIBER_DIAMETER_MM = 0.007  # 7 micrometers
AUTO_SAVE_CAE = False

if FIBER_DIAMETER_MM <= 0.0:
    raise ValueError('FIBER_DIAMETER_MM must be positive.')
# Nearest neighboring centers are L/sqrt(2), giving maximum Vf = pi/4.
if not 0.0 < VF < pi / 4.0:
    raise ValueError('VF must be greater than 0 and less than pi/4.')

r = FIBER_DIAMETER_MM / 2.0
L = sqrt(2.0 * pi * r * r / VF)
name_base = 'CFRP_CENTERED_Vf%02d' % int(round(100.0 * VF))
name = name_base
suffix = 1
while name in mdb.models.keys():
    name = '%s_run%02d' % (name_base, suffix)
    suffix += 1
model = mdb.Model(name=name)
sk = model.ConstrainedSketch(name='__cell__', sheetSize=max(0.1, 5.0 * L))
sk.rectangle(point1=(0.0, 0.0), point2=(L, L))
part = model.Part(name='CFRP_RVE', dimensionality=TWO_D_PLANAR,
                  type=DEFORMABLE_BODY)
part.BaseShell(sketch=sk)
del model.sketches['__cell__']

# Arc midpoints lie inside the square; arcs terminate on its boundary.
sk = model.ConstrainedSketch(name='__fibers__', sheetSize=max(0.1, 5.0 * L))
sk.CircleByCenterPerimeter(center=(L/2.0, L/2.0),
                           point1=(L/2.0 + r, L/2.0))
q = r / sqrt(2.0)
sk.Arc3Points(point1=(r, 0.0), point2=(0.0, r), point3=(q, q))
sk.Arc3Points(point1=(L-r, 0.0), point2=(L, r), point3=(L-q, q))
sk.Arc3Points(point1=(0.0, L-r), point2=(r, L), point3=(q, L-q))
sk.Arc3Points(point1=(L, L-r), point2=(L-r, L), point3=(L-q, L-q))
part.PartitionFaceBySketch(faces=part.faces[:], sketch=sk)
del model.sketches['__fibers__']

points = [(L/2.0, L/2.0), (r/4.0, r/4.0),
          (L-r/4.0, r/4.0), (r/4.0, L-r/4.0),
          (L-r/4.0, L-r/4.0)]
fiber_area = 0.0
for n, (x, y) in enumerate(points):
    faces = part.faces.findAt(((x, y, 0.0),))
    part.Set(name='FIBER_%02d' % (n+1), faces=faces)
    fiber_area += faces[0].getSize(printResults=OFF)
matrix_faces = part.faces.findAt(((L/2.0, r/4.0, 0.0),))
part.Set(name='MATRIX', faces=matrix_faces)
if len(part.faces) != 6:
    raise RuntimeError('Expected 5 fiber faces and 1 matrix face; got %d.' % len(part.faces))
total_area = 0.0
for face in part.faces:
    total_area += face.getSize(printResults=OFF)
actual_vf = fiber_area / total_area
if abs(total_area / (L*L) - 1.0) > 1.0e-4 or abs(actual_vf - VF) > 1.0e-4:
    raise RuntimeError('Geometry check failed: area=%.9g, Vf=%.9g' % (total_area, actual_vf))

# Placeholder materials: provide measured properties before analysis.
model.Material(name='MATRIX')
model.Material(name='CARBON_FIBER')
model.HomogeneousSolidSection(name='MATRIX_SECTION', material='MATRIX', thickness=1.0)
model.HomogeneousSolidSection(name='FIBER_SECTION', material='CARBON_FIBER', thickness=1.0)
part.SectionAssignment(region=part.sets['MATRIX'], sectionName='MATRIX_SECTION')
for n in range(5):
    part.SectionAssignment(region=part.sets['FIBER_%02d' % (n+1)], sectionName='FIBER_SECTION')
assembly = model.rootAssembly
assembly.DatumCsysByDefault(CARTESIAN)
assembly.Instance(name='CFRP_RVE-1', part=part, dependent=ON)
if len(session.viewports.keys()) > 0:
    view = session.viewports[session.viewports.keys()[0]]
    view.setValues(displayedObject=part)
    view.view.fitView()
print('Model: %s' % name)
print('Fiber diameter: %.6f mm; cell side: %.9f mm' % (FIBER_DIAMETER_MM, L))
print('Target Vf: %.6f; measured area fraction: %.6f' % (VF, actual_vf))
print('Geometry and empty materials only; add properties, mesh, steps and BCs.')
if AUTO_SAVE_CAE:
    mdb.saveAs(pathName=name + '.cae')
