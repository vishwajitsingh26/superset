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
import { useMemo } from 'react';
import { useTheme, getNumberFormatter } from './adapters/supersetAdapter';
import { CustomRegionMapProps } from './types';
import {
  resolveRegionCoordinates,
  projectToUnitSquare,
} from './utils/regionCoordinates';
import { resolveColor } from './utils/color';
import WorldLandmass from './components/WorldLandmass';

const MIN_RADIUS = 5;
const MAX_RADIUS = 14;

interface Marker {
  key: string;
  label: string;
  x: number;
  y: number;
  radius: number;
  value: number | null;
  highlighted: boolean;
}

export default function CustomRegionMap({
  data,
  width,
  height,
  regionColumn,
  metricLabel,
  markerColor,
  highlightColor,
  highlightMatch,
  sizeByMetric,
}: CustomRegionMapProps) {
  const theme = useTheme();
  const formatValue = useMemo(() => getNumberFormatter('$,.0f'), []);
  const landFill = theme.colorFillSecondary;
  const dotFill = resolveColor(markerColor, theme.colorPrimary);
  const dotHighlightFill = resolveColor(highlightColor, theme.colorError);

  const markers = useMemo<Marker[]>(() => {
    if (!regionColumn) return [];
    const resolved = data
      .map(row => {
        const raw = row[regionColumn];
        const label = raw === null || raw === undefined ? '' : String(raw);
        if (!label) return null;
        const coords = resolveRegionCoordinates(label);
        if (!coords) return null;
        const rawValue = metricLabel ? row[metricLabel] : null;
        const value =
          typeof rawValue === 'number' ? rawValue : Number(rawValue) || 0;
        return { label, coords, value };
      })
      .filter(
        (
          row,
        ): row is {
          label: string;
          coords: { lat: number; lon: number };
          value: number;
        } => row !== null,
      );

    const maxValue = Math.max(1, ...resolved.map(row => row.value));
    const match = highlightMatch.trim().toLowerCase();

    return resolved.map(row => {
      const { x, y } = projectToUnitSquare(row.coords);
      const ratio = sizeByMetric ? Math.sqrt(row.value / maxValue) : 1;
      return {
        key: row.label,
        label: row.label,
        x,
        y,
        radius: MIN_RADIUS + (MAX_RADIUS - MIN_RADIUS) * ratio,
        value: metricLabel ? row.value : null,
        highlighted:
          match.length > 0 && row.label.toLowerCase().includes(match),
      };
    });
  }, [data, regionColumn, metricLabel, sizeByMetric, highlightMatch]);

  if (!regionColumn) {
    return (
      <div
        style={{
          width,
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: theme.colorTextTertiary,
        }}
        data-testid="custom-region-map"
      >
        Add a region column to plot spend by location.
      </div>
    );
  }

  if (markers.length === 0) {
    return (
      <div
        style={{
          width,
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: theme.colorTextTertiary,
        }}
        data-testid="custom-region-map"
      >
        No matching region data.
      </div>
    );
  }

  return (
    <div style={{ width, height }} data-testid="custom-region-map">
      <svg
        viewBox="0 0 1000 500"
        width="100%"
        height="100%"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="World map of spend by region"
      >
        <WorldLandmass fill={landFill} />
        {markers.map(marker => (
          <circle
            key={marker.key}
            cx={marker.x * 1000}
            cy={marker.y * 500}
            r={marker.radius}
            fill={marker.highlighted ? dotHighlightFill : dotFill}
            stroke={theme.colorBgContainer}
            strokeWidth={1.5}
          >
            <title>
              {marker.value === null
                ? marker.label
                : `${marker.label}: ${formatValue(marker.value)}`}
            </title>
          </circle>
        ))}
      </svg>
    </div>
  );
}
