import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.providers.mta_bus import build_bus_waiting_point_sets, build_bus_waiting_points


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the HeatStop AI waiting-point resilience demo dataset from live public sources. Current adapter: NYC bus corridors."
    )
    parser.add_argument("--route", default=None, help="GTFS route_short_name or route_id. Default comes from env/config.")
    parser.add_argument(
        "--corridors",
        default=None,
        help="Comma-separated route:direction specs, for example `M15:0,M15:1,M15-SBS:0`.",
    )
    parser.add_argument("--direction", type=int, default=None, help="GTFS direction_id. Default comes from env/config.")
    parser.add_argument("--stop-limit", type=int, default=None, help="Maximum number of ordered demo waiting points (current adapter: bus stops).")
    parser.add_argument("--service-date", default=None, help="Service date in YYYY-MM-DD format.")
    parser.add_argument("--force-download", action="store_true", help="Redownload raw source files even if they already exist.")
    args = parser.parse_args()

    if args.corridors:
        corridor_specs: list[tuple[str, int]] = []
        for spec in args.corridors.split(","):
            route_short_name, direction = spec.rsplit(":", 1)
            corridor_specs.append((route_short_name.strip(), int(direction.strip())))
        outputs = build_bus_waiting_point_sets(
            corridor_specs=corridor_specs,
            stop_limit=args.stop_limit,
            service_date_value=args.service_date,
            force_download=args.force_download,
        )
        print(f"Built {len(outputs)} waiting-zone demo sets.")
        for corridor_id, df in outputs.items():
            route_short_name = str(df['route_short_name'].iloc[0]) if not df.empty else corridor_id
            direction_id = int(df['direction_id'].iloc[0]) if not df.empty else -1
            print(f"\n[{corridor_id}] {route_short_name} direction {direction_id}: {len(df)} scored waiting points")
            if not df.empty:
                top = df.loc[:, ["stop_id", "stop_name", "priority_score"]].head(3)
                print(top.to_string(index=False))
        return

    df = build_bus_waiting_points(
        route_short_name=args.route,
        direction_id=args.direction,
        stop_limit=args.stop_limit,
        service_date_value=args.service_date,
        force_download=args.force_download,
    )
    print(f"Built {len(df)} scored waiting points.")
    if not df.empty:
        top = df.loc[:, ["stop_id", "stop_name", "priority_score", "recommended_intervention"]].head(5)
        print(top.to_string(index=False))


if __name__ == "__main__":
    main()
