"""Session preparation: lap splitting, lap distance and lap classification."""
import numpy as np
import pandas as pd

SAMPLE_RATE = 20  # Hz, every channel of these Assetto Corsa exports

# Thresholds used to flag an incident (spin or excursion)
SPIN_SIDESLIP_DEG = 15.0      # |body sideslip| above this, at speed, is a spin
SPIN_MIN_SPEED_KMH = 30.0
OFF_TRACK_WHEELS = 3          # 3 or 4 wheels off the track counts as an excursion


def prepare_session(df: pd.DataFrame, stint: str) -> pd.DataFrame:
    """Add the derived channels every analysis relies on.

    New columns:
        Stint        label of the stint ("Stint 1", ...)
        Lap          lap number (0 = out-lap)
        Gear         gear with the neutral samples of each shift filled in
        Sideslip     body sideslip angle beta in degrees
        LapPos       position along the lap, 0 -> 1, continuous within a lap
    """
    df = df.copy()
    df["Stint"] = stint
    df["Lap"] = df["Session Lap Count"].astype(int)

    # Gear reads 0 (neutral) for a few samples during each shift. Replace those
    # samples with the previous gear when the car is moving.
    gear = df["Gear"].where(~((df["Gear"] == 0) & (df["Ground Speed"] > 10)))
    df["Gear"] = gear.ffill().fillna(0).astype(int)

    # Body sideslip: angle between the car's heading and its velocity vector.
    df["Sideslip"] = np.degrees(np.arctan2(df["Chassis Velocity Y"], df["Chassis Velocity X"]))

    # "Car Pos Norm" is Assetto Corsa's position along the track spline (0 -> 1).
    # The out-lap starts just before the line (0.98...), so unwrap those values.
    pos = df["Car Pos Norm"].to_numpy().copy()
    for lap, idx in df.groupby("Lap").groups.items():
        lap_pos = pos[idx]
        start_before_line = lap_pos[: SAMPLE_RATE * 2] > 0.5
        lap_pos[: SAMPLE_RATE * 2][start_before_line] -= 1.0
        # the last sample of a lap can already read 1.0 or wrap to 0.0
        if len(lap_pos) > 10 and lap_pos[-1] < 0.5 and lap_pos[-10] > 0.9:
            lap_pos[-1] = 1.0
        pos[idx] = lap_pos
    df["LapPos"] = pos
    return df


def estimate_track_length(df: pd.DataFrame, clean_laps) -> float:
    """Track length in metres: median distance driven over clean laps."""
    lengths = []
    for lap in clean_laps:
        speed_ms = df.loc[df["Lap"] == lap, "Ground Speed"] / 3.6
        lengths.append(speed_ms.sum() / SAMPLE_RATE)
    return float(np.median(lengths))


def add_distance(df: pd.DataFrame, track_length: float) -> pd.DataFrame:
    """Distance from the start/finish line in metres, aligned between laps."""
    df = df.copy()
    df["Distance"] = df["LapPos"] * track_length
    return df


def lap_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per lap: lap time, status and a few summary values."""
    rows = []
    laps = sorted(df["Lap"].unique())
    for lap in laps:
        lap_df = df[df["Lap"] == lap]
        next_lap = df[df["Lap"] == lap + 1]

        # Official lap time: "Last Lap Time" right after the line is crossed.
        lap_time = next_lap["Last Lap Time"].iloc[0] if len(next_lap) else np.nan

        moving = lap_df["Ground Speed"] > SPIN_MIN_SPEED_KMH
        spin = (lap_df["Sideslip"].abs() > SPIN_SIDESLIP_DEG) & moving
        off_track = lap_df["Num Tires Off Track"] >= OFF_TRACK_WHEELS

        if lap == 0:
            status = "out-lap"
        elif np.isnan(lap_time):
            status = "incomplete"
        elif spin.any() or off_track.sum() > SAMPLE_RATE // 2:
            status = "incident"
        else:
            status = "clean"

        incident_pos = np.nan
        if spin.any():
            incident_pos = lap_df.loc[spin, "Distance"].iloc[0]

        rows.append({
            "Stint": lap_df["Stint"].iloc[0],
            "Lap": lap,
            "LapTime_s": lap_time,
            "Status": status,
            "Spin": bool(spin.any()),
            "IncidentDistance_m": incident_pos,
            "VMax_kmh": lap_df["Ground Speed"].max(),
            "FuelStart_l": lap_df["Fuel Level"].iloc[0],
        })
    table = pd.DataFrame(rows)
    clean = table[table["Status"] == "clean"]
    if len(clean):
        best = clean["LapTime_s"].min()
        table["GapToBest_s"] = table["LapTime_s"] - best
    return table


def best_clean_lap(table: pd.DataFrame) -> int:
    clean = table[table["Status"] == "clean"]
    return int(clean.loc[clean["LapTime_s"].idxmin(), "Lap"])
