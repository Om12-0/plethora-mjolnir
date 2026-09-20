"""PHY2049 Lab 3 - RC circuit capacitor discharge experiment.

Measures the time constant tau = R * C by recording voltage across a
capacitor as it discharges through a resistor.
"""
import math

R_OHMS = 10_000.0        # 10 kOhm
C_FARADS = 100e-6        # 100 uF
V0 = 9.0                 # initial voltage


def tau():
    return R_OHMS * C_FARADS


def voltage(t):
    """Voltage across the capacitor at time t seconds (discharging)."""
    return V0 * math.exp(-t / tau())


def discharge_table(steps=10, duration=5.0):
    rows = []
    for i in range(steps):
        t = duration * i / (steps - 1)
        rows.append((t, round(voltage(t), 3)))
    return rows


if __name__ == "__main__":
    print(f"time constant tau = {tau():.2f} s")
    for t, v in discharge_table():
        print(f"t={t:4.1f}s  V={v:5.3f}V")
