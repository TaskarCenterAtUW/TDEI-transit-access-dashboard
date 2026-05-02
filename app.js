(function () {
  'use strict';

  const WA_CENTER = [-120.5, 47.4];
  const WA_ZOOM = 6;

  let mapRoutes, mapTracts;
  let routesData = [];           // { pathId, coordinates, agency, county_fips, serviceFlags, stops }
  let amenitiesByGeoid = {};     // geoid -> row object
  let tractGeoJSON = null;       // original
  let tractGeoJSONStyled = null; // with joined amenity counts for choropleth
  let pathIdToRoute = {};       // pathId -> route object
  let stopsByGeoid = {};        // geoid -> array of stops (each has pathId, path_sequence, lat, lon, ...)
  let agencies = new Set();
  let counties = [];            // { fips, name }
  let selectedStop = null;      // { pathId, path_sequence, geoid, ... }
  let selectedTract = null;     // geoid string
  let hoveredPathId = null;     // show stops for this path on hover
  let filterState = {
    agencies: new Set(),
    counties: new Set(),
    amenityMin: 0, amenityMax: 144,
    pedestrianMin: 0, pedestrianMax: 134,
    wheelchairMin: 0, wheelchairMax: 134,
    day15: null, peak15: null, night60: null, weekend60: null
  };

  function parseCSV(text) {
    const lines = text.split(/\r?\n/).filter(Boolean);
    if (!lines.length) return [];
    const header = lines[0].split(',');
    const rows = [];
    for (let i = 1; i < lines.length; i++) {
      const values = [];
      let rest = lines[i];
      for (let c = 0; c < header.length; c++) {
        if (rest.startsWith('"')) {
          const end = rest.indexOf('"', 1);
          values.push(rest.slice(1, end));
          rest = rest.slice(end + 1);
          if (rest.startsWith(',')) rest = rest.slice(1);
        } else {
          const idx = rest.indexOf(',');
          if (idx === -1) { values.push(rest); break; }
          values.push(rest.slice(0, idx));
          rest = rest.slice(idx + 1);
        }
      }
      rows.push(values);
    }
    return { header, rows };
  }

  function csvToObjects(text) {
    const { header, rows } = parseCSV(text);
    return rows.map(row => {
      const o = {};
      header.forEach((h, i) => { o[h] = row[i] !== undefined ? row[i].trim() : ''; });
      return o;
    });
  }

  function loadRoutes(csvText) {
    const rows = csvToObjects(csvText);
    const byPath = {};
    rows.forEach(r => {
      const pathId = r.route_path_id;
      const agency = (r.agency || '').trim();
      if (!pathId) return;
      const pathKey = agency + '|' + pathId;
      if (!byPath[pathKey]) {
        byPath[pathKey] = {
          pathId: pathKey,
          coordinates: [],
          agency: agency,
          county_fips: (r.county_fips || '').padStart(3, '0'),
          serviceFlags: {
            peak_15min_weekday: r.peak_15min_weekday === 'YES',
            day_15min_weekday: r.day_15min_weekday === 'YES',
            night_60min_weekday: r.night_60min_weekday === 'YES',
            allday_60min_weekend: r.allday_60min_weekend === 'YES'
          },
          route_color: r.route_color || '#0066cc',
          stops: []
        };
        agencies.add(agency || '');
      }
      const lat = parseFloat(r.stop_lat), lon = parseFloat(r.stop_lon);
      const seq = parseInt(r.path_sequence, 10);
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(seq)) return;
      const geoid = String(r.census_tract_geoid || '').trim();
      const stop = {
        pathId: pathKey,
        path_sequence: seq,
        stop_id: r.stop_id,
        stop_name: r.stop_name,
        lat, lon, geoid,
        agency: agency,
        serviceFlags: byPath[pathKey].serviceFlags
      };
      byPath[pathKey].stops.push(stop);
      if (geoid) {
        if (!stopsByGeoid[geoid]) stopsByGeoid[geoid] = [];
        stopsByGeoid[geoid].push(stop);
      }
    });
    routesData = Object.values(byPath)
      .map(r => {
        r.stops.sort((a, b) => a.path_sequence - b.path_sequence);
        const seen = new Set();
        r.stops = r.stops.filter(s => {
          const key = s.path_sequence;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        r.coordinates = r.stops.map(s => [s.lon, s.lat]);
        pathIdToRoute[r.pathId] = r;
        return r;
      });
  }

  function loadAmenities(csvText) {
    const rows = csvToObjects(csvText);
    const countyNames = {};
    rows.forEach(r => {
      const geoid = String(r.GEOID || '').trim();
      if (!geoid) return;
      const total = parseFloat(r.total_amenities) || 0;
      const ped = parseFloat(r.unconstrained_pedestrian_count) || 0;
      const wheel = parseFloat(r.manual_wheelchair_count) || 0;
      const pop = parseFloat(r.TOTAL_POPU) || 0;
      const countyFips = geoid.length >= 5 ? geoid.substring(2, 5) : '';
      let name = (r.wa_demo_census_tract_NAME || '').split(';')[1];
      if (name) name = name.trim();
      if (countyFips && name && !countyNames[countyFips]) countyNames[countyFips] = name;
      amenitiesByGeoid[geoid] = {
        GEOID: geoid,
        total_amenities: total,
        unconstrained_pedestrian_count: ped,
        manual_wheelchair_count: wheel,
        TOTAL_POPU: pop,
        county_fips: countyFips,
        county_name: name,
        ...r
      };
    });
    counties = Object.entries(countyNames).map(([fips, name]) => ({ fips, name })).sort((a, b) => a.name.localeCompare(b.name));
  }

  function joinAmenitiesToTractGeoJSON(geojson) {
    const features = geojson.features.map(f => {
      const p = f.properties || {};
      const geoid = p.GEOID || '';
      const a = amenitiesByGeoid[geoid];
      const total = a ? (a.total_amenities || 0) : 0;
      return {
        ...f,
        properties: { ...p, total_amenities: total, _geoid: geoid }
      };
    });
    return { ...geojson, features };
  }

  function getFilteredRoutes() {
    return routesData.filter(r => {
      if (filterState.agencies.size && !filterState.agencies.has(r.agency)) return false;
      if (filterState.counties.size && !filterState.counties.has(r.county_fips)) return false;
      const sf = filterState;
      if (sf.day15 !== null && r.serviceFlags.day_15min_weekday !== sf.day15) return false;
      if (sf.peak15 !== null && r.serviceFlags.peak_15min_weekday !== sf.peak15) return false;
      if (sf.night60 !== null && r.serviceFlags.night_60min_weekday !== sf.night60) return false;
      if (sf.weekend60 !== null && r.serviceFlags.allday_60min_weekend !== sf.weekend60) return false;
      return true;
    });
  }

  function getFilteredTractGeoids() {
    const geoids = new Set();
    Object.entries(amenitiesByGeoid).forEach(([geoid, a]) => {
      if (filterState.counties.size && !filterState.counties.has(a.county_fips)) return;
      const t = a.total_amenities ?? 0;
      const p = a.unconstrained_pedestrian_count ?? 0;
      const w = a.manual_wheelchair_count ?? 0;
      if (t < filterState.amenityMin || t > filterState.amenityMax) return;
      if (p < filterState.pedestrianMin || p > filterState.pedestrianMax) return;
      if (w < filterState.wheelchairMin || w > filterState.wheelchairMax) return;
      geoids.add(geoid);
    });
    return geoids;
  }

  function getRoutesGeoJSON(routes, options = {}) {
    const { onlyPathId = null, onlyStopsInGeoid = null } = options;
    let toUse = routes;
    if (onlyPathId) toUse = routes.filter(r => r.pathId === onlyPathId);
    const features = [];
    toUse.forEach(r => {
      let coords = r.coordinates;
      let stops = r.stops;
      if (onlyStopsInGeoid && onlyPathId) {
        stops = r.stops.filter(s => s.geoid === onlyStopsInGeoid);
        if (stops.length < 2) return;
        coords = stops.map(s => [s.lon, s.lat]);
      }
      if (coords.length < 2) return;
      features.push({
        type: 'Feature',
        properties: { pathId: r.pathId, agency: r.agency, route_color: r.route_color },
        geometry: { type: 'LineString', coordinates: coords }
      });
    });
    return { type: 'FeatureCollection', features };
  }

  function getStopsGeoJSON(stops) {
    const features = (stops || []).map(s => ({
      type: 'Feature',
      properties: { pathId: s.pathId, path_sequence: s.path_sequence, geoid: s.geoid, stop_name: s.stop_name },
      geometry: { type: 'Point', coordinates: [s.lon, s.lat] }
    }));
    return { type: 'FeatureCollection', features };
  }

  function getSegmentsInTract(geoid) {
    const stops = stopsByGeoid[geoid] || [];
    const byPath = {};
    stops.forEach(s => {
      if (!byPath[s.pathId]) byPath[s.pathId] = [];
      byPath[s.pathId].push(s);
    });
    const features = [];
    Object.entries(byPath).forEach(([pathId, list]) => {
      list.sort((a, b) => a.path_sequence - b.path_sequence);
      const coords = list.map(s => [s.lon, s.lat]);
      if (coords.length >= 2) {
        const r = pathIdToRoute[pathId];
        features.push({
          type: 'Feature',
          properties: { pathId, agency: r?.agency, route_color: r?.route_color || '#0066cc' },
          geometry: { type: 'LineString', coordinates: coords }
        });
      }
    });
    return { type: 'FeatureCollection', features };
  }

  function getBoundsFromLngLats(points) {
    if (!points.length) return null;
    let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;
    points.forEach(([lng, lat]) => {
      minLng = Math.min(minLng, lng); maxLng = Math.max(maxLng, lng);
      minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat);
    });
    return [minLng, minLat, maxLng, maxLat];
  }

  function fitMapsToBounds(bounds, padding = 40) {
    if (!bounds || !mapRoutes || !mapTracts) return;
    const [minLng, minLat, maxLng, maxLat] = bounds;
    const b = new maplibregl.LngLatBounds([minLng, minLat], [maxLng, maxLat]);
    mapRoutes.fitBounds(b, { padding, maxZoom: 14 });
    mapTracts.fitBounds(b, { padding, maxZoom: 14 });
  }

  function updateRoutesMap() {
    if (!mapRoutes || !mapRoutes.getSource('routes')) return;
    let routes = getFilteredRoutes();
    let segmentsSource = null;
    let stopsSource = null;

    if (selectedStop) {
      const r = pathIdToRoute[selectedStop.pathId];
      if (r) {
        segmentsSource = getRoutesGeoJSON([r], { onlyPathId: r.pathId, onlyStopsInGeoid: selectedStop.geoid });
        const stopsInTract = (r.stops || []).filter(s => s.geoid === selectedStop.geoid);
        stopsSource = getStopsGeoJSON(stopsInTract);
      }
    } else if (selectedTract) {
      segmentsSource = getSegmentsInTract(selectedTract);
      stopsSource = getStopsGeoJSON(stopsByGeoid[selectedTract] || []);
    } else {
      segmentsSource = getRoutesGeoJSON(routes);
      if (hoveredPathId) {
        const r = pathIdToRoute[hoveredPathId];
        if (r) stopsSource = getStopsGeoJSON(r.stops || []);
      }
    }

    mapRoutes.getSource('routes').setData(segmentsSource || { type: 'FeatureCollection', features: [] });
    if (mapRoutes.getSource('route-stops')) {
      mapRoutes.getSource('route-stops').setData(stopsSource || { type: 'FeatureCollection', features: [] });
    }
  }

  function updateTractsMap() {
    if (!mapTracts || !tractGeoJSONStyled) return;
    const allowed = getFilteredTractGeoids();
    const features = tractGeoJSONStyled.features.map(f => {
      const geoid = f.properties._geoid || f.properties.GEOID;
      const pass = allowed.size === 0 || allowed.has(geoid);
      return { ...f, properties: { ...f.properties, _filtered: pass } };
    });
    const filtered = { ...tractGeoJSONStyled, features };
    if (mapTracts.getSource('tracts')) mapTracts.getSource('tracts').setData(filtered);
    if (mapTracts.getLayer('tracts-highlight')) {
      mapTracts.setFilter('tracts-highlight', selectedTract ? ['==', ['get', 'GEOID'], selectedTract] : ['false']);
    }
  }

  function renderDetailPanel() {
    const el = document.getElementById('detail-content');
    const btn = document.getElementById('btn-clear');
    const geoid = selectedStop ? selectedStop.geoid : selectedTract;
    if (!geoid) {
      el.innerHTML = '<p class="empty">Select a stop or tract.</p>';
      btn.style.display = 'none';
      return;
    }
    btn.style.display = 'block';
    const a = amenitiesByGeoid[geoid];
    const countyName = a?.county_name || (a?.wa_demo_census_tract_NAME || '').split(';')[1]?.trim() || '';
    const pop = a ? (a.TOTAL_POPU != null ? Number(a.TOTAL_POPU).toLocaleString() : '—') : '—';
    const totalAmen = a ? (a.total_amenities != null ? a.total_amenities : 0) : 0;
    const pedAmen = a ? (a.unconstrained_pedestrian_count != null ? a.unconstrained_pedestrian_count : 0) : 0;
    const wheelAmen = a ? (a.manual_wheelchair_count != null ? a.manual_wheelchair_count : 0) : 0;

    const stops = stopsByGeoid[geoid] || [];
    const stopCounts = { day15: 0, peak15: 0, night60: 0, weekend60: 0 };
    stops.forEach(s => {
      if (s.serviceFlags) {
        if (s.serviceFlags.day_15min_weekday) stopCounts.day15++;
        if (s.serviceFlags.peak_15min_weekday) stopCounts.peak15++;
        if (s.serviceFlags.night_60min_weekday) stopCounts.night60++;
        if (s.serviceFlags.allday_60min_weekend) stopCounts.weekend60++;
      }
    });

    let html = '<div class="summary">';
    html += '<p><strong>' + (countyName || 'County') + '</strong></p>';
    html += '<p>Geoid: ' + geoid + '</p>';
    html += '<p>Population: ' + pop + '</p>';
    html += '<p>Total Amenities: ' + totalAmen + '</p>';
    html += '<p>Pedestrian Amenities: ' + pedAmen + '</p>';
    html += '<p>Wheelchair Amenities: ' + wheelAmen + '</p>';
    html += '<div class="stops-table"><table><tr><th></th><th>Stops</th></tr>';
    html += '<tr><td>Day 15Min Weekday</td><td>' + stopCounts.day15 + '</td></tr>';
    html += '<tr><td>Peak 15Min Weekday</td><td>' + stopCounts.peak15 + '</td></tr>';
    html += '<tr><td>Night 60Min Weekday</td><td>' + stopCounts.night60 + '</td></tr>';
    html += '<tr><td>Allday 60Min Weekend</td><td>' + stopCounts.weekend60 + '</td></tr></table></div>';
    html += '</div>';
    html += '<div class="expandable"><details><summary>Amenity breakdown</summary>';
    if (a) {
      const keys = ['wheelchair_bus_stop_count','pedestrian_bus_stop_count','wheelchair_supermarket_count','pedestrian_supermarket_count','wheelchair_school_count','pedestrian_school_count','wheelchair_hospital_count','pedestrian_hospital_count','wheelchair_college_count','pedestrian_college_count','wheelchair_middle_or_high_school_count','pedestrian_middle_or_high_school_count','wheelchair_elementary_school_count','pedestrian_elementary_school_count','wheelchair_other_school_count','pedestrian_other_school_count','wheelchair_grocery_store_count','pedestrian_grocery_store_count','wheelchair_station_count','pedestrian_station_count','wheelchair_doctors_count','pedestrian_doctors_count','wheelchair_clinic_count','pedestrian_clinic_count','wheelchair_healthcare_count','pedestrian_healthcare_count'];
      html += '<table class="stops-table">';
      keys.forEach(k => {
        const v = a[k];
        if (v == null || v === '' || (typeof v === 'number' && isNaN(v))) return;
        const label = k.replace(/_count$/,'').replace(/_/g, ' ');
        html += '<tr><td>' + label + '</td><td>' + v + '</td></tr>';
      });
      html += '</table>';
    } else {
      html += '<p>No breakdown data.</p>';
    }
    html += '</details></div>';
    el.innerHTML = html;
  }

  function setSelectionStop(stop) {
    selectedStop = stop;
    selectedTract = stop ? stop.geoid : selectedTract;
    if (!stop) selectedTract = null;
    if (stop) selectedTract = stop.geoid;
    updateRoutesMap();
    updateTractsMap();
    renderDetailPanel();
    if (stop) {
      const r = pathIdToRoute[stop.pathId];
      const pts = (r?.stops || []).filter(s => s.geoid === stop.geoid).map(s => [s.lon, s.lat]);
      if (pts.length) fitMapsToBounds(getBoundsFromLngLats(pts));
    }
  }

  function setSelectionTract(geoid) {
    selectedTract = geoid;
    selectedStop = null;
    updateRoutesMap();
    updateTractsMap();
    renderDetailPanel();
    if (geoid) {
      const stops = stopsByGeoid[geoid] || [];
      const pts = stops.map(s => [s.lon, s.lat]);
      if (pts.length) fitMapsToBounds(getBoundsFromLngLats(pts));
    }
  }

  function buildFilterUI() {
    const agencyList = document.getElementById('filter-agency');
    agencyList.innerHTML = '';
    [...agencies].sort().forEach(ag => {
      const label = document.createElement('label');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = true;
      cb.dataset.agency = ag;
      cb.addEventListener('change', () => {
        if (cb.checked) filterState.agencies.add(ag); else filterState.agencies.delete(ag);
        updateRoutesMap();
        updateTractsMap();
      });
      label.appendChild(cb);
      label.appendChild(document.createTextNode(' ' + (ag || '(blank)')));
      agencyList.appendChild(label);
    });

    const countyList = document.getElementById('filter-county');
    countyList.innerHTML = '';
    counties.forEach(({ fips, name }) => {
      const label = document.createElement('label');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = true;
      cb.dataset.fips = fips;
      cb.addEventListener('change', () => {
        if (cb.checked) filterState.counties.add(fips); else filterState.counties.delete(fips);
        updateRoutesMap();
        updateTractsMap();
      });
      label.appendChild(cb);
      label.appendChild(document.createTextNode(' ' + (name || fips)));
      countyList.appendChild(label);
    });

    function sliderChange(sliderId, textId, keyMin, keyMax, maxVal) {
      const s = document.getElementById(sliderId);
      const t = document.getElementById(textId);
      const single = !s.classList.contains('dual');
      if (single) {
        const v = parseInt(s.value, 10);
        filterState[keyMin] = 0;
        filterState[keyMax] = v;
        t.textContent = '0 – ' + v;
      }
      updateTractsMap();
    }
    document.getElementById('slider-amenities').addEventListener('input', function() {
      filterState.amenityMax = parseInt(this.value, 10);
      document.getElementById('slider-amenities-text').textContent = '0 – ' + this.value;
      updateTractsMap();
    });
    document.getElementById('slider-pedestrian').addEventListener('input', function() {
      filterState.pedestrianMax = parseInt(this.value, 10);
      document.getElementById('slider-pedestrian-text').textContent = '0 – ' + this.value;
      updateTractsMap();
    });
    document.getElementById('slider-wheelchair').addEventListener('input', function() {
      filterState.wheelchairMax = parseInt(this.value, 10);
      document.getElementById('slider-wheelchair-text').textContent = '0 – ' + this.value;
      updateTractsMap();
    });

    const serviceDiv = document.getElementById('filter-service');
    [
      { id: 'day15', label: '15 Minute Weekday Service', key: 'day_15min_weekday' },
      { id: 'peak15', label: '15-Minute Weekday Peak Hour', key: 'peak_15min_weekday' },
      { id: 'night60', label: '60-Minute Weekday Night', key: 'night_60min_weekday' },
      { id: 'weekend60', label: '60-Minute Weekend All-Day', key: 'allday_60min_weekend' }
    ].forEach(({ id, label, key }) => {
      const wrap = document.createElement('div');
      wrap.innerHTML = '<label>' + label + '</label> <select id="svc-' + id + '"><option value="">(All)</option><option value="yes">YES</option><option value="no">NO</option></select>';
      serviceDiv.appendChild(wrap);
      document.getElementById('svc-' + id).addEventListener('change', function() {
        const v = this.value;
        filterState[id] = v === 'yes' ? true : v === 'no' ? false : null;
        updateRoutesMap();
      });
    });
  }

  function initMaps() {
    mapRoutes = new maplibregl.Map({
      container: 'map-routes',
      style: 'https://demotiles.maplibre.org/style.json',
      center: WA_CENTER,
      zoom: WA_ZOOM
    });

    mapTracts = new maplibregl.Map({
      container: 'map-tracts',
      style: 'https://demotiles.maplibre.org/style.json',
      center: WA_CENTER,
      zoom: WA_ZOOM
    });

    mapRoutes.addControl(new maplibregl.NavigationControl(), 'top-right');
    mapTracts.addControl(new maplibregl.NavigationControl(), 'top-right');

    mapRoutes.on('load', () => {
      mapRoutes.addSource('routes', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      mapRoutes.addLayer({
        id: 'routes-line',
        type: 'line',
        source: 'routes',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': ['get', 'route_color'],
          'line-width': 3,
          'line-opacity': 0.9
        }
      });
      mapRoutes.addSource('route-stops', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      mapRoutes.addLayer({
        id: 'route-stops-circles',
        type: 'circle',
        source: 'route-stops',
        paint: {
          'circle-radius': 6,
          'circle-color': '#333',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#fff'
        }
      });
      mapRoutes.on('click', 'routes-line', e => {
        if (!e.features?.length) return;
        const pathId = e.features[0].properties.pathId;
        const r = pathIdToRoute[pathId];
        if (!r || !r.stops.length) return;
        const f = mapRoutes.queryRenderedFeatures(e.point, { layers: ['routes-line'] })[0];
        if (!f) return;
        const coords = f.geometry.coordinates;
        const clickLng = e.lngLat.lng, clickLat = e.lngLat.lat;
        let best = null, bestDist = Infinity;
        r.stops.forEach(s => {
          const d = (s.lon - clickLng) ** 2 + (s.lat - clickLat) ** 2;
          if (d < bestDist) { bestDist = d; best = s; }
        });
        if (best) setSelectionStop(best);
      });
      mapRoutes.on('click', 'route-stops-circles', e => {
        if (!e.features?.length) return;
        const p = e.features[0].properties;
        const pathId = p.pathId;
        const r = pathIdToRoute[pathId];
        const stop = r?.stops?.find(s => s.path_sequence === p.path_sequence);
        if (stop) setSelectionStop(stop);
      });
      mapRoutes.on('mouseenter', 'routes-line', () => { mapRoutes.getCanvas().style.cursor = 'pointer'; });
      mapRoutes.on('mouseleave', 'routes-line', () => {
        mapRoutes.getCanvas().style.cursor = '';
        if (hoveredPathId) {
          hoveredPathId = null;
          updateRoutesMap();
        }
      });
      mapRoutes.on('mousemove', 'routes-line', e => {
        if (e.features?.length && !selectedStop && !selectedTract) {
          const pathId = e.features[0].properties.pathId;
          if (pathId !== hoveredPathId) {
            hoveredPathId = pathId;
            updateRoutesMap();
          }
        }
      });
      updateRoutesMap();
    });

    mapTracts.on('load', () => {
      if (!tractGeoJSONStyled) return;
      const filtered = getFilteredTractGeoids();
      const features = tractGeoJSONStyled.features.map(f => {
        const geoid = f.properties._geoid || f.properties.GEOID;
        const pass = filtered.size === 0 || filtered.has(geoid);
        return { ...f, properties: { ...f.properties, _filtered: pass } };
      });
      mapTracts.addSource('tracts', { type: 'geojson', data: { ...tractGeoJSONStyled, features } });
      mapTracts.addLayer({
        id: 'tracts-fill',
        type: 'fill',
        source: 'tracts',
        paint: {
          'fill-color': [
            'interpolate', ['linear'], ['get', 'total_amenities'],
            0, '#e0f7fa', 50, '#0097a7', 100, '#004d40'
          ],
          'fill-opacity': 0.6
        },
        filter: ['==', ['get', '_filtered'], true]
      });
      mapTracts.addLayer({
        id: 'tracts-outline',
        type: 'line',
        source: 'tracts',
        paint: { 'line-color': '#666', 'line-width': 0.5 },
        filter: ['==', ['get', '_filtered'], true]
      });
      mapTracts.addLayer({
        id: 'tracts-highlight',
        type: 'fill',
        source: 'tracts',
        paint: { 'fill-color': '#ff9800', 'fill-opacity': 0.5 },
        filter: ['false']
      });
      mapTracts.on('click', e => {
        const features = mapTracts.queryRenderedFeatures(e.point, { layers: ['tracts-fill'] });
        if (!features.length) return;
        const geoid = features[0].properties.GEOID || features[0].properties._geoid;
        if (geoid) setSelectionTract(geoid);
      });
      mapTracts.on('mouseenter', 'tracts-fill', () => { mapTracts.getCanvas().style.cursor = 'pointer'; });
      mapTracts.on('mouseleave', 'tracts-fill', () => { mapTracts.getCanvas().style.cursor = ''; });
      if (selectedTract) mapTracts.setFilter('tracts-highlight', ['==', ['get', 'GEOID'], selectedTract]);
    });

    document.getElementById('btn-clear').addEventListener('click', () => {
      selectedStop = null;
      selectedTract = null;
      updateRoutesMap();
      updateTractsMap();
      renderDetailPanel();
    });
  }

  async function loadData() {
    const [routesResp, amenitiesResp, tractsResp] = await Promise.all([
      fetch('WA Bus Routes.csv').then(r => r.text()),
      fetch('WA amenities.csv').then(r => r.text()),
      fetch('WA Census Tracts.geojson').then(r => r.json())
    ]);
    loadRoutes(routesResp);
    loadAmenities(amenitiesResp);
    tractGeoJSON = tractsResp;
    tractsResp.features.forEach(f => {
      const geoid = (f.properties && f.properties.GEOID) || '';
      if (geoid && !amenitiesByGeoid[geoid]) {
        amenitiesByGeoid[geoid] = {
          GEOID: geoid,
          total_amenities: 0,
          unconstrained_pedestrian_count: 0,
          manual_wheelchair_count: 0,
          county_fips: geoid.length >= 5 ? geoid.substring(2, 5) : ''
        };
      }
    });
    tractGeoJSONStyled = joinAmenitiesToTractGeoJSON(tractsResp);
    buildFilterUI();
    initMaps();
  }

  loadData().catch(err => {
    document.body.innerHTML = '<p style="padding:20px;color:red;">Failed to load data. Serve this folder over HTTP (e.g. <code>npx serve .</code>) and ensure WA Bus Routes.csv, WA amenities.csv, and WA Census Tracts.geojson are in the same directory. Error: ' + err.message + '</p>';
  });
})();
