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
import { memo, useMemo } from 'react';

export interface SparklineProps {
  values: number[];
  width: number;
  height: number;
  color: string;
  label: string;
}

interface SparkPaths {
  line: string;
  area: string;
}

function buildPaths(
  values: number[],
  width: number,
  height: number,
): SparkPaths | null {
  if (values.length < 2 || width <= 0 || height <= 0) return null;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const stepX = width / (values.length - 1);
  const usable = Math.max(1, height - 2);
  const points = values.map((value, index) => {
    const x = index * stepX;
    const y = height - 1 - ((value - min) / span) * usable;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const line = `M${points.join('L')}`;
  return {
    line,
    area: `${line}L${width.toFixed(2)},${height}L0,${height}Z`,
  };
}

function Sparkline({ values, width, height, color, label }: SparklineProps) {
  const paths = useMemo(
    () => buildPaths(values, width, height),
    [values, width, height],
  );

  if (!paths) return null;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label}
      data-testid="provider-spend-sparkline"
    >
      <path d={paths.area} fill={color} fillOpacity={0.25} stroke="none" />
      <path
        d={paths.line}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default memo(Sparkline);
