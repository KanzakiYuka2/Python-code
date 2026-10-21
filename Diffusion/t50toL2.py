import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path


# =========================
# Experimental data
# =========================

# Select "t50" or "time_lag".
# For time_lag, enter theta values in characteristic_time_min below.
ANALYSIS_METHOD = "t50"

# PEEK thickness [mm]
thickness_mm = np.array([1.0, 2.0, 3.0])

# Characteristic time [min]
# t50 method   : enter t50 measured after He introduction
# time-lag method: enter theta obtained from the time-axis intercept
characteristic_time_min = np.array([19.089, 43.889, 95.418])

if ANALYSIS_METHOD not in {"t50", "time_lag"}:
    raise ValueError('ANALYSIS_METHOD must be "t50" or "time_lag".')

if len(thickness_mm) != len(characteristic_time_min):
    raise ValueError("Thickness and time arrays must have the same length.")

if len(thickness_mm) < 2:
    raise ValueError("At least two thickness-time pairs are required.")

if np.any(thickness_mm <= 0) or np.any(characteristic_time_min <= 0):
    raise ValueError("Thicknesses and characteristic times must be positive.")

if ANALYSIS_METHOD == "time_lag":
    method_factor = 6.0
    time_symbol = r"\theta"
    method_name = "Time-lag method"
    output_image = "PEEK_theta_vs_L2.png"
else:
    method_factor = 7.2
    time_symbol = r"t_{50}"
    method_name = "Half-time method"
    output_image = "PEEK_t50_vs_L2.png"


# =========================
# Calculate L^2
# =========================

L2_mm2 = thickness_mm ** 2


# =========================
# Linear fitting
# characteristic time = a * L^2 + b
# =========================

a, b = np.polyfit(L2_mm2, characteristic_time_min, 1)

# Predicted values
time_fit = a * L2_mm2 + b


# =========================
# Calculate R^2
# =========================

ss_res = np.sum((characteristic_time_min - time_fit) ** 2)
ss_tot = np.sum(
    (characteristic_time_min - np.mean(characteristic_time_min)) ** 2
)

r2 = 1 - ss_res / ss_tot


# =========================
# Calculate D from slope
# =========================

# t50 method    : D = L^2 / (7.2 * t50)
# time-lag method: D = L^2 / (6 * theta)
# The fitted slope a has units min/mm^2. Convert mm^2 to m^2 and min to s.
if a <= 0:
    raise ValueError("The fitted slope must be positive to calculate D.")

D_from_slope = 1e-6 / (method_factor * a * 60.0)


# =========================
# Make fitting line
# =========================

x_fit = np.linspace(0, 10, 300)
y_fit = a * x_fit + b


# =========================
# Plot
# =========================

plt.figure(figsize=(7, 5))

# Experimental points
plt.scatter(
    L2_mm2,
    characteristic_time_min,
    s=70,
    label="Experimental data"
)

# Linear fitting line
plt.plot(
    x_fit,
    y_fit,
    label="Linear fit"
)


# =========================
# Labels
# =========================

plt.xlabel(r"$L^2$ [mm$^2$]", fontsize=18)
plt.ylabel(rf"${time_symbol}$ [min]", fontsize=18)
plt.tick_params(axis="both", labelsize=18)

plt.grid(alpha=0.3)
plt.legend(fontsize=18, loc="lower right")


# =========================
# Show fitting equation
# =========================

text = (
    rf"${time_symbol} = {a:.3f}L^2 {b:+.3f}$"
    "\n"
    rf"$R^2 = {r2:.4f}$"
    "\n"
    rf"$D = {D_from_slope:.3e}\ \mathrm{{m^2/s}}$"
)

plt.text(
    0.05,
    0.95,
    text,
    transform=plt.gca().transAxes,
    verticalalignment="top",
    fontsize=18
)


# =========================
# Save and show
# =========================

plt.tight_layout()

# Always save beside this script in Diffusion, regardless of the working directory.
output_path = Path(__file__).resolve().parent / output_image
plt.savefig(
    output_path,
    dpi=300,
    bbox_inches="tight"
)

plt.show()


# =========================
# Print results
# =========================

print(f"Slope = {a:.6f} min/mm^2")
print(f"Intercept = {b:.6f} min")
print(f"R^2 = {r2:.6f}")
print(f"Method = {method_name}")
print(f"D from slope = {D_from_slope:.6e} m^2/s")
print(f"Graph saved as = {output_path}")
