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
import {
  ChartProps,
  DataRecord,
  DataRecordValue,
  QueryFormColumn,
  SetDataMaskHook,
  getColumnLabel,
  t,
} from '../adapters/supersetAdapter';
import {
  CustomDateRangeFilterFormData,
  CustomDateRangeFilterProps,
  DateRangeValue,
} from '../types';
import { clampRangeToBounds, toIsoDate } from '../utils/dateUtils';

type BoundsQueryData = { data?: DataRecord[]; error?: string };
type ChartExtras = {
  hooks?: { setDataMask?: SetDataMaskHook };
  filterState?: { value?: DateRangeValue | null };
};

function columnKey(column: QueryFormColumn | undefined): string {
  return column ? getColumnLabel(column) : '';
}

// The bounds view names its columns; this reads whatever the controls point at,
// case-insensitively, so repointing the chart at another dataset still works.
function readCell(
  row: DataRecord | undefined,
  key: string,
): DataRecordValue | undefined {
  if (!row || !key) return undefined;
  if (key in row) return row[key];
  const lower = key.toLowerCase();
  const match = Object.keys(row).find(
    candidate => candidate.toLowerCase() === lower,
  );
  return match ? row[match] : undefined;
}

function orderBounds(
  min: string | null,
  max: string | null,
): DateRangeValue | null {
  if (!min || !max) return null;
  return min <= max ? { start: min, end: max } : { start: max, end: min };
}

export default function transformProps(
  chartProps: ChartProps<CustomDateRangeFilterFormData>,
): CustomDateRangeFilterProps {
  const { width, height, formData, queriesData } = chartProps;
  const extras = chartProps as unknown as ChartExtras;
  const query = (queriesData?.[0] ?? {}) as unknown as BoundsQueryData;
  const rows = query.data ?? [];
  const row = rows[0];

  const startKey = columnKey(formData.boundsStartColumn);
  const endKey = columnKey(formData.boundsEndColumn);
  const configured = Boolean(startKey && endKey);

  const bounds = orderBounds(
    toIsoDate(readCell(row, startKey)),
    toIsoDate(readCell(row, endKey)),
  );

  const requestedStart = toIsoDate(formData.defaultStart);
  const requestedEnd = toIsoDate(formData.defaultEnd);
  const requested =
    requestedStart && requestedEnd
      ? { start: requestedStart, end: requestedEnd }
      : null;
  const defaultRange = clampRangeToBounds(requested, bounds) ?? bounds;

  const accent = formData.accentColor?.trim();

  let errorMessage: string | null = query.error ?? null;
  if (!errorMessage && !configured) {
    errorMessage = t('Set the range bounds columns in the chart controls.');
  }

  return {
    width,
    height,
    bounds,
    selected: clampRangeToBounds(extras.filterState?.value, bounds),
    defaultRange,
    targetDateColumn: formData.targetDateColumn ?? '',
    accentColor: accent || null,
    isLoading: configured && rows.length === 0 && !query.error,
    errorMessage,
    setDataMask: extras.hooks?.setDataMask ?? (() => {}),
  };
}
