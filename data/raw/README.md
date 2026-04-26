`data/raw/` stores only real downloaded source files and real user-supplied imagery.

Expected contents after running the pipeline:

- `google_transit_manhattan.zip`
- `nyc_bus_stop_shelters.csv`
- `nyc_seating_locations.csv`
- `nyc_street_trees_<route>_<direction>.csv`
- `stop_images/`

`stop_images/` can contain:

- user-supplied real files named like `<stop_id>.jpg`
- or auto-downloaded public street-level images named like `mapillary_<stop_id>.jpg`

Do not place fabricated CSVs or placeholder rows here.
