# =========================================================
# Helium permeability calculation
# =========================================================

# ASM340 mode leak rate
Q_mode = 2.34e-7               # mbar·L/s

# Specimen
thickness = 3.0e-3             # m
square=(41e-3)**2
area = square                # m²

# Pressure
upstream_absolute = 5000   # Pa
vacuum_pressure = 1.5          # Pa

# Temperature
temperature = 296.15           # K

# Constants
R = 8.314462618                # J/(mol·K)
BARRER_SI = 3.348e-16          # mol/(m·s·Pa)


# 1 mbar·L/s = 0.1 Pa·m³/s
Q_si = Q_mode * 0.1

delta_p = upstream_absolute - vacuum_pressure

P_volume = (
    Q_si * thickness
    / (area * delta_p)
)

P_molar = P_volume / (R * temperature)

P_barrer = P_molar / BARRER_SI


print(f"Pressure difference : {delta_p:.2f} Pa")
print(f"Permeability        : {P_barrer:.6f} Barrer")