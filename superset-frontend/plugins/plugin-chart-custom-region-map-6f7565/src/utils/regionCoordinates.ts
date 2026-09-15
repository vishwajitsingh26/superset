/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
export interface LonLat {
  lat: number;
  lon: number;
}

// The bound dataset carries only a region_name string, never lat/lon, so a
// design drawing point markers on a world map has to resolve a position
// from that name. Keyed by a lowercase substring checked against the row's
// region name; first match wins, so this list is not order-independent.
// Covers the five names this design draws plus enough other common
// cloud-provider region names that the chart keeps working once it is
// repointed at a real datasource with a different region list.
const REGION_KEYWORDS: [string, LonLat][] = [
  ['virginia', { lat: 38.13, lon: -78.45 }],
  ['us east', { lat: 38.13, lon: -78.45 }],
  ['ohio', { lat: 40.42, lon: -82.91 }],
  ['n. california', { lat: 37.35, lon: -121.96 }],
  ['california', { lat: 37.35, lon: -121.96 }],
  ['oregon', { lat: 45.84, lon: -119.7 }],
  ['us west', { lat: 45.84, lon: -119.7 }],
  ['canada', { lat: 56.13, lon: -106.35 }],
  ['ireland', { lat: 53.41, lon: -8.24 }],
  ['london', { lat: 51.51, lon: -0.13 }],
  ['paris', { lat: 48.86, lon: 2.35 }],
  ['frankfurt', { lat: 50.11, lon: 8.68 }],
  ['stockholm', { lat: 59.33, lon: 18.07 }],
  ['milan', { lat: 45.46, lon: 9.19 }],
  ['singapore', { lat: 1.35, lon: 103.82 }],
  ['sydney', { lat: -33.87, lon: 151.21 }],
  ['tokyo', { lat: 35.68, lon: 139.69 }],
  ['osaka', { lat: 34.69, lon: 135.5 }],
  ['seoul', { lat: 37.57, lon: 126.98 }],
  ['mumbai', { lat: 19.08, lon: 72.88 }],
  ['hyderabad', { lat: 17.38, lon: 78.49 }],
  ['jakarta', { lat: -6.21, lon: 106.85 }],
  ['hong kong', { lat: 22.32, lon: 114.17 }],
  ['sao paulo', { lat: -23.55, lon: -46.63 }],
  ['cape town', { lat: -33.92, lon: 18.42 }],
  ['bahrain', { lat: 26.07, lon: 50.56 }],
  ['dubai', { lat: 25.2, lon: 55.27 }],
];

export function resolveRegionCoordinates(regionName: string): LonLat | null {
  if (!regionName) return null;
  const normalized = regionName.toLowerCase();
  const match = REGION_KEYWORDS.find(([keyword]) =>
    normalized.includes(keyword),
  );
  return match ? match[1] : null;
}

// Plain equirectangular projection: (lon, lat) -> a point in [0,1] x [0,1],
// matching the coordinate system `WorldLandmass` draws its continents in.
export function projectToUnitSquare(point: LonLat): { x: number; y: number } {
  return {
    x: (point.lon + 180) / 360,
    y: (90 - point.lat) / 180,
  };
}
