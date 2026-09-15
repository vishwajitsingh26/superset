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
// Drawn as a decorative background element, exactly as observed -- no axes,
// no gridlines, no labels. Plain SVG rather than a charting library: this is
// a handful of points, not a chart with its own interactions.
import { useMemo } from 'react';

interface SparklineProps {
  points: number[];
  width: number;
  height: number;
  color: string;
}

function buildPaths(points: number[], width: number, height: number) {
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const stepX = points.length > 1 ? width / (points.length - 1) : width;

  const coords = points.map((value, index) => {
    const x = index * stepX;
    const y = height - ((value - min) / range) * height;
    return [x, y];
  });

  const line = coords
    .map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`)
    .join(' ');
  const area = `${line} L${width.toFixed(2)},${height.toFixed(2)} L0,${height.toFixed(2)} Z`;
  return { line, area };
}

export default function Sparkline({
  points,
  width,
  height,
  color,
}: SparklineProps) {
  const gradientId = useMemo(
    () => `kpi-sparkline-${Math.random().toString(36).slice(2)}`,
    [],
  );

  if (points.length < 2 || width <= 0 || height <= 0) {
    return null;
  }

  const { line, area } = buildPaths(points, width, height);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.35} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} stroke="none" />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
