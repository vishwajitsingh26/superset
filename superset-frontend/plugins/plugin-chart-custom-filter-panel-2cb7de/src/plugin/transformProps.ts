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
} from '../adapters/supersetAdapter';
import { DEFAULT_BUTTON_LABEL, MAX_OPTIONS } from '../constants';
import {
  FilterField,
  FilterOption,
  FilterPanelFormData,
  FilterPanelProps,
  FilterPanelValue,
} from '../types';
import { humanizeColumn, toStringArray } from '../utils/labels';

type Row = Record<string, unknown>;

function collectOptions(rows: Row[], column: string): FilterOption[] {
  const seen = new Set<string>();
  rows.forEach(row => {
    const raw = row[column];
    if (raw === null || raw === undefined || raw === '') return;
    seen.add(String(raw));
  });
  return Array.from(seen)
    .sort((a, b) => a.localeCompare(b))
    .slice(0, MAX_OPTIONS)
    .map(value => ({ value, label: value }));
}

function readSelected(
  value: unknown,
  fields: FilterField[],
): FilterPanelValue {
  const selected: FilterPanelValue = {};
  const source =
    value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {};
  fields.forEach(field => {
    selected[field.column] = toStringArray(source[field.column]);
  });
  return selected;
}

export default function transformProps(
  chartProps: ChartProps<FilterPanelFormData>,
): FilterPanelProps {
  const { width, height, formData, queriesData, hooks, filterState } =
    chartProps as ChartProps<FilterPanelFormData> & {
      hooks: { setDataMask?: SetDataMaskHook };
      filterState?: { value?: unknown };
    };

  const rows = (queriesData?.[0]?.data ?? []) as Row[];

  const fields: FilterField[] = ensureIsArray(formData.groupby)
    .map(column => getColumnLabel(column))
    .filter(column => column !== '')
    .map(column => ({
      column,
      label: humanizeColumn(column),
      options: collectOptions(rows, column),
    }));

  return {
    width,
    height,
    fields,
    selected: readSelected(filterState?.value, fields),
    buttonLabel: formData.buttonLabel || DEFAULT_BUTTON_LABEL,
    accentColor: formData.accentColor ?? null,
    setDataMask: hooks?.setDataMask ?? (() => {}),
  };
}
