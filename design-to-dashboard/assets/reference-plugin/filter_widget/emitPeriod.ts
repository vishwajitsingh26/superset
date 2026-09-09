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
import { ExtraFormData } from '../adapters/supersetAdapter';
import { GRAIN_SQLA } from '../constants';
import { GrainKey } from '../types';

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

// First instant after the selected anchor month (exclusive upper bound).
function monthEndExclusive(month: number, year: number): Date {
  const endMonth = month === 12 ? 0 : month;
  const endYear = month === 12 ? year + 1 : year;
  return new Date(Date.UTC(endYear, endMonth, 1));
}

// Snaps forward to the grain's own bucket boundary. Without this the window cuts
// mid-bucket and the chart renders an extra partial bar (N+1 bars).
function alignEnd(end: Date, grain: GrainKey): Date {
  const y = end.getUTCFullYear();
  const m = end.getUTCMonth();
  switch (grain) {
    case 'weekly': {
      const d = new Date(end.getTime());
      const dow = d.getUTCDay();
      d.setUTCDate(d.getUTCDate() + ((8 - (dow === 0 ? 7 : dow)) % 7));
      return d;
    }
    case 'quarterly': {
      const q = Math.floor(m / 3) * 3;
      if (m === q && end.getUTCDate() === 1) return end;
      return new Date(Date.UTC(y, q + 3, 1));
    }
    case 'yearly': {
      if (m === 0 && end.getUTCDate() === 1) return end;
      return new Date(Date.UTC(y + 1, 0, 1));
    }
    default:
      return end;
  }
}

// Start (inclusive) = aligned end minus `count` buckets of the grain.
function windowStart(end: Date, grain: GrainKey, count: number): Date {
  const d = new Date(end.getTime());
  const n = Math.max(1, Math.floor(count || 1));
  switch (grain) {
    case 'daily':
      d.setUTCDate(d.getUTCDate() - n);
      break;
    case 'weekly':
      d.setUTCDate(d.getUTCDate() - n * 7);
      break;
    case 'quarterly':
      d.setUTCMonth(d.getUTCMonth() - n * 3);
      break;
    case 'yearly':
      d.setUTCFullYear(d.getUTCFullYear() - n);
      break;
    default:
      d.setUTCMonth(d.getUTCMonth() - n);
      break;
  }
  return d;
}

function iso(d: Date): string {
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(
    d.getUTCDate(),
  )}`;
}

export function periodRange(
  grain: GrainKey,
  count: number,
  anchorMonth: number,
  anchorYear: number,
): { start: string; endExclusive: string } {
  const end = alignEnd(monthEndExclusive(anchorMonth, anchorYear), grain);
  const start = windowStart(end, grain, count);
  return { start: iso(start), endExclusive: iso(end) };
}

// Emits the grain AND the matching range in a single mask. Because both live in one
// component, they are always consistent — no cross-filter read, no ordering race.
export function buildPeriodExtraFormData(
  dateColumn: string,
  grain: GrainKey,
  count: number,
  anchorMonth: number,
  anchorYear: number,
): ExtraFormData {
  const { start, endExclusive } = periodRange(
    grain,
    count,
    anchorMonth,
    anchorYear,
  );

  const extra: Record<string, unknown> = {
    time_grain_sqla: GRAIN_SQLA[grain],
    time_range: `${start} : ${endExclusive}`,
  };

  // Explicit range filters so grouped charts window even when time_range is not
  // bound to their temporal column.
  if (dateColumn) {
    extra.filters = [
      { col: dateColumn, op: '>=', val: start },
      { col: dateColumn, op: '<', val: endExclusive },
    ];
  }

  return extra as unknown as ExtraFormData;
}
