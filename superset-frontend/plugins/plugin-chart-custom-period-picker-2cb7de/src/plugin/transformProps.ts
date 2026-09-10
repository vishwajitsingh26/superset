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
  getColumnLabel,
} from '../adapters/supersetAdapter';
import { PeriodPickerFormData, PeriodPickerProps } from '../types';
import { buildMonthOptions } from '../utils/monthOptions';

function readField(
  raw: Record<string, unknown> | undefined,
  formData: Record<string, unknown>,
  snake: string,
  camel: string,
): unknown {
  return raw?.[snake] ?? formData?.[camel] ?? formData?.[snake];
}

export default function transformProps(
  chartProps: ChartProps<PeriodPickerFormData>,
): PeriodPickerProps {
  const { width, height, queriesData } = chartProps;
  const { hooks, filterState } = chartProps as ChartProps<PeriodPickerFormData> & {
    hooks: { setDataMask?: SetDataMaskHook };
    filterState?: { value?: string[] | null };
  };

  const raw = (chartProps as unknown as Record<string, unknown>).rawFormData as
    | Record<string, unknown>
    | undefined;
  const formData = chartProps.formData as unknown as Record<string, unknown>;

  const column = readField(raw, formData, 'x_axis', 'xAxis') as
    | QueryFormColumn
    | undefined;
  const dateColumn = column ? getColumnLabel(column) : '';

  const queryData = queriesData?.[0];
  const rows = (queryData?.data ?? []) as Record<string, unknown>[];
  const monthOptions = buildMonthOptions(rows, dateColumn);

  const selected = filterState?.value;
  const selectedMonth =
    Array.isArray(selected) && selected.length > 0 ? String(selected[0]) : null;

  const accentRaw = readField(raw, formData, 'accent_color', 'accentColor');
  const placeholderRaw = readField(
    raw,
    formData,
    'placeholder_text',
    'placeholderText',
  );
  const defaultToLatestRaw = readField(
    raw,
    formData,
    'default_to_latest',
    'defaultToLatest',
  );

  return {
    width,
    height,
    monthOptions,
    selectedMonth,
    dateColumn,
    defaultToLatest: defaultToLatestRaw !== false,
    accentColor: typeof accentRaw === 'string' && accentRaw ? accentRaw : null,
    placeholderText:
      typeof placeholderRaw === 'string' && placeholderRaw
        ? placeholderRaw
        : 'Select month',
    isLoading: !queryData && !dateColumn === false && rows.length === 0 && !queryData,
    errorMessage:
      typeof (queryData as { error?: string } | undefined)?.error === 'string'
        ? ((queryData as { error?: string }).error as string)
        : null,
    setDataMask: hooks?.setDataMask ?? (() => {}),
  };
}
