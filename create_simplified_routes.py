import csv
import os
from collections import defaultdict

def load_csv_as_dict(file_path):
    if not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        return None

def create_route_paths(agency_name, gtfs_base_path):
    agency_path = os.path.join(gtfs_base_path, agency_name)
    
    stops_file = os.path.join(agency_path, 'stops.txt')
    stop_times_file = os.path.join(agency_path, 'stop_times.txt')
    trips_file = os.path.join(agency_path, 'trips.txt')
    routes_file = os.path.join(agency_path, 'routes.txt')
    headway_file = os.path.join(agency_path, 'stop_headway_summary.csv')
    
    stops = load_csv_as_dict(stops_file)
    stop_times = load_csv_as_dict(stop_times_file)
    trips = load_csv_as_dict(trips_file)
    routes = load_csv_as_dict(routes_file)
    headway_summary = load_csv_as_dict(headway_file)
    
    if not stops or not stop_times or not trips:
        return []
    
    stop_coords = {}
    for stop in stops:
        stop_id = stop['stop_id']
        try:
            stop_coords[stop_id] = {
                'stop_lat': float(stop['stop_lat']),
                'stop_lon': float(stop['stop_lon']),
                'stop_name': stop.get('stop_name', ''),
                'peak_15min_weekday': 'NO',
                'day_15min_weekday': 'NO', 
                'night_60min_weekday': 'NO',
                'allday_60min_weekend': 'NO'
            }
        except (ValueError, KeyError):
            continue

    if headway_summary:
        for headway in headway_summary:
            stop_id = headway['stop_id']
            if stop_id in stop_coords:
                stop_coords[stop_id]['peak_15min_weekday'] = headway.get('peak_15min_weekday', 'NO')
                stop_coords[stop_id]['day_15min_weekday'] = headway.get('day_15min_weekday', 'NO')
                stop_coords[stop_id]['night_60min_weekday'] = headway.get('night_60min_weekday', 'NO')
                stop_coords[stop_id]['allday_60min_weekend'] = headway.get('allday_60min_weekend', 'NO')
    
    route_info = {}
    if routes:
        for route in routes:
            route_id = route['route_id']
            route_info[route_id] = {
                'route_short_name': route.get('route_short_name', ''),
                'route_long_name': route.get('route_long_name', ''),
                'route_type': route.get('route_type', ''),
                'route_color': route.get('route_color', ''),
                'route_text_color': route.get('route_text_color', '')
            }
    
    route_directions = defaultdict(list)
    for trip in trips:
        route_id = trip['route_id']
        direction_id = trip.get('direction_id', '0')
        trip_id = trip['trip_id']
        route_directions[(route_id, direction_id)].append(trip_id)

    route_paths = []
    
    for (route_id, direction_id), trip_ids in route_directions.items():
        if not trip_ids:
            continue
            
        sample_trip = trip_ids[0]
        
        trip_stops = []
        for st in stop_times:
            if st['trip_id'] == sample_trip:
                try:
                    stop_sequence = int(st['stop_sequence'])
                    stop_id = st['stop_id']
                    if stop_id in stop_coords:
                        trip_stops.append((stop_sequence, stop_id))
                except (ValueError, KeyError):
                    continue
        
        trip_stops.sort()
        if len(trip_stops) < 2:
            continue
        
        route_info_dict = route_info.get(route_id, {})
        
        for i, (sequence, stop_id) in enumerate(trip_stops):
            stop_data = stop_coords[stop_id]
            
            path_point = {
                'route_id': route_id,
                'direction_id': direction_id,
                'route_path_id': f"{route_id}_{direction_id}",
                'path_sequence': i + 1,
                'stop_lat': stop_data['stop_lat'],
                'stop_lon': stop_data['stop_lon'],
                'stop_id': stop_id,
                'stop_name': stop_data['stop_name'],
                'agency': agency_name,
                'route_short_name': route_info_dict.get('route_short_name', ''),
                'route_long_name': route_info_dict.get('route_long_name', ''),
                'route_type': route_info_dict.get('route_type', ''),
                'route_color': route_info_dict.get('route_color', ''),
                'route_text_color': route_info_dict.get('route_text_color', ''),
                'peak_15min_weekday': stop_data['peak_15min_weekday'],
                'day_15min_weekday': stop_data['day_15min_weekday'],
                'night_60min_weekday': stop_data['night_60min_weekday'],
                'allday_60min_weekend': stop_data['allday_60min_weekend']
            }
            route_paths.append(path_point)
    
    return route_paths

def main():
    gtfs_base_path = '/Users/anyuhang/12th Internship/GTFS'
    output_path = '/Users/anyuhang/12th Internship'
    
    agency_dirs = [d for d in os.listdir(gtfs_base_path) 
                   if os.path.isdir(os.path.join(gtfs_base_path, d))]

    all_route_paths = []
    successful_agencies = 0
    
    for agency in sorted(agency_dirs):
        try:
            paths = create_route_paths(agency, gtfs_base_path)
            if paths:
                all_route_paths.extend(paths)
                successful_agencies += 1
        except Exception:
            continue
    
    all_route_paths.sort(key=lambda x: (x['agency'], x['route_id'], x['direction_id'], x['path_sequence']))
    
    output_file = os.path.join(output_path, 'simplified_routes_tableau.csv')
    
    fieldnames = [
        'route_id', 'direction_id', 'route_path_id', 'path_sequence',
        'stop_lat', 'stop_lon', 'stop_id', 'stop_name', 'agency',
        'route_short_name', 'route_long_name', 'route_type', 
        'route_color', 'route_text_color',
        'peak_15min_weekday', 'day_15min_weekday', 
        'night_60min_weekday', 'allday_60min_weekend'
    ]
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_route_paths)
    
    unique_paths = set(path['route_path_id'] for path in all_route_paths)
    unique_routes = set(path['route_id'] for path in all_route_paths)
    unique_agencies = set(path['agency'] for path in all_route_paths)

if __name__ == "__main__":
    main()
