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
import { PERIOD_GRAIN } from '../constants';
import { DimensionSelection, Period } from '../types';

interface RangeFilter {
  col: string;
  op: string;
  val: string | string[];
}

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function iso(year: number, month: number): string {
  return `${year}-${pad(month)}-01`;
}

// [start, endExclusive) for the selected anchor month.
export function monthRange(period: Period): {
  start: string;
  endExclusive: string;
} {
  const { month, year } = period;
  return {
    start: iso(year, month),
    endExclusive: month === 12 ? iso(year + 1, 1) : iso(year, month + 1),
  };
}

// Grain and range travel in one mask, so charts re-bucket and re-window from a
// single consistent selection with no ordering race.
export function buildPeriodExtraFormData(
  dateColumn: string,
  period: Period,
  dimensions: DimensionSelection,
): ExtraFormData {
  const { start, endExclusive } = monthRange(period);
  const filters: RangeFilter[] = [];

  if (dateColumn) {
    filters.push({ col: dateColumn, op: '>=', val: start });
    filters.push({ col: dateColumn, op: '<', val: endExclusive });
  }

  Object.keys(dimensions).forEach(col => {
    const values = dimensions[col];
    if (values && values.length > 0) {
      filters.push({ col, op: 'IN', val: values });
    }
  });

  const extra: Record<string, unknown> = {
    time_grain_sqla: PERIOD_GRAIN,
    time_range: `${start} : ${endExclusive}`,
  };
  if (filters.length > 0) {
    extra.filters = filters;
  }

  return extra as unknown as ExtraFormData;
}
