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
  SetDataMaskHook,
  ensureIsArray,
  getColumnLabel,
  t,
} from '../adapters/supersetAdapter';
import { DEFAULT_FILTER_LABEL, DEFAULT_PLACEHOLDER } from '../constants';
import {
  PlatformFilterFormData,
  PlatformFilterProps,
  PlatformOption,
} from '../types';

type QueryResult = {
  data?: Record<string, unknown>[];
  error?: string;
};

function toOptions(
  rows: Record<string, unknown>[],
  columnName: string,
  ascending: boolean,
): PlatformOption[] {
  const seen = new Set<string>();
  rows.forEach(row => {
    const raw = row[columnName];
    if (raw === null || raw === undefined) {
      return;
    }
    const value = String(raw);
    if (value !== '') {
      seen.add(value);
    }
  });
  const values = Array.from(seen).sort((a, b) =>
    ascending ? a.localeCompare(b) : b.localeCompare(a),
  );
  return values.map(value => ({ label: value, value }));
}

export default function transformProps(
  chartProps: ChartProps<PlatformFilterFormData>,
): PlatformFilterProps {
  const { width, height, formData, queriesData } =
    chartProps as ChartProps<PlatformFilterFormData> & {
      hooks: { setDataMask?: SetDataMaskHook };
      filterState?: { value?: unknown };
      isRefreshing?: boolean;
    };

  const extras = chartProps as unknown as {
    hooks?: { setDataMask?: SetDataMaskHook };
    filterState?: { value?: unknown };
    isRefreshing?: boolean;
  };

  const columnName = formData.filterColumn
    ? getColumnLabel(formData.filterColumn)
    : '';

  const result = (queriesData?.[0] ?? {}) as QueryResult;
  const rows = result.data ?? [];
  const options = columnName
    ? toOptions(rows, columnName, formData.sortAscending !== false)
    : [];

  const stateValue = extras.filterState?.value;
  const selectedValues =
    stateValue === null || stateValue === undefined
      ? ensureIsArray<string>(formData.defaultValues).map(v => String(v))
      : ensureIsArray<string>(stateValue as string | string[]).map(v =>
          String(v),
        );

  let errorMessage: string | null = null;
  if (!columnName) {
    errorMessage = t('Choose a column to filter on');
  } else if (result.error) {
    errorMessage = t('Could not load filter values');
  }

  return {
    width,
    height,
    options,
    selectedValues,
    columnName,
    filterLabel: formData.filterLabel || DEFAULT_FILTER_LABEL,
    placeholderText: formData.placeholderText || DEFAULT_PLACEHOLDER,
    multiSelect: formData.multiSelect !== false,
    isLoading: Boolean(extras.isRefreshing),
    errorMessage,
    setDataMask: extras.hooks?.setDataMask ?? (() => {}),
  };
}
