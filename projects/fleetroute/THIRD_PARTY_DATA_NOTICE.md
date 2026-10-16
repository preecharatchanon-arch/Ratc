# Third-party data and software notice

This supplement contains or references benchmark material derived from established public VRP/VRPTW instance families (Augerat/CVRPLIB, Solomon, and Gehring-Homberger) and road-network information derived from OpenStreetMap. Original source/provenance receipts are retained under `benchmark/extracted_parent/public_raw/` and the benchmark protocol.

The application source snapshot also vendors browser-side Leaflet and Chart.js assets together with their bundled license files under `app/source_snapshot/fleetroute_app/app/static/vendor/`.

Google OR-Tools is used as an external comparison baseline through the included runner source. The supplement does not present OR-Tools source code as project-authored code.

Users redistributing third-party benchmark data or map-derived data should comply with the applicable upstream terms and attribution requirements.

## External map services

- OSM raster basemaps: https://operations.osmfoundation.org/policies/tiles/ — interactive viewing only; visible attribution, valid browser Referer and normal HTTP caching are required. No bulk/offline tile downloading. The service is best effort, without an availability guarantee.
- Geofabrik PBF extracts: https://download.geofabrik.de/ — road data, separate from raster tiles; OSM data remains under ODbL.
- Existing place search uses public Nominatim: https://operations.osmfoundation.org/policies/nominatim/ — explicit user searches only, cached responses and a serialized 1.05-second default interval per server process. Configure a suitable provider for commercial/scaled deployment; multiple independent runtimes do not share this limiter. Do not submit confidential addresses or personal data.
- Terrain imagery is provided by Esri World Topographic Map, with attribution shown on the map. Access to an endpoint is not an assurance of production service entitlement; deployment must comply with Esri's applicable terms.
