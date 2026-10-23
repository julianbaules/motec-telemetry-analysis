"""Full pipeline: .ld files -> processed CSV -> tables -> figures.

Usage (from the repository root):
    python scripts/run_all.py              # reads data/raw/*.ld
    python scripts/run_all.py --from-csv   # reads the published CSV files instead
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from telemetry import analysis as A          # noqa: E402
from telemetry import laps as L              # noqa: E402
from telemetry import plotting as P          # noqa: E402
from telemetry.export import export_processed, session_info  # noqa: E402
from telemetry.ld_reader import read_ld      # noqa: E402

RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
FIGS = ROOT / "reports" / "figures"
TABLES = ROOT / "reports" / "tables"


def load_from_ld():
    """Read every .ld file, return {stint label: DataFrame} and the metadata."""
    sessions, metas = {}, {}
    for path in sorted(RAW.glob("*.ld")):
        match = re.search(r"stint_(\d+)", path.stem)
        stint = f"Stint {match.group(1)}" if match else path.stem
        ld = read_ld(path)
        sessions[stint] = L.prepare_session(ld.to_dataframe(), stint)
        metas[stint] = ld.meta
    if not sessions:
        sys.exit(f"No .ld file found in {RAW}. Use --from-csv to run on the published data.")
    return sessions, metas


def load_from_csv():
    """Rebuild the sessions from the published per-lap CSV files."""
    sessions = {}
    for path in sorted(PROCESSED.glob("stint*_lap*.csv")):
        lap_df = pd.read_csv(path)
        stint = lap_df["Stint"].iloc[0]
        sessions.setdefault(stint, []).append(lap_df)
    return {s: pd.concat(parts, ignore_index=True) for s, parts in sessions.items()}


def main(from_csv: bool):
    for d in (FIGS, TABLES):
        d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ 1. sessions
    if from_csv:
        sessions = load_from_csv()
        infos = json.loads((PROCESSED / "sessions.json").read_text())
        track_length = infos[0]["track_length_m"]
    else:
        sessions, metas = load_from_ld()
        # lap status needs a Distance column; a first pass with 0 is enough
        # to find the clean laps that give the track length
        lengths = []
        for df in sessions.values():
            table = L.lap_table(df.assign(Distance=0.0))
            clean = table.loc[table["Status"] == "clean", "Lap"]
            lengths += [L.estimate_track_length(df, [lap]) for lap in clean]
        track_length = float(np.median(lengths))
        sessions = {s: L.add_distance(df, track_length) for s, df in sessions.items()}
        infos = [session_info(metas[s], s, track_length) for s in sessions]

    lap_tables = pd.concat([L.lap_table(df) for df in sessions.values()], ignore_index=True)
    best_overall = lap_tables.loc[lap_tables["Status"] == "clean", "LapTime_s"].min()
    lap_tables["GapToBest_s"] = lap_tables["LapTime_s"] - best_overall
    if not from_csv:
        export_processed(sessions, lap_tables, infos, PROCESSED)
    lap_tables.round(3).to_csv(TABLES / "lap_times.csv", index=False)
    print(f"Track length: {track_length:.1f} m")
    print(lap_tables[["Stint", "Lap", "LapTime_s", "Status", "GapToBest_s"]].round(3).to_string(index=False))

    # ------------------------------------------------------------ 2. resampled laps
    def res(stint, lap):
        df = sessions[stint]
        r = A.resample_lap(df[df["Lap"] == lap], track_length)
        front = (r["Tire Slip Angle FL"] + r["Tire Slip Angle FR"]) / 2
        rear = (r["Tire Slip Angle RL"] + r["Tire Slip Angle RR"]) / 2
        r["RearMinusFrontSlip"] = rear.abs() - front.abs()
        r["RearSlipRatio"] = (r["Tire Slip Ratio RL"] + r["Tire Slip Ratio RR"]) / 2
        return r

    clean = lap_tables[lap_tables["Status"] == "clean"]
    stints = list(sessions)
    best = {s: L.best_clean_lap(lap_tables[lap_tables["Stint"] == s]) for s in stints}
    ref_stint = clean.loc[clean["LapTime_s"].idxmin(), "Stint"]
    comp_stint = next(s for s in stints if s != ref_stint)
    ref, comp = res(ref_stint, best[ref_stint]), res(comp_stint, best[comp_stint])
    ref_label = f"{ref_stint} lap {best[ref_stint]}"
    comp_label = f"{comp_stint} lap {best[comp_stint]}"

    # ------------------------------------------------------------ 3. corners and delta
    corners = A.detect_corners(ref)
    corner_delta = A.corner_time_delta(ref, comp, corners)
    corners.round(1).to_csv(TABLES / "corners.csv", index=False)
    corner_delta.round(3).to_csv(TABLES / "corner_delta.csv", index=False)
    print("\nCorners:\n", corners[["Corner", "Direction", "Start_m", "End_m", "ApexSpeed_kmh"]].round(0).to_string(index=False))
    print("\nTime lost per corner:\n", corner_delta.round(3).to_string(index=False))

    # ------------------------------------------------------------ 3b. ideal lap
    seg = pd.DataFrame({f"{r.Stint} L{r.Lap}": A.segment_times(res(r.Stint, r.Lap), corners)
                        for r in clean.itertuples()}).T
    gain = seg.loc[f"{ref_label.replace(' lap ', ' L')}"] - seg.min()
    ideal = pd.DataFrame({"BestSegment_s": seg.min(), "BestLap": seg.idxmin(),
                          "ReferenceLap_s": seg.loc[ref_label.replace(" lap ", " L")], "Gain_s": gain})
    seg.round(3).to_csv(TABLES / "segment_times.csv")
    ideal.round(3).to_csv(TABLES / "ideal_lap.csv")
    print(f"\nIdeal lap (best segments of all clean laps): {best_overall - gain.sum():.3f} s, "
          f"{gain.sum():.3f} s under the best lap")
    print(ideal.round(3).to_string())

    # ------------------------------------------------------------ 4. braking
    brakes = []
    for _, row in clean.iterrows():
        b = A.braking_zones(res(row["Stint"], row["Lap"]), corners)
        b.insert(0, "Lap", row["Lap"])
        b.insert(0, "Stint", row["Stint"])
        brakes.append(b)
    brakes = pd.concat(brakes, ignore_index=True)
    brakes.round(1).to_csv(TABLES / "braking_zones.csv", index=False)
    spread = brakes.groupby("Corner").agg(
        BrakePointSpread_m=("BrakePoint_m", lambda x: x.max() - x.min()),
        MinSpeedSpread_kmh=("MinSpeed_kmh", lambda x: x.max() - x.min()),
        MeanMinSpeed_kmh=("MinSpeed_kmh", "mean"))
    print("\nBraking consistency (clean laps):\n", spread.round(1).to_string())

    # ------------------------------------------------------------ 5. grip
    clean_raw = pd.concat([sessions[r["Stint"]][sessions[r["Stint"]]["Lap"] == r["Lap"]]
                           for _, r in clean.iterrows()])
    ax_g = clean_raw["CG Accel Longitudinal"].to_numpy()
    ay_g = clean_raw["CG Accel Lateral"].to_numpy()
    env = A.gg_envelope(ax_g, ay_g)
    usage = A.grip_usage(ax_g, ay_g, env)
    print(f"\ng-g: peak lateral {np.percentile(np.abs(ay_g), 99):.2f} g, "
          f"peak braking {-np.percentile(ax_g, 1):.2f} g, peak traction {np.percentile(ax_g, 99):.2f} g")
    print(f"Share of the lap above 90 % of the envelope: {(usage > 0.9).mean() * 100:.0f} %")

    # ------------------------------------------------------------ 6. tyres and platform
    s1 = sessions[stints[0]]
    s1_clean = s1[s1["Lap"].isin(clean.loc[clean["Stint"] == stints[0], "Lap"])]
    tyres = A.tyre_temperature_summary(s1_clean)
    evo = A.per_lap_tyre_evolution(s1[s1["Lap"] <= lap_tables.loc[lap_tables["Stint"] == stints[0], "Lap"].max() - 1])
    tyres.round(1).to_csv(TABLES / "tyres.csv", index=False)
    evo.round(2).to_csv(TABLES / "tyre_evolution.csv", index=False)
    print("\nTyres (Stint 1, clean laps):\n", tyres.round(1).to_string(index=False))

    straight = s1_clean[(s1_clean["CG Accel Lateral"].abs() < 0.3) & (s1_clean["Brake Pos"] < 1)
                        & (s1_clean["Throttle Pos"] > 95) & (s1_clean["Ground Speed"] > 90)]
    bottoming = s1_clean[s1_clean["Ride Height FL"] < 0]
    print(f"\nFront ride height below 0 mm on {len(bottoming)} samples, "
          f"around {bottoming['Distance'].median():.0f} m" if len(bottoming) else "\nNo bottoming")

    # ------------------------------------------------------------ 7. incidents at T2
    window = (150.0, 300.0)
    spin_rows = lap_tables[lap_tables["Spin"]]
    clean_laps = {f"{r.Stint} L{r.Lap}": res(r.Stint, r.Lap) for r in clean.itertuples()}
    spin_laps = {f"{r.Stint} L{r.Lap}": res(r.Stint, r.Lap) for r in spin_rows.itertuples()}
    entry = []
    for name, lap in {**clean_laps, **spin_laps}.items():
        m = A.corner_entry_metrics(lap, 180.0, 275.0)
        m["Lap"] = name
        m["Spin"] = name in spin_laps
        entry.append(m)
    entry = pd.DataFrame(entry).set_index("Lap")
    entry.round(1).to_csv(TABLES / "t2_entry.csv")
    print("\nT2 entry, clean vs spin:\n", entry.round(1).to_string())

    spins_xy = []
    for r in spin_rows.itertuples():
        df = sessions[r.Stint]
        lap = df[df["Lap"] == r.Lap]
        first = lap[(lap["Sideslip"].abs() > L.SPIN_SIDESLIP_DEG) & (lap["Ground Speed"] > L.SPIN_MIN_SPEED_KMH)].iloc[0]
        spins_xy.append({"Stint": r.Stint, "Lap": r.Lap, "Distance": first["Distance"],
                         "X": first["Car Coord X"], "Y": first["Car Coord Y"]})
    spins_xy = pd.DataFrame(spins_xy)
    print("\nSpin locations:\n", spins_xy.round(1).to_string(index=False))

    # ------------------------------------------------------------ 8. figures
    P.plot_lap_times(lap_tables, FIGS / "01_lap_times.png")
    P.plot_lap_comparison(ref, comp, ref_label, comp_label, corners, FIGS / "02_best_lap_comparison.png")
    P.plot_track_maps(ref, comp, corners, spins_xy, FIGS / "03_track_map.png")
    P.plot_corner_delta(corner_delta, comp_label, ref_label, FIGS / "04_corner_delta.png")
    P.plot_braking(brakes, FIGS / "05_braking_consistency.png")
    P.plot_gg(ax_g, ay_g, env, FIGS / "06_gg_diagram.png")
    P.plot_tyre_temps(tyres, FIGS / "07_tyre_temperatures.png")
    P.plot_tyre_evolution(evo, FIGS / "08_tyre_evolution.png")
    P.plot_ride_height(straight, FIGS / "09_ride_height.png")
    P.plot_spin_analysis(clean_laps, spin_laps, window, FIGS / "10_t2_spins.png")
    t2_brakes = brakes[brakes["Corner"] == "T2"].copy()
    t2_brakes["SegmentTime_s"] = [seg.loc[f"{r.Stint} L{r.Lap}", "T2"] for r in t2_brakes.itertuples()]
    P.plot_t2_brake_vs_time(t2_brakes, FIGS / "11_t2_brake_point.png")
    print(f"\nFigures written to {FIGS}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-csv", action="store_true", help="use data/processed instead of data/raw")
    main(parser.parse_args().from_csv)
