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
  QueryFormColumn,
  SetDataMaskHook,
  ensureIsArray,
  getColumnLabel,
} from '../adapters/supersetAdapter';
import { MAX_PERIOD_LABEL, MIN_PERIOD_LABEL } from '../constants';
import {
  DimensionOption,
  PeriodFilterFormData,
  PeriodFilterProps,
  PeriodFilterValue,
} from '../types';
import { buildMonthOptions, parsePeriod } from '../utils/parseBounds';

type Row = Record<string, unknown>;

function getRowValue(row: Row, key: string): unknown {
  if (key in row) return row[key];
  const lower = key.toLowerCase();
  const match = Object.keys(row).find(k => k.toLowerCase() === lower);
  return match ? row[match] : undefined;
}

function readField(
  raw: Row | undefined,
  formData: Row,
  snake: string,
  camel: string,
): unknown {
  return raw?.[snake] ?? formData?.[camel];
}

function buildDimensionOptions(
  columns: string[],
  rows: Row[],
): DimensionOption[] {
  return columns.map(column => {
    const seen = new Set<string>();
    rows.forEach(row => {
      const value = getRowValue(row, column);
      if (value !== null && value !== undefined && value !== '') {
        seen.add(String(value));
      }
    });
    return { column, values: Array.from(seen).sort() };
  });
}

export default function transformProps(
  chartProps: ChartProps<PeriodFilterFormData>,
): PeriodFilterProps {
  const { width, height, queriesData, hooks, filterState } =
    chartProps as ChartProps<PeriodFilterFormData> & {
      hooks: { setDataMask?: SetDataMaskHook };
      filterState?: { value?: PeriodFilterValue | null };
    };

  const raw = (chartProps as unknown as Row).rawFormData as Row | undefined;
  const formData = chartProps.formData as unknown as Row;

  const dateColumn =
    (readField(raw, formData, 'date_column', 'dateColumn') as string) ?? '';

  const showFilterButton =
    (readField(
      raw,
      formData,
      'show_filter_button',
      'showFilterButton',
    ) as boolean) ?? true;

  const boundsRow = ((queriesData?.[0]?.data ?? []) as Row[])[0] ?? {};
  const min = parsePeriod(getRowValue(boundsRow, MIN_PERIOD_LABEL));
  const max = parsePeriod(getRowValue(boundsRow, MAX_PERIOD_LABEL));
  const monthOptions = min && max ? buildMonthOptions(min, max) : [];

  const dimensionColumns = ensureIsArray<QueryFormColumn>(
    (readField(raw, formData, 'groupby', 'groupby') ?? []) as QueryFormColumn[],
  ).map(column => getColumnLabel(column));

  const dimensionRows = (queriesData?.[1]?.data ?? []) as Row[];
  const dimensionOptions =
    dimensionColumns.length > 0
      ? buildDimensionOptions(dimensionColumns, dimensionRows)
      : [];

  return {
    width,
    height,
    monthOptions,
    dimensionOptions,
    selectedValue: (filterState?.value as PeriodFilterValue) ?? null,
    dateColumn,
    showFilterButton,
    setDataMask: hooks?.setDataMask ?? (() => {}),
    isRefreshing: (chartProps as unknown as Row).isRefreshing as
      | boolean
      | undefined,
  };
}
