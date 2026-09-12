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
import {
  DeltaDirection,
  DeltaSemantics,
  DeltaTone,
  SparkPoint,
} from '../types';

export interface SeriesRow {
  t: number;
  v: number;
  d: number | null;
}

function toTimestamp(raw: DataRecordValue, fallback: number): number {
  if (typeof raw === 'number') return raw;
  if (raw instanceof Date) return raw.getTime();
  if (typeof raw === 'string') {
    const parsed = Date.parse(raw);
    return Number.isNaN(parsed) ? fallback : parsed;
  }
  return fallback;
}

function toNumber(raw: DataRecordValue): number | null {
  if (
    raw === null ||
    raw === undefined ||
    typeof raw === 'boolean' ||
    raw === ''
  )
    return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

// One pass over the rows the single query returned: the value series that
// feeds the sparkline and the delta that sits beside it come from the same
// rows, so no second query is needed.
export function extractSeries(
  records: DataRecord[],
  xKey: string,
  valueKey: string,
  deltaKey: string,
): SeriesRow[] {
  if (!valueKey) return [];
  const rows: SeriesRow[] = [];
  records.forEach((row, index) => {
    const value = toNumber(row[valueKey]);
    if (value === null) return;
    rows.push({
      t: xKey ? toTimestamp(row[xKey], index) : index,
      v: value,
      d: deltaKey ? toNumber(row[deltaKey]) : null,
    });
  });
  return rows.sort((a, b) => a.t - b.t);
}

export function normalizePoints(values: number[]): SparkPoint[] {
  if (values.length === 0) return [];
  if (values.length === 1) {
    return [
      { x: 0, y: 0.5 },
      { x: 1, y: 0.5 },
    ];
  }
  const min = values.reduce((acc, v) => (v < acc ? v : acc), values[0]);
  const max = values.reduce((acc, v) => (v > acc ? v : acc), values[0]);
  const span = max - min;
  const lastIndex = values.length - 1;
  return values.map((v, i) => ({
    x: i / lastIndex,
    y: span === 0 ? 0.5 : (v - min) / span,
  }));
}

// Prefer the bound change measure; fall back to deriving the change from the
// series already fetched rather than asking the database a second time.
export function deriveDeltaPercent(series: SeriesRow[]): number | null {
  if (series.length === 0) return null;
  const last = series[series.length - 1];
  if (last.d !== null) return last.d;
  if (series.length < 2) return null;
  const previous = series[series.length - 2];
  if (previous.v === 0) return null;
  return ((last.v - previous.v) / Math.abs(previous.v)) * 100;
}

export function deltaDirectionOf(delta: number | null): DeltaDirection {
  if (delta === null || delta === 0) return 'flat';
  return delta < 0 ? 'down' : 'up';
}

export function deltaToneOf(
  direction: DeltaDirection,
  semantics: DeltaSemantics,
): DeltaTone {
  if (direction === 'flat' || semantics === 'neutral') return 'neutral';
  const favorableDirection: DeltaDirection =
    semantics === 'decrease_is_good' ? 'down' : 'up';
  return direction === favorableDirection ? 'favorable' : 'unfavorable';
}
