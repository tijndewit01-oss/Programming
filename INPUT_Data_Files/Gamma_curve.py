"""Interactive tool for fitting a gamma curve to festival arrival data.

Scanner counts per 30-minute bin for three festival days are fitted with a
scaled gamma PDF. Day 1 is fitted automatically with curve_fit, and an
interactive matplotlib window lets you explore the shape/scale/shift parameters
by hand against any day's data via sliders and day-selection radio buttons.

The fitted Day 1 parameters printed here are what feed
config.VISITOR_GENERATOR['InterDepartDistributionParams'].
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, RadioButtons
from scipy.stats import gamma
from scipy.optimize import curve_fit

# --- Raw scanner data: counts per 30-minute bin, labelled by clock time ---
times = ['12:30', '13:00', '13:30', '14:00', '14:30', '15:00', '15:30', '16:00',
         '16:30', '17:00', '17:30', '18:00', '18:30', '19:00', '19:30', '20:00',
         '20:30', '21:00', '21:30', '22:00', '22:30', '23:00', '23:30']

day1 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 97, 615, 1045, 830, 503, 652, 760, 311, 114, 60, 31, 6]
day2 = [76, 1070, 1069, 822, 762, 553, 996, 610, 415, 224, 142, 100, 164, 148, 172, 170, 115, 100, 45, 17, 4, 0, 0]
day3 = [183, 1236, 1252, 971, 593, 778, 487, 247, 196, 111, 88, 68, 8, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0]

data_dict = {'Day 1': day1, 'Day 2': day2, 'Day 3': day3}

BIN_WIDTH = 1800  # Width of each bin in seconds (30 minutes).

def normalize_data(data):
    """Convert raw counts into probabilities so the bars sum to 1."""
    total = sum(data)
    if total == 0: return [0] * len(data)
    return [x / total for x in data]

def gamma_pdf_scaled(x, k, shift, theta):
    """Gamma PDF scaled by the bin width so it matches the probability bar heights."""
    return gamma.pdf(x, a=k, loc=shift, scale=theta) * BIN_WIDTH

# X axis in seconds since midnight: bin index i maps to clock time (i/2 + 12) h.
x_bars = np.arange(1, 24)
x_bars_second = (x_bars / 2 + 12) * 3600  # e.g. slot 1 -> 12:30 -> 45000 s.

# --- Fit the gamma parameters to Day 1 ---
# Initial guess: peak near 19:00 (68400 s) and a shift just before the first
# arrivals at 18:00 (64800 s); bounds keep the fit physically sensible.
p0 = [2.0, 64800.0, 3600.0]
bounds = ([0.1, 0.0, 1.0], [50.0, 86400.0, 86400.0])
opt_params, _ = curve_fit(
    gamma_pdf_scaled, x_bars_second, normalize_data(day1),
    p0=p0, bounds=bounds, maxfev=20000
)
opt_k, opt_shift, opt_theta = opt_params

print("Optimal parameters for Day 1 (time in seconds):")
print(f"  k (shape)  = {opt_k:.4f}")
print(f"  x₀ (shift) = {opt_shift:.1f} s  →  {int(opt_shift // 3600):02d}:{int((opt_shift % 3600) // 60):02d}")
print(f"  θ (scale)  = {opt_theta:.1f} s  →  {opt_theta / 3600:.3f} h")

# --- Slider start values: begin at the optimal fit so it can be explored from there ---
init_k     = opt_k
init_theta = opt_theta
init_shift = opt_shift
current_day = 'Day 1'

# --- Set up the figure and leave room at the bottom for the sliders ---
fig, ax = plt.subplots(figsize=(10, 7))
plt.subplots_adjust(bottom=0.35, left=0.2)

# Bar chart of the empirical (normalised) data for the current day.
norm_data = normalize_data(data_dict[current_day])
bars = ax.bar(x_bars_second, norm_data, color='lightgray', edgecolor='gray',
              alpha=0.8, label='Scanner Data', width=BIN_WIDTH)

# Fixed reference line: the best Day 1 fit, which never changes with the sliders.
y_opt = gamma_pdf_scaled(x_bars_second, opt_k, opt_shift, opt_theta)
opt_line, = ax.plot(x_bars_second, y_opt, lw=3, color='red', zorder=3,
                    label=f'Optimal Fit Day 1  (k={opt_k:.2f}, θ={opt_theta:.0f} s, x₀={opt_shift:.0f} s)')

# Interactive line driven by the sliders below.
y_line = gamma_pdf_scaled(x_bars_second, init_k, init_shift, init_theta)
line, = ax.plot(x_bars_second, y_line, lw=2, color='#1f77b4',
                linestyle='--', label='Gamma Fit (sliders)')

# Axis formatting and labels.
ax.set_xticks(x_bars_second)
ax.set_xticklabels(times, rotation=45, ha='right', fontsize=8)
ax.set_xlim(12.5 * 3600, 24 * 3600)
ax.set_ylim(0, max(norm_data) * 1.2)
ax.set_ylabel('Probability (fraction per 30-min bin)')
ax.set_title('Festival Scanner Arrival Rates vs. Gamma Distribution')
ax.legend(loc='upper right', fontsize=8)
ax.grid(True, linestyle='--', alpha=0.4)

# --- Sliders for the three gamma parameters, in the seconds domain ---
ax_k     = plt.axes([0.25, 0.20, 0.65, 0.03])
ax_theta = plt.axes([0.25, 0.15, 0.65, 0.03])
ax_shift = plt.axes([0.25, 0.10, 0.65, 0.03])

k_slider     = Slider(ax=ax_k,     label='Shape (k)',      valmin=0.5,     valmax=15.0,    valinit=init_k,     color='lightblue')
theta_slider = Slider(ax=ax_theta, label='Scale θ [s]',    valmin=100.0,   valmax=36000.0, valinit=init_theta, color='lightgreen')
shift_slider = Slider(ax=ax_shift, label='Shift x₀ [s]',   valmin=30000.0, valmax=82800.0, valinit=init_shift, color='salmon')

# --- Radio buttons to switch which day's data is shown ---
ax_radio = plt.axes([0.02, 0.5, 0.12, 0.15], facecolor='lightgoldenrodyellow')
radio = RadioButtons(ax_radio, ('Day 1', 'Day 2', 'Day 3'))

# --- Redraw callback: refresh the bars and interactive line on any change ---
def update(_val):
    """Redraw the bars and slider-driven curve when a widget changes."""
    k     = k_slider.val
    theta = theta_slider.val
    shift = shift_slider.val
    day   = radio.value_selected

    # Swap in the selected day's bars.
    new_norm_data = normalize_data(data_dict[day])
    for bar, h in zip(bars, new_norm_data):
        bar.set_height(h)

    # Recompute the interactive curve from the slider values.
    y_new = gamma_pdf_scaled(x_bars_second, k, shift, theta)
    line.set_ydata(y_new)

    # Rescale the y axis to fit whichever curve/bars are now tallest.
    max_all = max(max(new_norm_data), max(y_new), max(opt_line.get_ydata()))
    ax.set_ylim(0, max_all * 1.1)

    fig.canvas.draw_idle()

k_slider.on_changed(update)
theta_slider.on_changed(update)
shift_slider.on_changed(update)
radio.on_clicked(update)

plt.show()
