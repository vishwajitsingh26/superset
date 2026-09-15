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
import { DataRecord } from '../adapters/supersetAdapter';
import {
  metricValue,
  metricLabelOrNull,
  OptionalMetric,
} from '../adapters/optionalMetrics';

export interface TrendResult {
  points: number[];
  deltaPercent: number | null;
}

// Both the sparkline and the delta come from the widened series query, never
// from the (possibly single-row) headline query. The series is split at its
// midpoint into a "previous" and "current" half; comparing their sums gives
// a period-over-period change without needing a second aggregate query.
export function computeTrend(
  rows: DataRecord[],
  metric: OptionalMetric,
  timeColumnLabel: string | null,
): TrendResult {
  if (!rows.length || metricLabelOrNull(metric) === null) {
    return { points: [], deltaPercent: null };
  }

  const timeValue = (row: DataRecord): number =>
    new Date(String(timeColumnLabel ? row[timeColumnLabel] : '')).getTime();

  const sorted = timeColumnLabel
    ? [...rows].sort((a, b) => timeValue(a) - timeValue(b))
    : rows;

  const points = sorted.map(row => {
    const raw = metricValue(row, metric);
    const num = typeof raw === 'number' ? raw : Number(raw);
    return Number.isFinite(num) ? num : 0;
  });

  if (points.length < 2) {
    return { points, deltaPercent: null };
  }

  const half = Math.floor(points.length / 2);
  const previousSum = points.slice(0, half).reduce((sum, v) => sum + v, 0);
  const currentSum = points.slice(half).reduce((sum, v) => sum + v, 0);
  const deltaPercent =
    previousSum === 0 ? null : ((currentSum - previousSum) / previousSum) * 100;

  return { points, deltaPercent };
}
