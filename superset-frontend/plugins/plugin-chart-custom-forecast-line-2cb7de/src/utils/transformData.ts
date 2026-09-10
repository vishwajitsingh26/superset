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
import { ForecastSeries, ShapedData } from '../types';

export interface ShapeOptions {
  xLabel: string;
  seriesLabel: string;
  flagLabel: string;
  metricLabel: string;
  forecastValue: string;
  labelSuffix: string;
  forecastSuffix: string;
}

interface Bucket {
  group: string;
  forecast: boolean;
  points: Map<number, number>;
}

function toTime(value: DataRecordValue): number {
  if (typeof value === 'number') return value;
  if (value instanceof Date) return value.getTime();
  const parsed = Date.parse(String(value ?? ''));
  return Number.isNaN(parsed) ? 0 : parsed;
}

function seriesName(
  group: string,
  forecast: boolean,
  options: ShapeOptions,
): string {
  const parts = [group, options.labelSuffix].filter(Boolean);
  if (forecast && options.forecastSuffix) parts.push(options.forecastSuffix);
  return parts.join(' ');
}

// A forecast line starts where its actual line ends, so the two read as one run.
function bridgeForecast(
  series: ForecastSeries[],
  categories: number[],
  dividerX: number | null,
): void {
  if (dividerX === null) return;
  const index = categories.indexOf(dividerX);
  if (index < 0) return;
  series
    .filter(item => item.forecast)
    .forEach(item => {
      const actual = series.find(
        other => !other.forecast && other.group === item.group,
      );
      if (actual && item.values[index] === null) {
        item.values[index] = actual.values[index];
      }
    });
}

export default function shapeRows(
  rows: DataRecord[],
  options: ShapeOptions,
): ShapedData {
  const buckets = new Map<string, Bucket>();
  const totals: Record<string, number> = {};
  const times = new Set<number>();
  let dividerX: number | null = null;
  let hasForecast = false;

  rows.forEach(row => {
    const x = toTime(row[options.xLabel]);
    const group = String(row[options.seriesLabel] ?? '');
    const flag = options.flagLabel ? String(row[options.flagLabel] ?? '') : '';
    const forecast =
      flag.toLowerCase() === options.forecastValue.toLowerCase();
    const y = Number(row[options.metricLabel] ?? 0);
    const id = `${group}|${forecast ? 'f' : 'a'}`;
    const bucket = buckets.get(id) ?? {
      group,
      forecast,
      points: new Map<number, number>(),
    };
    bucket.points.set(x, (bucket.points.get(x) ?? 0) + y);
    buckets.set(id, bucket);
    times.add(x);
    totals[String(x)] = (totals[String(x)] ?? 0) + y;
    if (forecast) hasForecast = true;
    else if (dividerX === null || x > dividerX) dividerX = x;
  });

  const categories = Array.from(times).sort((a, b) => a - b);
  const series: ForecastSeries[] = Array.from(buckets.entries())
    .sort(
      ([, a], [, b]) =>
        a.group.localeCompare(b.group) ||
        Number(a.forecast) - Number(b.forecast),
    )
    .map(([id, bucket]) => ({
      id,
      group: bucket.group,
      forecast: bucket.forecast,
      name: seriesName(bucket.group, bucket.forecast, options),
      values: categories.map(x => bucket.points.get(x) ?? null),
    }));

  bridgeForecast(series, categories, dividerX);

  return { series, categories, dividerX: hasForecast ? dividerX : null, totals };
}
