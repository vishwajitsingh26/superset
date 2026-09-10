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
import { TrendPoint } from '../types';
import { toNumber } from './format';

export interface Deltas {
  absolute: number | null;
  percent: number | null;
}

export interface TopDriver {
  name: string;
  value: number;
}

// Rows arrive newest-first from the query, so the series is reversed once here
// rather than on every render.
export function buildTrend(
  rows: DataRecord[],
  xKey: string,
  metricKey: string,
  formatLabel: (value: DataRecordValue) => string,
): TrendPoint[] {
  if (!xKey || !metricKey) {
    return [];
  }
  return rows
    .map(row => ({
      label: formatLabel(row[xKey]),
      value: toNumber(row[metricKey]),
    }))
    .reverse();
}

export function computeDeltas(trend: TrendPoint[]): Deltas {
  if (trend.length < 2) {
    return { absolute: null, percent: null };
  }
  const current = trend[trend.length - 1].value;
  const previous = trend[trend.length - 2].value;
  const absolute = current - previous;
  const percent = previous === 0 ? null : (absolute / previous) * 100;
  return { absolute, percent };
}

export function topDriver(
  rows: DataRecord[],
  dimensionKey: string,
  metricKey: string,
): TopDriver | null {
  const row = rows[0];
  if (!row || !dimensionKey || !metricKey) {
    return null;
  }
  return {
    name: String(row[dimensionKey] ?? ''),
    value: toNumber(row[metricKey]),
  };
}
