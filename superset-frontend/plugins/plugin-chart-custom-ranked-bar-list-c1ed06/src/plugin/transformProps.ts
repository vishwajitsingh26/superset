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
  ensureIsArray,
  getColumnLabel,
  getMetricLabel,
} from '../adapters/supersetAdapter';
import {
  DEFAULT_DECIMAL_PLACES,
  DEFAULT_MAX_ITEMS,
  DEFAULT_VALUE_SUFFIX,
} from '../constants';
import { formatValue } from '../utils/formatValue';
import { RankedBarListItem, RankedBarListQueryFormData } from '../types';

export default function transformProps(
  chartProps: ChartProps<RankedBarListQueryFormData>,
) {
  const { width, height, formData, queriesData } = chartProps;
  const {
    groupby,
    metric,
    chartTitle,
    barColor,
    valueSuffix,
    decimalPlaces,
    maxItems,
  } = formData;

  const queryData = queriesData?.[0] as
    | { data?: DataRecord[]; error?: string }
    | undefined;
  const rows: DataRecord[] = queryData?.data ?? [];

  const dimension = ensureIsArray(groupby)[0];
  const categoryKey = dimension ? getColumnLabel(dimension) : '';
  const valueKey = metric ? getMetricLabel(metric) : '';

  const limit =
    typeof maxItems === 'number' && maxItems > 0 ? maxItems : DEFAULT_MAX_ITEMS;
  const decimals =
    typeof decimalPlaces === 'number' ? decimalPlaces : DEFAULT_DECIMAL_PLACES;
  const suffix = valueSuffix === undefined ? DEFAULT_VALUE_SUFFIX : valueSuffix;

  const items: RankedBarListItem[] = rows
    .map(row => ({
      label: String(row[categoryKey] ?? ''),
      value: Number(row[valueKey] ?? 0),
    }))
    .filter(item => Number.isFinite(item.value))
    .sort((a, b) => b.value - a.value)
    .slice(0, limit)
    .map(item => ({
      ...item,
      formatted: formatValue(item.value, decimals, suffix),
    }));

  const maxValue = items.reduce((acc, item) => Math.max(acc, item.value), 0);

  return {
    width,
    height,
    title: chartTitle ?? '',
    items,
    maxValue,
    barColor: barColor ?? '',
    error: queryData?.error ?? null,
  };
}
