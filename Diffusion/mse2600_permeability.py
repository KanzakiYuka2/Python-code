"""Calculate helium permeability from MSE2600 leak-rate results."""


# =========================================================
# User settings
# =========================================================

# MSE2600 leak rates are already in Pa m^3/s.
# Use the steady-state value reported by mse2600_t50_diffusion.py.
Q_SS_PA_M3_S = 6.92e-8

# Specimen dimensions.
THICKNESS_MM = 2.0
EXPOSED_WIDTH_MM = 41.0
EXPOSED_HEIGHT_MM = 41.0

# Helium pressures on both sides of the specimen.
# For a gas mixture, use helium partial pressure rather than total pressure.
UPSTREAM_HE_PRESSURE_PA = 106325.0
DOWNSTREAM_HE_PRESSURE_PA = 1.5

# Measurement temperature.
TEMPERATURE_C = 22.5


# =========================================================
# Constants and validation
# =========================================================

R = 8.314462618                 # Pa m^3/(mol K)
BARRER_SI = 3.348e-16           # mol m/(m^2 s Pa) per Barrer

if Q_SS_PA_M3_S <= 0:
    raise ValueError("Q_SS_PA_M3_S must be greater than zero.")

if THICKNESS_MM <= 0:
    raise ValueError("THICKNESS_MM must be greater than zero.")

if EXPOSED_WIDTH_MM <= 0 or EXPOSED_HEIGHT_MM <= 0:
    raise ValueError("Exposed specimen dimensions must be greater than zero.")

if UPSTREAM_HE_PRESSURE_PA <= DOWNSTREAM_HE_PRESSURE_PA:
    raise ValueError("Upstream helium pressure must exceed downstream pressure.")

temperature_k = TEMPERATURE_C + 273.15

if temperature_k <= 0:
    raise ValueError("Temperature must be above absolute zero.")


# =========================================================
# Permeability calculation
# =========================================================

thickness_m = THICKNESS_MM * 1e-3
area_m2 = (
    EXPOSED_WIDTH_MM * 1e-3
    * EXPOSED_HEIGHT_MM * 1e-3
)
delta_p_pa = UPSTREAM_HE_PRESSURE_PA - DOWNSTREAM_HE_PRESSURE_PA

# Convert vacuum throughput (Pa m^3/s) to molar flow (mol/s).
molar_flow_mol_s = Q_SS_PA_M3_S / (R * temperature_k)

# P = n_dot L / (A delta_p)
permeability_si = (
    molar_flow_mol_s
    * thickness_m
    / (area_m2 * delta_p_pa)
)

permeability_barrer = permeability_si / BARRER_SI


# =========================================================
# Results
# =========================================================

print()
print("=" * 68)
print("MSE2600 Helium Permeability Calculation")
print("=" * 68)
print(f"Q_SS                     : {Q_SS_PA_M3_S:.12e} Pa m^3/s")
print(f"Molar flow               : {molar_flow_mol_s:.12e} mol/s")
print(f"Specimen thickness       : {thickness_m:.12e} m")
print(f"Exposed area             : {area_m2:.12e} m^2")
print(f"Helium pressure difference: {delta_p_pa:.6f} Pa")
print(f"Temperature              : {temperature_k:.2f} K")
print("-" * 68)
print(
    "Permeability (SI)       : "
    f"{permeability_si:.12e} mol m/(m^2 s Pa)"
)
print(f"Permeability             : {permeability_barrer:.6f} Barrer")
print("=" * 68)
print()
