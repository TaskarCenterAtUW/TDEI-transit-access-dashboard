import json
import csv

def point_in_polygon(lat, lon, polygon_coords):
    x, y = lon, lat
    n = len(polygon_coords)
    inside = False
    
    p1x, p1y = polygon_coords[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon_coords[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    
    return inside

def get_bounding_box(polygon_coords):
    lons = [coord[0] for coord in polygon_coords]
    lats = [coord[1] for coord in polygon_coords]
    return {
        'min_lon': min(lons),
        'max_lon': max(lons),
        'min_lat': min(lats),
        'max_lat': max(lats)
    }

def point_in_bbox(lat, lon, bbox):
    return (bbox['min_lon'] <= lon <= bbox['max_lon'] and 
            bbox['min_lat'] <= lat <= bbox['max_lat'])

def load_census_tracts(geojson_file):
    
    with open(geojson_file, 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
    
    tracts = []
    for feature in geojson_data['features']:
        geom = feature['geometry']
        props = feature['properties']
        
        polygons = []
        bboxes = []
        if geom['type'] == 'Polygon':
            poly = geom['coordinates'][0]
            polygons.append(poly)
            bboxes.append(get_bounding_box(poly))
        elif geom['type'] == 'MultiPolygon':
            for poly in geom['coordinates']:
                exterior = poly[0]
                polygons.append(exterior)
                bboxes.append(get_bounding_box(exterior))
        
        tracts.append({
            'polygons': polygons,
            'bboxes': bboxes,
            'GEOID': props.get('GEOID', props.get('GEOID20', '')),
            'NAME': props.get('NAME', props.get('NAMELSAD', props.get('NAMELSAD20', ''))),
            'COUNTYFP': props.get('COUNTYFP', props.get('COUNTYFP20', '')),
            'TRACTCE': props.get('TRACTCE', props.get('TRACTCE20', '')),
            'STATEFP': props.get('STATEFP', props.get('STATEFP20', '53'))
        })
    return tracts

def find_census_tract(lat, lon, tracts):
    for tract in tracts:
        for i, polygon in enumerate(tract['polygons']):
            if point_in_bbox(lat, lon, tract['bboxes'][i]):
                if point_in_polygon(lat, lon, polygon):
                    return tract
    return None

def add_census_tracts():
    
    routes_file = '/Users/anyuhang/12th Internship/simplified_routes_tableau.csv'
    census_file = '/Users/anyuhang/12th Internship/tl_2022_53_tract.geojson'
    output_file = '/Users/anyuhang/12th Internship/routes_with_census_tracts.csv'
    
    tracts = load_census_tracts(census_file)
    
    enhanced_data = []
    points_processed = 0
    points_matched = 0
    
    coord_cache = {}
    
    with open(routes_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            points_processed += 1
            
            lat = float(row['stop_lat'])
            lon = float(row['stop_lon'])
            coord_key = f"{lat:.6f},{lon:.6f}"
            
            if coord_key in coord_cache:
                tract_info = coord_cache[coord_key]
            else:
                tract_info = find_census_tract(lat, lon, tracts)
                coord_cache[coord_key] = tract_info
            
            if tract_info:
                row['census_tract_geoid'] = tract_info['GEOID']
                row['census_tract_name'] = tract_info['NAME']
                row['county_fips'] = tract_info['COUNTYFP']
                row['tract_code'] = tract_info['TRACTCE']
                points_matched += 1
            else:
                row['census_tract_geoid'] = ''
                row['census_tract_name'] = ''
                row['county_fips'] = ''
                row['tract_code'] = ''
            
            enhanced_data.append(row)
    
    fieldnames = [
        'route_id', 'direction_id', 'route_path_id', 'path_sequence',
        'stop_lat', 'stop_lon', 'stop_id', 'stop_name', 'agency',
        'route_short_name', 'route_long_name', 'route_type', 
        'route_color', 'route_text_color',
        'peak_15min_weekday', 'day_15min_weekday', 
        'night_60min_weekday', 'allday_60min_weekend',
        'census_tract_geoid', 'census_tract_name', 'county_fips', 'tract_code'
    ]
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enhanced_data)

if __name__ == "__main__":
    add_census_tracts()