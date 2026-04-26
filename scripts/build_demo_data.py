import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingest import build_processed_dataset, build_processed_datasets


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the HeatStop AI MVP dataset from live public sources.")
    parser.add_argument("--route", default=None, help="GTFS route_short_name or route_id. Default comes from env/config.")
    parser.add_argument(
        "--corridors",
        default=None,
        help="Comma-separated route:direction specs, for example `M15:0,M15:1,M15-SBS:0`.",
    )
    parser.add_argument("--direction", type=int, default=None, help="GTFS direction_id. Default comes from env/config.")
    parser.add_argument("--stop-limit", type=int, default=None, help="Maximum number of ordered corridor stops.")
    parser.add_argument("--service-date", default=None, help="Service date in YYYY-MM-DD format.")
    parser.add_argument("--force-download", action="store_true", help="Redownload raw source files even if they already exist.")
    args = parser.parse_args()

    if args.corridors:
        corridor_specs: list[tuple[str, int]] = []
        for spec in args.corridors.split(","):
            route_short_name, direction = spec.rsplit(":", 1)
            corridor_specs.append((route_short_name.strip(), int(direction.strip())))
        outputs = build_processed_datasets(
            corridor_specs=corridor_specs,
            stop_limit=args.stop_limit,
            service_date_value=args.service_date,
            force_download=args.force_download,
        )
        print(f"Built {len(outputs)} corridors.")
        for corridor_id, df in outputs.items():
            route_short_name = str(df['route_short_name'].iloc[0]) if not df.empty else corridor_id
            direction_id = int(df['direction_id'].iloc[0]) if not df.empty else -1
            print(f"\n[{corridor_id}] {route_short_name} direction {direction_id}: {len(df)} scored stops")
            if not df.empty:
                top = df.loc[:, ["stop_id", "stop_name", "priority_score"]].head(3)
                print(top.to_string(index=False))
        return

    df = build_processed_dataset(
        route_short_name=args.route,
        direction_id=args.direction,
        stop_limit=args.stop_limit,
        service_date_value=args.service_date,
        force_download=args.force_download,
    )
    print(f"Built {len(df)} scored stops.")
    if not df.empty:
        top = df.loc[:, ["stop_id", "stop_name", "priority_score", "recommended_intervention"]].head(5)
        print(top.to_string(index=False))


if __name__ == "__main__":
    main()
