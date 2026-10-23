"""Lap comparison, corner, braking, grip, tyre and incident analysis."""
import numpy as np
import pandas as pd
from scipy.signal import find_peaks

CORNERS = ("FL", "FR", "RL", "RR")


# --------------------------------------------------------------------------
# Distance-based resampling and time delta
# --------------------------------------------------------------------------
def resample_lap(lap_df: pd.DataFrame, track_length: float, step: float = 1.0,
                 channels=None) -> pd.DataFrame:
    """Interpolate a lap on a regular distance grid (default: every metre).

    Two laps can only be compared point by point if they share the same x-axis.
    Time is not a good axis (a slower lap is longer), distance is.
    """
    if channels is None:
        channels = [c for c in lap_df.columns
                    if c not in ("Distance", "Stint") and pd.api.types.is_numeric_dtype(lap_df[c])]
    lap_df = lap_df[lap_df["Distance"].between(0, track_length)]
    # np.interp needs a strictly increasing x: drop samples where the car
    # did not move forward (standstill, or noise in the position signal).
    dist = lap_df["Distance"].to_numpy()
    keep = np.concatenate([[True], np.diff(dist) > 0])
    keep &= dist >= np.maximum.accumulate(dist)
    lap_df = lap_df[keep]

    grid = np.arange(0.0, track_length, step)
    out = {"Distance": grid}
    for c in channels:
        out[c] = np.interp(grid, lap_df["Distance"], lap_df[c])
    return pd.DataFrame(out)


def delta_time(reference: pd.DataFrame, comparison: pd.DataFrame) -> np.ndarray:
    """Time gained (<0) or lost (>0) by `comparison` versus `reference` along the lap.

    Both laps must be resampled on the same distance grid. "Lap Time" is the
    running lap timer, so the difference of the two timers at the same
    distance is the gap at that point of the track.
    """
    return comparison["Lap Time"].to_numpy() - reference["Lap Time"].to_numpy()


# --------------------------------------------------------------------------
# Corners and braking
# --------------------------------------------------------------------------
def detect_corners(ref: pd.DataFrame, min_lat_g: float = 0.6, min_length_m: float = 20.0,
                   merge_gap_m: float = 30.0) -> pd.DataFrame:
    """Find the corners of the track on a reference lap from lateral acceleration.

    A corner is a stretch where |lateral g| stays above `min_lat_g` for at
    least `min_length_m` with the same sign (same direction). Two stretches of
    the same direction separated by less than `merge_gap_m` are one corner.
    Lateral g works better than speed minima here: several corners of this
    track are taken flat out and show no speed minimum at all.

    Each corner also gets a segment (SegStart_m -> SegEnd_m). Segments cut the
    lap into consecutive pieces, with boundaries halfway between corners, and
    are used for the corner-by-corner time comparison.
    """
    dist = ref["Distance"].to_numpy()
    step = dist[1] - dist[0]
    # 15 m moving average: removes kerb strikes and sensor noise
    window = max(int(15 / step), 1)
    lat = np.convolve(ref["CG Accel Lateral"], np.ones(window) / window, mode="same")
    direction = np.where(lat > min_lat_g, 1, np.where(lat < -min_lat_g, -1, 0))

    # 1. contiguous stretches with the same non-zero direction
    stretches = []
    i = 0
    while i < len(direction):
        if direction[i] == 0:
            i += 1
            continue
        j = i
        while j < len(direction) and direction[j] == direction[i]:
            j += 1
        if (j - i) * step >= min_length_m:
            stretches.append([i, j - 1, direction[i]])
        i = j

    # 2. merge stretches of the same direction separated by a short gap
    merged = []
    for s in stretches:
        if merged and s[2] == merged[-1][2] and (s[0] - merged[-1][1]) * step < merge_gap_m:
            merged[-1][1] = s[1]
        else:
            merged.append(s)

    # 3. describe each corner
    speed = ref["Ground Speed"].to_numpy()
    corners = []
    for k, (i0, i1, sign) in enumerate(merged):
        apex = i0 + np.argmin(speed[i0:i1 + 1])
        corners.append({
            "Corner": f"T{k + 1}",
            # positive lateral g = left-hand corner in this export
            "Direction": "left" if sign > 0 else "right",
            "Start_m": dist[i0],
            "End_m": dist[i1],
            "Apex_m": dist[apex],
            "ApexSpeed_kmh": speed[apex],
            "PeakLatG": np.abs(lat[i0:i1 + 1]).max(),
            "X": ref["Car Coord X"].iloc[apex],
            "Y": ref["Car Coord Y"].iloc[apex],
        })
    corners = pd.DataFrame(corners)

    # 4. segments: boundaries halfway between the end of a corner and the start of the next
    bounds = [0.0]
    for k in range(len(corners) - 1):
        bounds.append((corners["End_m"].iloc[k] + corners["Start_m"].iloc[k + 1]) / 2)
    bounds.append(dist[-1])
    corners["SegStart_m"] = bounds[:-1]
    corners["SegEnd_m"] = bounds[1:]
    return corners


def corner_time_delta(ref: pd.DataFrame, comp: pd.DataFrame, corners: pd.DataFrame) -> pd.DataFrame:
    """Time gained or lost in each corner segment (comparison minus reference)."""
    delta = delta_time(ref, comp)
    dist = ref["Distance"].to_numpy()
    rows = []
    for _, c in corners.iterrows():
        i0 = np.searchsorted(dist, c["SegStart_m"])
        i1 = min(np.searchsorted(dist, c["SegEnd_m"]), len(dist) - 1)
        rows.append({"Corner": c["Corner"], "Delta_s": delta[i1] - delta[i0]})
    return pd.DataFrame(rows)


def segment_times(lap_res: pd.DataFrame, corners: pd.DataFrame) -> dict:
    """Time spent in each corner segment of one lap (seconds)."""
    t = lap_res["Lap Time"].to_numpy()
    dist = lap_res["Distance"].to_numpy()
    out = {}
    for _, c in corners.iterrows():
        i0 = np.searchsorted(dist, c["SegStart_m"])
        i1 = min(np.searchsorted(dist, c["SegEnd_m"]), len(dist) - 1)
        out[c["Corner"]] = t[i1] - t[i0]
    return out


def braking_zones(lap_res: pd.DataFrame, corners: pd.DataFrame, brake_on: float = 5.0,
                  min_peak: float = 20.0, min_length_m: float = 10.0) -> pd.DataFrame:
    """Every braking zone of a lap, with the corner it leads into.

    A braking zone is a continuous stretch with the brake pedal above
    `brake_on` %, at least `min_length_m` long and reaching `min_peak` %.
    It is assigned to the corner whose segment contains the minimum speed
    reached just after the zone (within 50 m of the release).
    """
    dist = lap_res["Distance"].to_numpy()
    step = dist[1] - dist[0]
    brake = lap_res["Brake Pos"].to_numpy()
    speed = lap_res["Ground Speed"].to_numpy()
    throttle = lap_res["Throttle Pos"].to_numpy()

    on = brake > brake_on
    # start and end indices of each run of True values
    edges = np.diff(np.concatenate([[0], on.astype(int), [0]]))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0] - 1

    rows = []
    for i0, i1 in zip(starts, ends):
        if (i1 - i0) * step < min_length_m or brake[i0:i1 + 1].max() < min_peak:
            continue
        search_end = min(i1 + int(50 / step), len(dist) - 1)
        i_min = i0 + np.argmin(speed[i0:search_end + 1])
        in_segment = (corners["SegStart_m"] <= dist[i_min]) & (corners["SegEnd_m"] > dist[i_min])
        corner = corners.loc[in_segment, "Corner"].iloc[0] if in_segment.any() else "?"
        after = np.where(throttle[i1:search_end + 1] > 20)[0]
        rows.append({
            "Corner": corner,
            "BrakePoint_m": dist[i0],
            "BrakeRelease_m": dist[i1],
            "EntrySpeed_kmh": speed[i0],
            "PeakBrake_pct": brake[i0:i1 + 1].max(),
            "MinSpeed_kmh": speed[i_min],
            "MinSpeedAt_m": dist[i_min],
            "ThrottlePickup_m": dist[i1 + after[0]] if len(after) else np.nan,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Grip: g-g diagram
# --------------------------------------------------------------------------
def gg_envelope(ax: np.ndarray, ay: np.ndarray, n_sectors: int = 36,
                percentile: float = 98.0) -> pd.DataFrame:
    """Outer envelope of a g-g diagram.

    The plane is cut into angular sectors; in each one the envelope radius is a
    high percentile of the combined acceleration (more robust than the max,
    which is often a kerb strike).
    """
    radius = np.hypot(ax, ay)
    angle = np.arctan2(ax, ay)
    edges = np.linspace(-np.pi, np.pi, n_sectors + 1)
    rows = []
    for a0, a1 in zip(edges[:-1], edges[1:]):
        in_sector = (angle >= a0) & (angle < a1)
        if in_sector.sum() >= 5:
            r = np.percentile(radius[in_sector], percentile)
            mid = (a0 + a1) / 2
            rows.append({"angle": mid, "r": r, "ay": r * np.cos(mid), "ax": r * np.sin(mid)})
    return pd.DataFrame(rows)


def grip_usage(ax: np.ndarray, ay: np.ndarray, envelope: pd.DataFrame) -> np.ndarray:
    """Combined acceleration as a fraction of the envelope in the same direction."""
    angle = np.arctan2(ax, ay)
    env_r = np.interp(angle, envelope["angle"], envelope["r"], period=2 * np.pi)
    return np.hypot(ax, ay) / env_r


# --------------------------------------------------------------------------
# Tyres and platform
# --------------------------------------------------------------------------
def tyre_temperature_summary(df: pd.DataFrame, min_speed: float = 60.0) -> pd.DataFrame:
    """Mean inner / middle / outer / core temperature and pressure for each tyre."""
    running = df[df["Ground Speed"] > min_speed]
    rows = []
    for c in CORNERS:
        inner = running[f"Tire Temp Inner {c}"].mean()
        middle = running[f"Tire Temp Middle {c}"].mean()
        outer = running[f"Tire Temp Outer {c}"].mean()
        rows.append({
            "Tyre": c,
            "Inner_C": inner, "Middle_C": middle, "Outer_C": outer,
            "Core_C": running[f"Tire Temp Core {c}"].mean(),
            "InnerMinusOuter_C": inner - outer,
            # > 0: middle hotter than the shoulders (over-inflated tendency)
            "MiddleMinusAvgEdges_C": middle - (inner + outer) / 2,
            "Pressure_psi": running[f"Tire Pressure {c}"].mean(),
        })
    return pd.DataFrame(rows)


def per_lap_tyre_evolution(df: pd.DataFrame) -> pd.DataFrame:
    """Mean pressure and core temperature of each tyre on each lap."""
    agg = {}
    for c in CORNERS:
        agg[f"Pressure {c}"] = (f"Tire Pressure {c}", "mean")
        agg[f"Core {c}"] = (f"Tire Temp Core {c}", "mean")
    return df.groupby(["Stint", "Lap"]).agg(**agg).reset_index()


# --------------------------------------------------------------------------
# Incident analysis
# --------------------------------------------------------------------------
def corner_entry_metrics(lap_res: pd.DataFrame, start_m: float, end_m: float) -> dict:
    """Driver inputs and car response through one corner entry window.

    Used to compare laps that went through a corner cleanly with laps that spun.
    """
    w = lap_res[lap_res["Distance"].between(start_m, end_m)]
    slip_front = (w["Tire Slip Angle FL"] + w["Tire Slip Angle FR"]) / 2
    slip_rear = (w["Tire Slip Angle RL"] + w["Tire Slip Angle RR"]) / 2
    brake = w["Brake Pos"].to_numpy()
    on = np.where(brake > 5)[0]
    return {
        "EntrySpeed_kmh": w["Ground Speed"].iloc[0],
        "BrakePoint_m": w["Distance"].iloc[on[0]] if len(on) else np.nan,
        "MeanBrake_pct": w["Brake Pos"].mean(),
        "MaxYawRate_degps": w["Chassis Yaw Rate"].abs().max(),
        "MaxRearMinusFrontSlip_deg": (slip_rear.abs() - slip_front.abs()).max(),
        "MaxSideslip_deg": w["Sideslip"].abs().max(),
        # most negative = rear wheels turning slowest relative to the ground (locking)
        "MinRearSlipRatio_pct": ((w["Tire Slip Ratio RL"] + w["Tire Slip Ratio RR"]) / 2).min(),
    }
