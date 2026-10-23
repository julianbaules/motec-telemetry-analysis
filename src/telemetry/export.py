"""Export of the processed, anonymised data that is published with the repository."""
import json
from pathlib import Path

import pandas as pd

DRIVER_ALIAS = "Driver A"

# Channels kept in the published CSV files (the .ld files hold 169).
EXPORT_CHANNELS = [
    "Time", "Stint", "Lap", "Distance", "LapPos", "Lap Time", "Last Lap Time",
    "Ground Speed", "Engine RPM", "Gear", "Throttle Pos", "Brake Pos", "Clutch Pos",
    "Steering Angle", "Brake Bias",
    "CG Accel Lateral", "CG Accel Longitudinal", "CG Accel Vertical",
    "Chassis Yaw Rate", "Chassis Roll Angle", "Chassis Pitch Angle",
    "Chassis Velocity X", "Chassis Velocity Y", "Sideslip",
    "Car Coord X", "Car Coord Y", "Car Coord Z",
    "Ride Height FL", "Ride Height RL",
    "Num Tires Off Track", "Fuel Level",
]
for corner in ("FL", "FR", "RL", "RR"):
    EXPORT_CHANNELS += [
        f"Suspension Travel {corner}", f"Tire Load {corner}",
        f"Tire Slip Angle {corner}", f"Tire Slip Ratio {corner}",
        f"Tire Pressure {corner}", f"Tire Temp Core {corner}",
        f"Tire Temp Inner {corner}", f"Tire Temp Middle {corner}", f"Tire Temp Outer {corner}",
        f"Brake Temp {corner}", f"Toe In {corner}",
    ]


def session_info(meta: dict, stint: str, track_length: float) -> dict:
    """Session metadata with the driver name replaced by an alias."""
    return {
        "stint": stint,
        "driver": DRIVER_ALIAS,
        "date": meta.get("date"),
        "simulator": meta.get("comment"),
        "vehicle": meta.get("vehicle_id"),
        "venue": meta.get("venue"),
        "session": meta.get("session"),
        "tyres": meta.get("short_comment"),
        "track_length_m": round(track_length, 1),
    }


def export_processed(sessions: dict, lap_tables: pd.DataFrame, infos: list, out_dir) -> None:
    """Write one CSV per lap, the lap table and the session metadata."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stint, df in sessions.items():
        stint_tag = stint.lower().replace(" ", "")
        for lap, lap_df in df.groupby("Lap"):
            lap_df[EXPORT_CHANNELS].round(4).to_csv(
                out_dir / f"{stint_tag}_lap{lap:02d}.csv", index=False)
    lap_tables.round(3).to_csv(out_dir / "laps.csv", index=False)
    with open(out_dir / "sessions.json", "w", encoding="utf-8") as f:
        json.dump(infos, f, indent=2)
