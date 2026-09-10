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
import { DataRecord, DataRecordValue } from '../adapters/supersetAdapter';
import { toNumber } from './buildRows';

interface TrendPoint {
  at: string;
  value: number;
}

function sortKey(value: DataRecordValue): string {
  if (value === null || value === undefined) return '';
  if (value instanceof Date) return String(value.getTime()).padStart(16, '0');
  if (typeof value === 'number') return String(value).padStart(16, '0');
  return String(value);
}

// One sparkline series per entity, ordered by the trend column.
export function buildTrendMap(
  data: DataRecord[],
  entityKey: string,
  timeKey: string,
  metricKey: string,
): Map<string, number[]> {
  const buckets = new Map<string, TrendPoint[]>();
  if (!entityKey || !timeKey) return new Map<string, number[]>();
  data.forEach(row => {
    const entity = String(row[entityKey] ?? '');
    const value = toNumber(row[metricKey]);
    if (value === null) return;
    const points = buckets.get(entity) ?? [];
    points.push({ at: sortKey(row[timeKey]), value });
    buckets.set(entity, points);
  });
  const result = new Map<string, number[]>();
  buckets.forEach((points, entity) => {
    result.set(
      entity,
      points
        .sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0))
        .map(point => point.value),
    );
  });
  return result;
}

export interface SparkPath {
  line: string;
  area: string;
}

export function buildSparkPath(
  values: number[],
  width: number,
  height: number,
): SparkPath | null {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const points = values.map((value, index) => {
    const x = index * step;
    const y = height - 1 - ((value - min) / span) * (height - 2);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const line = `M${points.join('L')}`;
  const area = `${line}L${width.toFixed(2)},${height}L0,${height}Z`;
  return { line, area };
}
