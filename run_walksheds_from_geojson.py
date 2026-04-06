# 5. This code builds a router to run walksheds and generates walkshed geojson files
import os
import json
import csv
import aiohttp
import requests
import time
import geopandas as gpd

tdei_auth_token = None
if os.getenv("TDEI_AUTH_TOKEN") is not None:
   tdei_auth_token = str(os.getenv("TDEI_AUTH_TOKEN")).replace("'", "")

base_url = "https://api.tdei.us"
if os.getenv("TDEI_BASE_URL") is not None:
   base_url = os.getenv("TDEI_BASE_URL")

tdei_username = None
if os.getenv("TDEI_USERNAME") is not None:
   tdei_username = str(os.getenv("TDEI_USERNAME")).replace("'", "")

tdei_password = None
if os.getenv("TDEI_PASSWORD") is not None:
   tdei_password = str(os.getenv("TDEI_PASSWORD")).replace("'", "")

if tdei_auth_token is None:
    credentials = {
        "username": tdei_username,
        "password": tdei_password
    }

    auth_url = str(base_url) + "/api/v1/authenticate"
    headers = {"Content-Type": "application/json"}
    auth_response = requests.post(auth_url, json=credentials, headers=headers)

    if auth_response.status_code == 200:
        tdei_auth_token = auth_response.json().get("access_token")
    else:
        print("Authentication failed:", auth_response.status_code, auth_response.text)
        exit()

if tdei_auth_token:
    print("Authentication successful.")
    headers = {"Authorization": f"Bearer {tdei_auth_token}"}

# Walkshed API (walkshed.tdei.us) requires Bearer auth on router + routing calls — not only query ?auth_token=
def walkshed_headers():
    return {"Authorization": f"Bearer {tdei_auth_token}"}

# Step 1: Build Router Function
BASE_PATH=os.path.join(os.getcwd(), "data")


def _request_router_build(auth_token, dataset_id, h):
    """POST-equivalent GET to walkshed build endpoint; returns parsed JSON or raises."""
    url = "https://walkshed.tdei.us/api/v1/router/build"
    params = {
        "turbo": 1,
        "auth_token": auth_token,
        "dataset_id": dataset_id,
        "extension_dataset_id": "None",
        "internal_extensions": "",
        "external_extensions": "",
    }
    response = requests.get(url, params=params, headers=h, timeout=120)
    response.raise_for_status()
    return response.json()


def build_router(auth_token, dataset_id):
    """
    Wait until the walkshed router is ready with *this* dataset_id loaded.

    Handles stale server state: if status is 'failed' or the loaded dataset_id
    doesn't match the folder name (e.g. still 'yakima' after you renamed to
    'yakima_city'), triggers a rebuild instead of waiting forever on 'failed'.
    """
    statusUrl = "https://walkshed.tdei.us/api/v1/router/status"
    h = walkshed_headers()

    while True:
        resp = requests.get(statusUrl, headers=h, timeout=60)
        try:
            status_json = resp.json()
        except ValueError:
            print(f"Router status: non-JSON response HTTP {resp.status_code}: {resp.text[:500]}")
            time.sleep(30)
            continue

        if os.getenv("WALKSHED_DEBUG_STATUS", "1") != "0":
            print(f"Router status response: {status_json}")

        if status_json and status_json.get("code") == "Unauthorized":
            print(
                "Walkshed router returned Unauthorized. Check TDEI token (use same credential "
                "that works for api.tdei.us), or ask TDEI if walkshed needs a separate scope."
            )
            exit(1)

        status = (status_json or {}).get("status")
        current_ds = (status_json or {}).get("dataset_id")

        # Success: ready and serving our dataset
        if status == "ready" and current_ds == dataset_id:
            print(f"Router is ready for dataset ID {dataset_id!r}.")
            return

        # Failed previous build or wrong dataset still loaded — rebuild for this folder's ID
        if status == "failed" or (status == "ready" and current_ds != dataset_id):
            reason = "last build failed" if status == "failed" else f"loaded {current_ds!r}, need {dataset_id!r}"
            print(f"Requesting router build ({reason})...")
            try:
                data = _request_router_build(auth_token, dataset_id, h)
                if data.get("code") == "Ok":
                    print("Router build initiated successfully.")
                else:
                    print(f"Unexpected response from router build: {data}")
                    exit(1)
            except requests.RequestException as e:
                print(f"Router build request failed: {e}")
                exit(1)
            except ValueError:
                print("Failed to parse JSON from router build response.")
                exit(1)
            time.sleep(30)
            continue

        # building / not ready yet
        print(
            f"Router status: {status!r}, dataset_id: {current_ds!r} "
            f"(want {dataset_id!r}). Waiting 30s..."
        )
        time.sleep(30)

# Step 2: Reachable Tree Class
class AccessMapTreeProcessingAlgorithmFromGeoJSON:
    def __init__(self, geojson_file_path, output_dir, csv_output_dir):
        self.geojson_file_path = geojson_file_path
        self.output_dir = output_dir
        self.csv_output_dir = csv_output_dir
        # TEMPORARY: pedestrian only — restore Manual Wheelchair entry when you want both profiles again.
        self.combined_edges_profiles = {
            "Unconstrained Pedestrian (Sidewalks Only)": {"type": "FeatureCollection", "features": []},
            "Manual Wheelchair": {"type": "FeatureCollection", "features": []},
        }
        self.metrics_by_profile = {}

    def calculate_unique_length(self, geojson_path):
        """Calculate total unique path length in meters (deduplicated by geometry)."""
        try:
            gdf = gpd.read_file(geojson_path)
            if gdf.crs is None:
                gdf.set_crs(epsg=4326, inplace=True)  # assume WGS84 if missing
            gdf = gdf.to_crs(epsg=3857)  # convert to meters

            # Dissolve overlapping geometries to remove duplicates
            merged = gdf.unary_union

            # Handle case: merged might be a MultiLineString or GeometryCollection
            if merged.geom_type == "GeometryCollection":
                lines = [geom for geom in merged.geoms if geom.geom_type.startswith("Line")]
                total_length_m = sum(line.length for line in lines)
            else:
                total_length_m = merged.length

            return total_length_m

        except Exception as e:
            print(f"Error computing unique length for {geojson_path}: {e}")
            return 0

    def fetch_with_retries(self, url, retries=3):
        h = walkshed_headers()
        for attempt in range(retries):
            try:
                response = requests.get(url, headers=h, timeout=120)
                if response.status_code == 200:
                    return response.json()
                print(
                    f"HTTP Error {response.status_code}, body={response.text[:500]}. "
                    f"Retrying... ({attempt + 1}/{retries})"
                )
            except Exception as e:
                print(f"Request failed: {e}. Retrying... ({attempt + 1}/{retries})")

            time.sleep(1)
            print(".", end="", flush=True)

        return None

    def reachable_tree(self, lon, lat, location_name, profile_name, params, stop_id="", agency=""):
        #print(f"Processing {location_name} ({lat}, {lon}) for {profile_name}")
        url = (
            'https://walkshed.tdei.us/api/v1/routing/reachable_tree/custom.json?'
            f'lon={lon}&lat={lat}&uphill={params["uphill"]}&downhill={params["downhill"]}'
            f'&avoidCurbs={params["avoidCurbs"]}&streetAvoidance={params["streetAvoidance"]}'
            f'&max_cost={params["max_cost"]}&reverse={params["reverse"]}'
        )
        data = self.fetch_with_retries(url)
        if not data or "edges" not in data:
            #print(f"No data returned for {profile_name} at {location_name}")
            return
        edge_features = data["edges"].get("features") or []
        for edge_feat in edge_features:
            props = edge_feat.setdefault("properties", {})
            props["stop_id"] = stop_id
            props["agency"] = agency
        self.combined_edges_profiles[profile_name]["features"].extend(edge_features)

    def calculate_metrics(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        features = data.get("features", [])
        if not features and "edges" in data:
            features = data["edges"].get("features", [])
        metrics = {
            "total_length": 0,
            "path_count": 0,
            "crossing_count": 0,
            "curb_count": 0,
            "marked_curbs": 0,
            "lowered_curbs": 0
        }
        for feature in features:
            properties = feature.get("properties", {})
            metrics["total_length"] += properties.get("length", 0)
            metrics["path_count"] += 1
            if properties.get("footway") == "crossing":
                metrics["crossing_count"] += 1
            if properties.get("curbramps") in {0, 1, 2}:
                metrics["marked_curbs"] += 1
                metrics["curb_count"] += 2
            if properties.get("curbramps") == 1:
                metrics["lowered_curbs"] += 1

        return metrics

    def processAlgorithm(self):
        # TEMPORARY: pedestrian only — add Manual Wheelchair back to match __init__.combined_edges_profiles.
        profiles = {
            "Unconstrained Pedestrian (Sidewalks Only)": {"uphill": 0.15, "downhill": 0.15, "avoidCurbs": 0, "streetAvoidance": 1, "max_cost": 600, "reverse": 0},
            "Manual Wheelchair": {"uphill": 0.083, "downhill": 0.083, "avoidCurbs": 1, "streetAvoidance": 1, "max_cost": 600, "reverse": 0}
        }

        jurisdiction_name = os.path.basename(self.geojson_file_path).split("_filtered_amenities.geojson")[0]

        tasks = []
        with open(self.geojson_file_path, 'r', encoding='utf-8') as geojsonfile:
            geojson_data = json.load(geojsonfile)
            processed_locations = 0

            for feature in geojson_data["features"]:
                try:
                    lon, lat = feature["geometry"]["coordinates"]
                    props = feature.get("properties") or {}
                    location_name = props.get("name", "Unknown")
                    stop_id = str(props.get("stop_id", "")).strip()
                    agency = str(props.get("agency", "")).strip()
                    for profile_name, params in profiles.items():
                        task = self.reachable_tree(
                            lon,
                            lat,
                            location_name,
                            profile_name,
                            params,
                            stop_id=stop_id,
                            agency=agency,
                        )
                        tasks.append(task)
                    processed_locations += 1
                except (KeyError, ValueError) as e:
                    print(f"Error processing feature: {e}")
                    exit(1)
                        
            print(f"Processed {processed_locations} locations.")

        for profile_name, edges_data in self.combined_edges_profiles.items():
            output_path = os.path.join(
                self.output_dir,
                f"{jurisdiction_name}_{profile_name.replace(' ', '_')}_combined_edges.geojson"
            )
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(edges_data, f, indent=4)

            # Calculate standard metrics
            metrics = self.calculate_metrics(output_path)

            # Compute unique total length (deduplicated)
            unique_length_m = self.calculate_unique_length(output_path)
            metrics["total_length"] = unique_length_m  # overwrite inflated value

            self.metrics_by_profile[profile_name] = {
                **metrics,
                **profiles[profile_name]
            }

        output_csv_path = os.path.join(self.csv_output_dir, f"{jurisdiction_name}_metrics.csv")
        with open(output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=["profile", "uphill", "downhill", "avoidCurbs", "streetAvoidance", "max_cost", "reverse", "total_length", "path_count", "crossing_count", "curb_count", "marked_curbs", "lowered_curbs"])
            writer.writeheader()
            for profile_name, metrics in self.metrics_by_profile.items():
                writer.writerow({"profile": profile_name, **metrics})

        print(f"Metrics saved to {output_csv_path}")

# Step 3: Master Runner Function
def process_single_city(base_path, dataset_id, auth_token):
    city_folder = os.path.join(base_path, dataset_id)
    poi_path = os.path.join(city_folder, "data", "pois")
    output_dir = os.path.join(city_folder, "data", "walkshed_geojson")
    csv_output_dir = os.path.join(city_folder, "data", "metrics")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(csv_output_dir, exist_ok=True)

    tasks = []
    for filename in os.listdir(poi_path):
        if filename.endswith("_filtered_amenities.geojson"):
            geojson_file_path = os.path.join(poi_path, filename)
            algorithm = AccessMapTreeProcessingAlgorithmFromGeoJSON(
                geojson_file_path, output_dir, csv_output_dir
            )
            tasks.append(algorithm.processAlgorithm())

def run_all_datasets():
    processed_file_path = os.path.join(BASE_PATH, "processed.txt")

    # Read processed datasets into a set
    if os.path.exists(processed_file_path):
        with open(processed_file_path, "r") as f:
            processed_datasets = set(line.strip() for line in f if line.strip())
    else:
        processed_datasets = set()

    for folder_name in os.listdir(BASE_PATH):
        dataset_path = os.path.join(BASE_PATH, folder_name)
        if not os.path.isdir(dataset_path) or folder_name.lower() == "reports":
            continue
            
        if not os.path.isdir(dataset_path):
            continue

        if folder_name in processed_datasets:
            print(f"Skipping already processed dataset: {folder_name}")
            continue

        # CHECK output_dir before doing anything else
        output_dir = os.path.join(dataset_path, "data", "walkshed_geojson")
        if os.path.exists(output_dir) and os.listdir(output_dir):
            print(f"Skipping {folder_name} because output_dir is not empty.")
            continue
            
        print(f"Starting processing for dataset: {folder_name}")
        
        # Step 1: Build the router
        build_router(tdei_auth_token, folder_name)

        time.sleep(2)

        # Step 2: Process the dataset
        process_single_city(BASE_PATH, folder_name, tdei_auth_token)

        # Log successful completion
        with open(processed_file_path, "a") as log_file:
            log_file.write(f"{folder_name}\n")

        print(f"Finished processing for dataset: {folder_name}\n")

run_all_datasets()
exit(0)