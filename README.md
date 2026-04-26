# HeatStop AI

HeatStop AI is a production-style MVP that ranks bus stops by heat-risk upgrade priority using only real public data and real user-supplied imagery. The default scope is Manhattan in New York City, with one or more selected bus corridors built from the official MTA feed. Each corridor is still intentionally capped to a small ordered stop set for demo clarity.

The system never fabricates stop rows, coordinates, images, heat values, or GTFS metrics. If a real source is missing, the app shows an empty state and tells you what to provide.

## Final architecture

### Backend

- `FastAPI` serves processed stop rankings, metadata, and GeoJSON.
- `app/ingest.py` downloads official data, builds one or more corridor stop sets, joins amenities, pulls NOAA/NWS heat metrics, and writes processed outputs plus a corridor registry.
- `app/weather.py` centralizes NWS weather fetches, weather metadata, and live corridor refresh summaries.
- `app/scoring.py` computes a transparent weighted HeatStop Priority Score and exposes a full score breakdown.
- `app/vision.py` runs lightweight OpenCV heuristics on real stop images only.
- `app/planner.py` generates planner-facing notes strictly from computed features.
- `app/llm.py` adds an optional LLM explanation layer with deterministic fallback when no provider key is configured.
- `app/vulnerability.py` fetches official NYC facility proxies for hospitals, senior services, and K-12 schools.
- `app/corridor_intelligence.py` runs a lightweight three-agent corridor reasoning workflow on top of real computed stop evidence.

### Frontend

- `Streamlit` provides a clean judge-friendly dashboard.
- `Folium` renders a color-coded route map.
- A ranked table and stop detail card show the score, image, computed features, score contributions, recommended intervention, and planner note.

### Data flow

1. Download official GTFS, shelter, seating, tree, and weather inputs.
2. Build one or more real corridor stop lists from GTFS.
3. Spatially join shelters, nearby seating, and nearby trees.
4. Optionally analyze real stop images from `data/raw/stop_images/`.
5. Score the stops with transparent weights.
6. Write `data/processed/stops_scored.csv` and `stops_scored.geojson`.
7. Serve the results through FastAPI and render them in Streamlit.
8. Optionally refresh corridor weather live in the dashboard without rebuilding the corridor.
9. Recompute scores from fresh NWS weather while preserving the existing spatial and image features.
10. Build corridor-level agent intelligence from the scored stop set, segment patterns, and vulnerability proxy joins.

## Exact real datasets used

### Default NYC MVP

1. `MTA Manhattan GTFS`
Source: http://web.mta.info/developers/data/nyct/bus/google_transit_manhattan.zip
Used for:
- stop locations
- route / direction filtering
- service-date filtering
- scheduled departure counts
- average scheduled headway per stop

2. `NYC DOT Bus Stop Shelters`
Source: https://data.cityofnewyork.us/api/views/t4f2-8md7/rows.csv?accessType=DOWNLOAD
Used for:
- spatial shelter presence proxy for each stop

3. `NYC DOT Seating Locations`
Source: https://data.cityofnewyork.us/resource/esmy-s8q5.csv
Used for:
- spatial nearby seating proxy for each stop

4. `NYC Street Tree Census`
Source: https://data.cityofnewyork.us/resource/uvpi-gqnh.csv
Used for:
- nearby tree count within a stop buffer
- nearby tree diameter sum as a simple canopy-strength proxy

5. `NOAA / NWS Gridpoint Forecast`
Source pattern: `https://api.weather.gov/points/{lat},{lon}` then `forecastGridData`
Used for:
- near-term maximum heat index, apparent temperature, or temperature
- normalized heat burden score

6. `NYC Facilities Database`
Source: https://data.cityofnewyork.us/resource/ji82-xba5.csv
Used for:
- hospital proximity proxy
- senior center proximity proxy
- K-12 school proximity proxy
- corridor-level vulnerability overlap findings

7. `MTA Bus Time / SIRI StopMonitoring`
Source: https://bustime.mta.info/wiki/Developers/SIRIStopMonitoring
Used for:
- real-time next bus ETA at the selected stop
- route / destination display
- expected arrival timestamp
- rider-facing heat-aware waiting guidance

8. `OpenStreetMap / Overpass API`
Source: https://overpass-api.de/
Used for:
- nearby cafes
- libraries
- community centers
- pharmacies
- parks / green spaces
- public restrooms
- drinking water points
- rider-facing safer nearby waiting suggestions

9. `Mapillary street-level imagery`
Source docs:
- https://help.mapillary.com/hc/en-us/articles/360010234680-Accessing-imagery-and-data-through-the-Mapillary-API
- https://www.mapillary.com/developer/api-documentation/
Used for:
- latest nearby public street-level stop image when no local file exists
- image download for UI display and OpenCV analysis
- capture date and source attribution

10. `Real stop images`
Source: local folder `data/raw/stop_images/`
Used for:
- visible tree ratio
- open-sky / direct sun proxy
- heuristic shelter estimate
- heuristic bench estimate

## Manual data required

The app only uses free, traceable imagery sources for stop photos:

- local real images in `data/raw/stop_images/`
- Mapillary public street-level imagery

If no reliable free geolocated image exists, the detail card will say `image unavailable`.

The dashboard includes a community-photo upload flow for image-missing stops when enabled. A user can upload a real stop-area photo directly from the stop detail panel, and the app stores it locally in `data/raw/stop_images/` with manifest metadata such as stop ID, uploader name, note, and upload timestamp.

Upload safety note:

- local filesystem storage is intended for local/demo use
- hosted deployments may lose these files unless persistent disk is configured
- feature flag: `HEATSTOP_ENABLE_COMMUNITY_UPLOADS=1` (set to `0` to disable upload UI)
- when a new community photo is uploaded for a stop, it becomes the preferred local image for that stop and is used by the visual analysis path
- visual analysis always runs OpenCV heuristics; pretrained detector signals are included only if `HEATSTOP_ENABLE_PRETRAINED_VISION=1`

Local files still take precedence over public imagery. To override the automatic fetcher, add real files to:

- `data/raw/stop_images/<stop_id>.jpg`
- or `data/raw/stop_images/manifest.csv` with `stop_id,file_name,source_url`

Do not add screenshots, mockups, or generated imagery.

Public imagery settings:

- `HEATSTOP_ENABLE_PUBLIC_IMAGERY=1`
- `HEATSTOP_PUBLIC_IMAGERY_RADIUS_M=35`
- `HEATSTOP_MAPILLARY_ACCESS_TOKEN=...`
- `HEATSTOP_USE_MAPILLARY_DEMO_TOKEN=1`

The default hackathon path uses the public demo token published in Mapillary's official `api-demo` repository when you do not provide your own token. For anything beyond a demo, replace it with your own Mapillary token.

Optional future expansion:

- geotagged Wikimedia Commons images may be added later if they are clearly matched to the exact stop area and preserve clear attribution metadata
- the current app does not use Google Street View, Google Images, random web search, or scraped blog/news/social photos

## Stable public deployment path

The repo now includes a hosted deployment path aimed at a persistent public URL instead of a temporary tunnel:

- `Dockerfile` packages the Streamlit UI and FastAPI backend together.
- `scripts/start_public.sh` starts FastAPI on `127.0.0.1:8000`, waits for it to become ready, and then serves Streamlit on the public port.
- `render.yaml` defines a Render Blueprint web service that can deploy this repo to a stable `onrender.com` URL.

Why this path:

- Render web services receive a public `onrender.com` subdomain and support custom domains.
- Render supports Docker-based services directly.
- Streamlit's Docker docs use `0.0.0.0` binding and the `/_stcore/health` endpoint, which matches the hosted setup here.

Official docs:

- https://render.com/docs/web-services
- https://render.com/docs/docker
- https://render.com/docs/blueprint-spec
- https://docs.streamlit.io/deploy/tutorials/docker

## HeatStop Priority Score

The score is interpretable and re-normalized only across features that are actually available for a stop.

Default weights:

- `0.35` no shelter
- `0.25` low tree cover
- `0.15` heat burden
- `0.15` wait burden
- `0.10` nearby seating gap

Feature definitions:

- `no shelter`: `1` if no shelter is found within the configured match radius
- `low tree cover`: `1 - combined_tree_cover_score`
- `heat burden`: normalized from the near-term NWS heat metric
- `wait burden`: normalized from scheduled GTFS headway
- `nearby seating gap`: `1` if no seating asset is found nearby

The score breakdown is saved per stop in `score_breakdown_json`.

## Live weather refresh

The dashboard includes a `Refresh Weather` button. It does not rebuild GTFS, shelters, trees, or imagery.

Instead, the app:

1. Loads the already-processed corridor from disk.
2. Fetches the latest real NWS gridpoint snapshot for the corridor centroid.
3. Updates the corridor-level weather fields.
4. Recomputes the weather-derived heat burden and final stop scores.
5. Returns the refreshed stop records to Streamlit without overwriting the saved corridor files.

Weather metadata exposed in the UI:

- source label: `NWS / weather.gov`
- source URL: live `forecastGridData` endpoint
- NWS update time
- app snapshot fetch time
- metric used: `heatIndex`, `apparentTemperature`, or `temperature`

The live refresh remains corridor-level by design.

## How the Corridor Intelligence panel works

The `Corridor Intelligence` panel is not a separate scoring model. It is a reasoning layer on top of the already computed stop scores and vulnerability joins.

Pipeline steps:

1. **Use scored stop rows already in memory**
   - The UI passes the active corridor stop table to `generate_corridor_intelligence(...)`.
   - If field-review display overrides are present for the selected view, the intelligence layer prefers `display_*` columns; otherwise it falls back to raw scored columns.

2. **Compute corridor evidence**
   - The app computes corridor-level aggregates such as:
     - unsheltered percentage
     - top-5 burden share
     - dominant score contributors
     - top segment by total burden
     - top burden stops with their action summaries
   - Segments are derived by ordering stops along the route and splitting into three route-position buckets, then labeled as southern/central/northern (or western/central/eastern) based on corridor orientation.

3. **Join vulnerability proxies**
   - Stops are enriched with nearby hospitals, senior centers, and schools.
   - A rule-based severity pass identifies where elevated stop risk overlaps with vulnerable uses under current heat conditions.

4. **Run three scoped agents (with strict schemas)**
   - **Corridor Analyst Agent** summarizes burden patterns.
   - **Vulnerability Agent** summarizes overlap findings and severity.
   - **Action Planning Agent** recommends intervention mix and priority segment.
   - Each agent only receives structured evidence and must return schema-constrained JSON.

5. **Fallback if no LLM output**
   - If provider keys are missing or generation fails, deterministic fallback logic builds the same sections from computed evidence.
   - The UI still renders and labels the source in `Reasoning`.

What this means in practice:

- `Unsheltered: 47%` and `Top 5 burden share: 52%` come from direct aggregate math on the corridor stop table.
- `Priority segment: Southern segment` comes from segment burden ranking.
- Bulleted stop lines in the vulnerability card come from enriched stop rows that met overlap thresholds.
- The planning memo is a synthesis over top stop actions + segment burden + vulnerability overlap count.

## Planner notes

Planner notes stay grounded in the transparent scoring system.

- The score remains the source of truth.
- The LLM never changes stop scores or factor weights.
- If `HEATSTOP_OPENAI_API_KEY` is missing or the LLM call fails, the app falls back to a deterministic planner note and labels it clearly as `Deterministic fallback`.

Current provider path:

- provider: `openai`
- default model: `gpt-4.1-mini`
- endpoint family: OpenAI Chat Completions API
- official docs: https://platform.openai.com/docs/api-reference/chat/create

Gemini is also supported for both stop-level planner notes and corridor-intelligence agents.

Gemini env example:

```bash
export HEATSTOP_LLM_PROVIDER=gemini
export HEATSTOP_GEMINI_API_KEY=your_key_here
export HEATSTOP_GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
export HEATSTOP_GEMINI_MODEL=gemini-2.0-flash
```

Official Gemini docs used for this integration:

- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/quota
- https://ai.google.dev/pricing

## Corridor Intelligence Agents

The dashboard now includes a corridor-level multi-step reasoning layer that sits on top of the stop scoring pipeline.

Important:

- the transparent stop score remains the source of truth
- the agents interpret existing real corridor evidence
- the agents do not invent stops, segments, vulnerability, or weather

### Agent workflow

1. `Corridor Analyst Agent`
- inputs:
  - stop order (`stop_sequence` / `route_rank`)
  - display-adjusted stop scores
  - risk categories
  - shelter / tree / seating / wait / heat features
  - top contributing factors
- outputs:
  - corridor summary
  - dominant drivers
  - top risk segment
  - signature insight
  - severity label

2. `Vulnerability Agent`
- inputs:
  - stop scores
  - stop locations
  - proximity to hospitals, senior services, and K-12 schools from the NYC Facilities Database
  - weather snapshot
  - corridor segment context
- outputs:
  - critical overlap findings
  - vulnerable segment summary
  - severity label

3. `Action Planning Agent`
- inputs:
  - Corridor Analyst output
  - Vulnerability Agent output
  - top stop actions already computed from the score pipeline
- outputs:
  - top corridor actions
  - priority segment
  - intervention mix
  - short planner memo

### Deterministic fallback

If no OpenAI key is configured, the app still runs the same three-step workflow with deterministic reasoning:

- corridor aggregates:
  - `% unsheltered stops`
  - top 5 burden share
  - segment burden comparison
  - dominant corridor drivers
- vulnerability overlap counts:
  - stops near hospitals
  - stops near senior services
  - stops near schools
  - high heat + high vulnerability escalation checks
- action planning from the existing intervention mix and top segment

The UI shape stays the same whether the reasoning source is OpenAI or deterministic fallback.

## Nearby Relief Copilot

The dashboard now includes a rider-facing `Nearby Relief Copilot` section. It is separate from the city-planning panels and uses the selected stop plus live waiting context to answer:

- should I stay near this stop?
- is there a safer nearby place to wait?
- is there a lower-exposure nearby stop on the same corridor?

The copilot combines:

1. the selected stop’s current HeatStop risk
2. real-time MTA stop arrivals when available
3. nearby relief places from OpenStreetMap / Overpass
4. nearby lower-risk stop candidates from the existing corridor score output

Important:

- the deterministic waiting logic is the source of truth
- the optional LLM layer only explains that grounded recommendation
- if real-time ETA or nearby-place lookup fails, the UI falls back cleanly to stop risk guidance

## Computer vision approach

By default, the MVP runs lightweight, explainable OpenCV heuristics (deployment-safe baseline):

- green HSV mask -> visible tree ratio
- upper-frame sky / bright mask -> open-sky ratio
- top-frame horizontal line density -> shelter estimate
- lower-frame horizontal line density -> bench estimate

Optional pretrained detector:

- disabled by default: `HEATSTOP_ENABLE_PRETRAINED_VISION=0`
- enable explicitly only when your environment can support model downloads/inference:
  - `HEATSTOP_ENABLE_PRETRAINED_VISION=1`
  - `HEATSTOP_PRETRAINED_VISION_MODEL=google/owlvit-base-patch32`

Limitations:

- these are heuristics, not audited object detectors
- shelter and bench estimates can be noisy
- official shelter and seating datasets remain the primary scoring inputs
- image-derived values are supplementary and never fabricated when images are missing
- public web imagery is selected as the latest nearby street-level image, not guaranteed to be centered perfectly on the bus stop pole

## Project structure

```text
app/
data/raw/
data/processed/
models/
notebooks/
scripts/
ui/
README.md
requirements.txt
.env.example
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional LLM env vars:

```bash
export HEATSTOP_LLM_PROVIDER=openai
export HEATSTOP_OPENAI_API_KEY=your_key_here
export HEATSTOP_OPENAI_BASE_URL=https://api.openai.com/v1
export HEATSTOP_LLM_MODEL=gpt-4.1-mini
export HEATSTOP_GEMINI_API_KEY=
export HEATSTOP_GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
export HEATSTOP_GEMINI_MODEL=gemini-2.0-flash
export HEATSTOP_MTA_BUS_TIME_API_KEY=
export HEATSTOP_MTA_BUS_TIME_BASE_URL=https://bustime.mta.info/api/siri/stop-monitoring.json
export HEATSTOP_RELIEF_PLACES_BASE_URL=https://overpass-api.de/api/interpreter
export HEATSTOP_RELIEF_SEARCH_RADIUS_M=400
export HEATSTOP_RELIEF_MAX_RESULTS=8
export HEATSTOP_RIDER_WALKING_SPEED_M_PER_MIN=80
export HEATSTOP_LOWER_RISK_STOP_RADIUS_M=500
export HEATSTOP_LOWER_RISK_STOP_MIN_RISK_DROP=12
```

Deployment-safety env vars:

```bash
export HEATSTOP_ENABLE_PRETRAINED_VISION=0
export HEATSTOP_ENABLE_COMMUNITY_UPLOADS=1
export HEATSTOP_CORS_ALLOW_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
export HEATSTOP_CORS_ALLOW_CREDENTIALS=0
```

Notes:

- CORS defaults to local Streamlit origins instead of `*`.
- Community uploads write to local disk and may not persist on ephemeral hosting unless persistent storage is configured.

## Build the real dataset

Single corridor:

```bash
python scripts/build_demo_data.py --route M15 --direction 0 --stop-limit 20
```

Multiple corridors in one build:

```bash
python scripts/build_demo_data.py --corridors 'M15:0,M15-SBS:0,M101:0' --stop-limit 15
```

Other examples:

```bash
python scripts/build_demo_data.py --route M15 --direction 1 --stop-limit 20
python scripts/build_demo_data.py --route M15-SBS --direction 0 --stop-limit 20
```

Outputs:

- `data/processed/stops_scored.csv`
- `data/processed/stops_scored.geojson`
- `data/processed/build_meta.json`
- `data/processed/corridors/<corridor_id>/...`
- `data/processed/corridors_index.json`

## Run locally

Terminal 1:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2:

```bash
streamlit run ui/dashboard.py
```

Then open:

- Dashboard: `http://localhost:8501`
- API docs: `http://localhost:8000/docs`

In the dashboard:

1. Choose a corridor.
2. Click `Refresh Weather`.
3. Wait for the live NWS snapshot and rescored corridor results.
4. Inspect a stop to see the updated note source, observed conditions, risk drivers, and refreshed weather metadata.
5. Use `Nearby Relief Copilot` to fetch:
- the next live bus arrival
- nearby safer places to wait
- a lower-risk nearby stop candidate when one is practical
6. Ask the copilot a rider question such as `Should I stay here or wait somewhere cooler?`

Single-process local run that matches production:

```bash
./scripts/start_public.sh
```

Optional local rebuild before startup:

```bash
HEATSTOP_BUILD_ON_START=1 HEATSTOP_BOOT_CORRIDORS='M15:0,M15-SBS:0,M101:0' ./scripts/start_public.sh
```

## Deploy on Render

1. Push this repo to GitHub, GitLab, or Bitbucket.
2. Make sure the repo includes the demo-ready artifacts you want served:
- `data/processed/`
- `data/raw/stop_images/`
3. In Render, create a new Blueprint or Web Service from the repo.
4. Use the included `render.yaml` or point Render at the repo's root `Dockerfile`.
5. Keep the default `HEATSTOP_BUILD_ON_START=0` for the fastest and most stable startup.
6. Optionally set `HEATSTOP_MAPILLARY_ACCESS_TOKEN` in Render for your own Mapillary quota.
7. After deploy, Render will give the app a stable `https://<service>.onrender.com` URL. You can later attach a custom domain from the Render dashboard.

Current `render.yaml` safety defaults:

- `HEATSTOP_ENABLE_PRETRAINED_VISION=0` (heuristic-only baseline)
- `HEATSTOP_ENABLE_COMMUNITY_UPLOADS=0` (upload UI hidden unless explicitly enabled)
- `HEATSTOP_CORS_ALLOW_ORIGINS` is explicitly set instead of wildcard CORS

Notes:

- The default Blueprint uses the `starter` plan because it is more stable than a sleeping free service for live demos.
- If you prefer to rebuild data during deploy/startup, set `HEATSTOP_BUILD_ON_START=1`. This is slower and depends on the upstream public datasets being reachable at boot time.
- Because Streamlit is the public process, the health check path is `/_stcore/health`.

## API endpoints

- `GET /health`
- `GET /corridors`
- `GET /meta`
- `GET /stops`
- `GET /stops/{stop_id}`
- `GET /stops/{stop_id}/rider-support`
- `POST /weather/refresh`
- `GET /geojson`

## Places where real data still must be supplied manually

1. `Stop imagery`
Reason: local images are optional, but still best if you want stop-specific framing.
Action: place real images in `data/raw/stop_images/`.

2. `Alternative city support`
Reason: this MVP is intentionally scoped to NYC for hackathon feasibility.
Action: swap the source URLs and field mappings in `app/ingest.py` and `app/data_sources.py`.

3. `LLM provider key`
Reason: the repo now supports a real LLM planner-note layer, but it is optional.
Action: set `HEATSTOP_OPENAI_API_KEY` if you want live LLM planner notes instead of deterministic fallback notes.

4. `MTA Bus Time API key`
Reason: rider ETA guidance depends on the official live stop-monitoring feed.
Action: set `HEATSTOP_MTA_BUS_TIME_API_KEY` if you want real-time arrivals inside `Nearby Relief Copilot`.

## Engineering notes

- No synthetic rows or fake images are included.
- Missing data is left null, excluded from weighted scoring when appropriate, and surfaced in the UI.
- Each processed corridor is capped at 10-30 stops for demo clarity.
- The backend is simple enough for a hackathon but structured enough to extend cleanly.
