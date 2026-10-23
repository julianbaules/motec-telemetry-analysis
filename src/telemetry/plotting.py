"""Figures. Every function takes prepared data and saves one PNG."""
import matplotlib

matplotlib.use("Agg")  # no window: figures are written to files
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.transforms import offset_copy

from . import analysis as A

# ---------------------------------------------------------------- style
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
NEUTRAL = "#b5b3ad"
BLUE = "#2a78d6"        # Stint 1 / reference
ORANGE = "#eb6834"      # Stint 6 / comparison
CRITICAL = "#d03b3b"    # incidents (spins)
STINT_COLORS = {"Stint 1": BLUE, "Stint 6": ORANGE}

SEQ_BLUE = LinearSegmentedColormap.from_list(
    "seq_blue", ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"])
DIVERGING = LinearSegmentedColormap.from_list(
    "blue_red", ["#2a78d6", "#86b6ef", "#f0efec", "#ec9a9a", "#d03b3b"])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 9,
    "text.color": INK, "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.edgecolor": GRID, "axes.linewidth": 0.8,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "grid.linestyle": "-",
    "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
    "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.titlecolor": INK, "legend.frameon": False, "lines.linewidth": 1.4,
})


def _save(fig, path, title=None, subtitle=None):
    """Title and subtitle sit just above everything already drawn, then the PNG is written."""
    fig.canvas.draw()
    top = fig.get_tightbbox(fig.canvas.get_renderer()).y1 / fig.get_figheight()  # figure fraction
    if title:
        y_title = 24 if subtitle else 8
        fig.text(0.01, top, title, ha="left", va="bottom", fontsize=12, fontweight="bold", color=INK,
                 transform=offset_copy(fig.transFigure, fig=fig, y=y_title, units="points"))
    if subtitle:
        fig.text(0.01, top, subtitle, ha="left", va="bottom", fontsize=9, color=INK_2,
                 transform=offset_copy(fig.transFigure, fig=fig, y=8, units="points"))
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def _shade_corners(ax, corners, label=False):
    """Light grey bands on the corners, with their names on the top panel."""
    for _, c in corners.iterrows():
        ax.axvspan(c["Start_m"], c["End_m"], color="#efeeea", zorder=0, lw=0)
        if label:
            ax.text((c["Start_m"] + c["End_m"]) / 2, 1.02, c["Corner"], transform=ax.get_xaxis_transform(),
                    ha="center", va="bottom", fontsize=8, color=INK_2)


def _track_line(ax, x, y, values, cmap, norm, lw=4.0):
    points = np.column_stack([x, y]).reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    lc = LineCollection(segments, cmap=cmap, norm=norm, linewidth=lw, capstyle="round")
    lc.set_array(np.asarray(values)[:-1])
    ax.add_collection(lc)
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.axis("off")
    return lc


def _label_corners_on_map(ax, corners, offset=28):
    cx, cy = corners["X"].mean(), corners["Y"].mean()
    for _, c in corners.iterrows():
        dx, dy = c["X"] - cx, c["Y"] - cy
        n = np.hypot(dx, dy) or 1
        ax.annotate(c["Corner"], (c["X"], c["Y"]), xytext=(c["X"] + dx / n * offset, c["Y"] + dy / n * offset),
                    ha="center", va="center", fontsize=8, fontweight="bold", color=INK,
                    arrowprops=dict(arrowstyle="-", color=INK_2, lw=0.6))


# ---------------------------------------------------------------- 1. lap times
def plot_lap_times(table: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(8, 3.6))
    timed = table[table["Status"].isin(["clean", "incident"])]
    for stint, grp in timed.groupby("Stint"):
        clean = grp[grp["Status"] == "clean"]
        shift = -0.08 if stint == "Stint 1" else 0.08     # keeps dots of the same lap apart
        ax.plot(clean["Lap"] + shift, clean["LapTime_s"], "o", color=STINT_COLORS[stint], ms=8,
                label=f"{stint} – clean laps", mec=SURFACE, mew=1.5)
        inc = grp[grp["Status"] == "incident"]
        ax.plot(inc["Lap"], inc["LapTime_s"], "X", color=CRITICAL, ms=9, mec=SURFACE, mew=1)
        for _, r in inc.iterrows():
            ax.annotate(f"spin T2  {r['LapTime_s']:.3f}", (r["Lap"], r["LapTime_s"]), xytext=(8, 0),
                        textcoords="offset points", va="center", fontsize=8, color=INK_2)
    best = timed[timed["Status"] == "clean"].sort_values("LapTime_s").iloc[0]
    ax.annotate(f"best {best['LapTime_s']:.3f} s", (best["Lap"], best["LapTime_s"]), xytext=(0, 10),
                textcoords="offset points", ha="center", fontsize=8, fontweight="bold", color=INK)
    ax.plot([], [], "X", color=CRITICAL, ms=8, label="lap with a spin")
    ax.set_xlabel("Lap")
    ax.set_ylabel("Lap time (s)")
    ax.set_xticks(sorted(timed["Lap"].unique()))
    ax.set_ylim(48.2, 56)
    ax.legend(loc="upper right", ncols=3, fontsize=8)
    ax.set_xlim(0.5, timed["Lap"].max() + 0.9)
    _save(fig, path, "Lap times", "Out-laps and the unfinished last lap of each stint are not shown")


# ---------------------------------------------------------------- 2. best laps
def plot_lap_comparison(ref, comp, ref_label, comp_label, corners, path):
    delta = A.delta_time(ref, comp)
    panels = [("Ground Speed", "Speed (km/h)"), ("Throttle Pos", "Throttle (%)"),
              ("Brake Pos", "Brake (%)"), ("Steering Angle", "Steering (deg)")]
    fig, axes = plt.subplots(5, 1, figsize=(10, 9), sharex=True,
                             gridspec_kw={"height_ratios": [2.2, 1, 1, 1, 1.3]})
    for ax, (ch, lab) in zip(axes, panels):
        _shade_corners(ax, corners, label=(ax is axes[0]))
        ax.plot(ref["Distance"], ref[ch], color=BLUE, label=ref_label)
        ax.plot(comp["Distance"], comp[ch], color=ORANGE, label=comp_label)
        ax.set_ylabel(lab)
    axes[0].legend(loc="lower right", ncols=2, fontsize=8)
    ax = axes[-1]
    _shade_corners(ax, corners)
    ax.axhline(0, color=INK_2, lw=0.8)
    ax.fill_between(ref["Distance"], delta, 0, where=delta >= 0, color=CRITICAL, alpha=0.25, lw=0)
    ax.fill_between(ref["Distance"], delta, 0, where=delta < 0, color=BLUE, alpha=0.25, lw=0)
    ax.plot(ref["Distance"], delta, color=INK, lw=1.2)
    ax.set_ylabel("Delta (s)")
    ax.set_xlabel("Distance (m)")
    ax.set_xlim(0, ref["Distance"].iloc[-1])
    _save(fig, path, "Best lap comparison",
          f"{ref_label} (blue) against {comp_label} (orange), aligned on distance. "
          f"Delta above 0 = {comp_label} behind ({delta[-1]:+.3f} s at the line)")


# ---------------------------------------------------------------- 3. track maps
def plot_track_maps(ref, comp, corners, spins, path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5.2))
    speed = ref["Ground Speed"].to_numpy()
    norm = plt.Normalize(speed.min(), speed.max())
    lc = _track_line(ax1, ref["Car Coord X"], ref["Car Coord Y"], speed, SEQ_BLUE, norm)
    cb = fig.colorbar(lc, ax=ax1, shrink=0.6, pad=0.02)
    cb.set_label("Speed (km/h)", color=INK_2)
    cb.outline.set_visible(False)
    _label_corners_on_map(ax1, corners)
    ax1.plot(ref["Car Coord X"].iloc[0], ref["Car Coord Y"].iloc[0], marker="s", color=INK, ms=6)
    ax1.annotate("S/F", (ref["Car Coord X"].iloc[0], ref["Car Coord Y"].iloc[0]), xytext=(6, -10),
                 textcoords="offset points", fontsize=8, color=INK_2)
    ax1.set_title("Speed on the reference lap")

    # rate of time loss: derivative of the delta, smoothed over 25 m
    delta = A.delta_time(ref, comp)
    rate = np.gradient(delta, ref["Distance"]) * 100      # seconds per 100 m
    rate = np.convolve(rate, np.ones(25) / 25, mode="same")
    lim = np.percentile(np.abs(rate), 98)
    lc2 = _track_line(ax2, ref["Car Coord X"], ref["Car Coord Y"], rate, DIVERGING,
                      TwoSlopeNorm(0, -lim, lim))
    cb2 = fig.colorbar(lc2, ax=ax2, shrink=0.6, pad=0.02)
    cb2.set_label("Time lost by comparison lap (s / 100 m)", color=INK_2)
    cb2.outline.set_visible(False)
    _label_corners_on_map(ax2, corners)
    if len(spins):
        ax2.plot(spins["X"], spins["Y"], "X", color=CRITICAL, ms=10, mec=SURFACE, mew=1.2,
                 label=f"spin locations ({len(spins)})")
        ax2.legend(loc="lower left", fontsize=8)
    ax2.set_title("Where the comparison lap loses (red) or gains (blue)")
    _save(fig, path, "Track map")


# ---------------------------------------------------------------- 4. corner delta
def plot_corner_delta(corner_delta: pd.DataFrame, comp_label, ref_label, path):
    fig, ax = plt.subplots(figsize=(8, 3.4))
    colors = [CRITICAL if d > 0 else BLUE for d in corner_delta["Delta_s"]]
    ax.bar(corner_delta["Corner"], corner_delta["Delta_s"], color=colors, width=0.6)
    for i, d in enumerate(corner_delta["Delta_s"]):
        ax.text(i, d + (0.004 if d >= 0 else -0.004), f"{d:+.3f}", ha="center",
                va="bottom" if d >= 0 else "top", fontsize=8, color=INK)
    ax.axhline(0, color=INK_2, lw=0.8)
    ax.set_ylabel("Time lost (s)")
    lim = corner_delta["Delta_s"].abs().max() * 1.35
    ax.set_ylim(-lim, lim)
    ax.grid(axis="x", visible=False)
    _save(fig, path, "Time lost per corner",
          f"{comp_label} vs {ref_label}: above 0 = slower. Total {corner_delta['Delta_s'].sum():+.3f} s")


# ---------------------------------------------------------------- 5. braking consistency
def plot_braking(brakes: pd.DataFrame, path):
    """Brake point and minimum speed of every clean lap, per braking zone."""
    zones = sorted(brakes["Corner"].unique(), key=lambda c: int(c[1:]))
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, col, lab in [(axes[0], "BrakePoint_m", "Brake point (m from zone average)"),
                         (axes[1], "MinSpeed_kmh", "Minimum speed (km/h from zone average)")]:
        for i, z in enumerate(zones):
            zb = brakes[brakes["Corner"] == z]
            centred = zb[col] - zb[col].mean()
            for stint, g in zb.groupby("Stint"):
                jitter = (np.arange(len(g)) - (len(g) - 1) / 2) * 0.06
                ax.scatter(i + jitter + (-0.12 if stint == "Stint 1" else 0.12), centred[g.index],
                           s=40, color=STINT_COLORS[stint], edgecolor=SURFACE, lw=1, zorder=3,
                           label=stint if i == 0 else None)
            unit = "m" if col == "BrakePoint_m" else "km/h"
            ax.text(i, 1.01, f"spread {zb[col].max() - zb[col].min():.0f} {unit}", transform=ax.get_xaxis_transform(),
                    ha="center", va="bottom", fontsize=8, color=INK_2)
        ax.axhline(0, color=INK_2, lw=0.8)
        ax.set_xticks(range(len(zones)), zones)
        ax.set_ylabel(lab)
        ax.grid(axis="x", visible=False)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncols=2, fontsize=8,
               bbox_to_anchor=(0.5, -0.06))
    _save(fig, path, "Braking consistency",
          "Each dot is one clean lap, centred on the zone average. Positive brake point = later braking")


# ---------------------------------------------------------------- 6. g-g diagram
def plot_gg(ax_g, ay_g, envelope, path):
    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    ax.scatter(ay_g, ax_g, s=3, color=BLUE, alpha=0.25, lw=0)
    env = pd.concat([envelope, envelope.iloc[:1]])
    ax.plot(env["ay"], env["ax"], color=INK, lw=1.4, label="98th percentile envelope")
    ax.axhline(0, color=INK_2, lw=0.6)
    ax.axvline(0, color=INK_2, lw=0.6)
    ax.set_aspect("equal")
    lim = 3.0
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_xlabel("Lateral acceleration (g)")
    ax.set_ylabel("Longitudinal acceleration (g)")
    ax.text(0, 2.2, "traction", ha="center", fontsize=8, color=INK_2)
    ax.text(0, -2.85, "braking", ha="center", fontsize=8, color=INK_2)
    ax.legend(loc="upper right", fontsize=8)
    _save(fig, path, "g-g diagram", "All clean laps, both stints")


# ---------------------------------------------------------------- 7. tyre temperatures
def plot_tyre_temps(summary: pd.DataFrame, path):
    """Inner / middle / outer temperatures drawn as a heat strip on each tyre."""
    fig, axes = plt.subplots(2, 2, figsize=(8, 5), gridspec_kw={"hspace": 0.55, "wspace": 0.12})
    layout = {"FL": axes[0, 0], "FR": axes[0, 1], "RL": axes[1, 0], "RR": axes[1, 1]}
    t_min, t_max = 55, 90
    for _, r in summary.iterrows():
        ax = layout[r["Tyre"]]
        # seen from behind the car: the inner edge of every tyre faces the centreline
        if r["Tyre"] in ("FL", "RL"):
            labels, vals = ["Outer", "Middle", "Inner"], [r["Outer_C"], r["Middle_C"], r["Inner_C"]]
        else:
            labels, vals = ["Inner", "Middle", "Outer"], [r["Inner_C"], r["Middle_C"], r["Outer_C"]]
        for i, (lab, v) in enumerate(zip(labels, vals)):
            shade = SEQ_BLUE((v - t_min) / (t_max - t_min))
            ax.add_patch(plt.Rectangle((i + 0.03, 0), 0.94, 1, color=shade, lw=0))
            ink = SURFACE if v > 72 else INK
            ax.text(i + 0.5, 0.55, f"{v:.0f} °C", ha="center", va="center", fontsize=11,
                    fontweight="bold", color=ink)
            ax.text(i + 0.5, 0.25, lab, ha="center", va="center", fontsize=8, color=ink)
        ax.set_xlim(0, 3)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.set_title(r["Tyre"], fontsize=10)
        ax.text(0, -0.08, f"core {r['Core_C']:.0f} °C   ·   {r['Pressure_psi']:.1f} psi   ·   "
                f"inner − outer {r['InnerMinusOuter_C']:+.0f} °C", transform=ax.transAxes,
                ha="left", va="top", fontsize=8, color=INK_2)
    _save(fig, path, "Tyre surface temperatures",
          "Stint 1, clean laps, mean of the samples above 60 km/h. Seen from behind the car")


def plot_tyre_evolution(evo: pd.DataFrame, path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.6))
    colors = {"FL": BLUE, "FR": "#1baf7a", "RL": ORANGE, "RR": "#6250d6"}
    for c, col in colors.items():
        ax1.plot(evo["Lap"], evo[f"Core {c}"], "o-", color=col, ms=4, label=c)
        ax2.plot(evo["Lap"], evo[f"Pressure {c}"], "o-", color=col, ms=4, label=c)
        ax1.text(evo["Lap"].iloc[-1] + 0.15, evo[f"Core {c}"].iloc[-1], c, va="center", fontsize=8, color=INK)
        ax2.text(evo["Lap"].iloc[-1] + 0.15, evo[f"Pressure {c}"].iloc[-1], c, va="center", fontsize=8, color=INK)
    ax1.set_ylabel("Core temperature (°C)")
    ax2.set_ylabel("Pressure (psi)")
    for ax in (ax1, ax2):
        ax.set_xlabel("Lap")
        ax.set_xticks(evo["Lap"])
    ax1.legend(ncols=4, fontsize=8, loc="upper left")
    _save(fig, path, "Tyre warm-up over Stint 1", "Mean per lap (lap 0 = out-lap)")


# ---------------------------------------------------------------- 8. ride height
def plot_ride_height(straight: pd.DataFrame, path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.8))
    v = straight["Ground Speed"]
    for ch, col, lab in [("Ride Height FL", BLUE, "Front"), ("Ride Height RL", ORANGE, "Rear")]:
        ax1.scatter(v, straight[ch], s=4, color=col, alpha=0.3, lw=0)
        fit = np.polyfit(v, straight[ch], 2)
        vv = np.linspace(v.min(), v.max(), 50)
        ax1.plot(vv, np.polyval(fit, vv), color=col, lw=2, label=f"{lab}: {np.polyval(fit, vv[0]):.1f} → "
                                                               f"{np.polyval(fit, vv[-1]):.1f} mm")
    ax1.set_xlabel("Speed (km/h)")
    ax1.set_ylabel("Ride height (mm)")
    ax1.legend(fontsize=8)
    ax1.set_title("Ride height on the straights")
    rake = straight["Ride Height RL"] - straight["Ride Height FL"]
    ax2.scatter(v, rake, s=4, color=INK_2, alpha=0.3, lw=0)
    fit = np.polyfit(v, rake, 1)
    vv = np.linspace(v.min(), v.max(), 50)
    ax2.plot(vv, np.polyval(fit, vv), color=INK, lw=2)
    ax2.set_xlabel("Speed (km/h)")
    ax2.set_ylabel("Rake, rear − front (mm)")
    ax2.set_title("Rake")
    _save(fig, path, "Aero platform", "Full throttle, no brake, |lateral g| < 0.3, clean laps of Stint 1")


# ---------------------------------------------------------------- 9. T2 spins
def plot_spin_analysis(clean_laps: dict, spin_laps: dict, window, path):
    """Overlay of every clean and every spinning lap through the T2 entry."""
    chans = [("Ground Speed", "Speed (km/h)"), ("Brake Pos", "Brake (%)"),
             ("Steering Angle", "Steering (deg)"), ("RearSlipRatio", "Rear slip\nratio (%)"),
             ("Chassis Yaw Rate", "Yaw rate (deg/s)"),
             ("RearMinusFrontSlip", "Rear − front\nslip angle (deg)")]
    fig, axes = plt.subplots(len(chans), 1, figsize=(9, 10.5), sharex=True)
    for ax, (ch, lab) in zip(axes, chans):
        for name, lap in clean_laps.items():
            w = lap[lap["Distance"].between(*window)]
            ax.plot(w["Distance"], w[ch], color=BLUE, lw=1, alpha=0.6)
        for name, lap in spin_laps.items():
            w = lap[lap["Distance"].between(*window)]
            ax.plot(w["Distance"], w[ch], color=CRITICAL, lw=1.4)
        ax.set_ylabel(lab)
    axes[2].set_ylim(-60, 110)
    axes[3].set_ylim(-60, 5)
    axes[4].set_ylim(-40, 110)
    axes[5].set_ylim(-10, 45)
    for ax in axes:
        ax.axvline(255, color=INK_2, lw=0.8, ls=(0, (2, 2)))
    axes[0].text(256, 0.05, "downshift to 2nd\n≈ 250–270 m", transform=axes[0].get_xaxis_transform(),
                 fontsize=8, color=INK_2, va="bottom")
    axes[0].plot([], [], color=BLUE, label=f"clean laps ({len(clean_laps)})")
    axes[0].plot([], [], color=CRITICAL, label=f"laps with a spin ({len(spin_laps)})")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[-1].set_xlabel("Distance (m)")
    _save(fig, path, "T2 entry: clean laps vs spins",
          "From the end of T1 (left, flat out) to the T2 apex (right, 2nd gear)")


# ---------------------------------------------------------------- 10. T2 brake point vs time
def plot_t2_brake_vs_time(t2: pd.DataFrame, path):
    fig, ax = plt.subplots(figsize=(6.4, 4))
    for stint, g in t2.groupby("Stint"):
        ax.scatter(g["BrakePoint_m"], g["SegmentTime_s"], s=60, color=STINT_COLORS[stint],
                   edgecolor=SURFACE, lw=1.2, zorder=3, label=stint)
        for r in g.itertuples():
            ax.annotate(f"L{r.Lap}  {r.MinSpeed_kmh:.0f} km/h", (r.BrakePoint_m, r.SegmentTime_s),
                        xytext=(7, 0), textcoords="offset points", va="center", fontsize=8, color=INK_2)
    ax.set_xlabel("T2 brake point (m from the line)   later →")
    ax.set_ylabel("Time in the T2 segment (s)")
    ax.legend(fontsize=8, loc="upper left")
    _save(fig, path, "T2: braking later did not pay",
          f"Clean laps only (n = {len(t2)}). Labels: lap and minimum speed in T2")
