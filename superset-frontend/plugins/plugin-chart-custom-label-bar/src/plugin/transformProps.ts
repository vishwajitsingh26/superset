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
  QueryFormColumn,
  ensureIsArray,
  getColumnLabel,
  getMetricLabel,
  getNumberFormatter,
} from '../adapters/supersetAdapter';
import { DEFAULT_BAR_HEIGHT, DEFAULT_NUMBER_FORMAT } from '../constants';
import { BarDatum, CustomLabelBarFormData, CustomLabelBarProps } from '../types';

export default function transformProps(
  chartProps: ChartProps<CustomLabelBarFormData>,
): CustomLabelBarProps {
  const { width, height, formData, queriesData, hooks, filterState } =
    chartProps;
  const { groupby, metric, barColor, barHeight, numberFormat, valueSuffix } =
    formData;

  const groupbyLabel =
    ensureIsArray<QueryFormColumn>(groupby).map(getColumnLabel)[0] ?? '';
  const metricLabel = metric ? getMetricLabel(metric) : '';
  const rows = (queriesData?.[0]?.data ?? []) as DataRecord[];

  const formatter = getNumberFormatter(numberFormat || DEFAULT_NUMBER_FORMAT);
  const suffix = valueSuffix ?? '';

  const values =
    groupbyLabel && metricLabel
      ? rows.map(row => ({
          key: String(row[groupbyLabel] ?? ''),
          value: Number(row[metricLabel] ?? 0),
        }))
      : [];

  const maxValue = values.reduce((max, item) => Math.max(max, item.value), 0);

  const bars: BarDatum[] = values.map(item => ({
    key: item.key,
    label: item.key,
    value: item.value,
    formattedValue: `${formatter(item.value)}${suffix}`,
    ratio: maxValue > 0 ? item.value / maxValue : 0,
  }));

  const selectedValues = ensureIsArray<string>(
    (filterState?.value ?? []) as string[],
  ).map(String);

  return {
    width,
    height,
    bars,
    barColor: barColor ?? null,
    barHeight: Number(barHeight) || DEFAULT_BAR_HEIGHT,
    groupbyLabel,
    metricLabel,
    emitCrossFilters: Boolean(chartProps.emitCrossFilters),
    selectedValues,
    setDataMask: hooks?.setDataMask ?? (() => {}),
  };
}
