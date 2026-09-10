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
  getCurrencySymbol,
  getMetricLabel,
  QueryFormColumn,
} from '../adapters/supersetAdapter';
import { DEFAULT_FORECAST_VALUE } from '../constants';
import { ForecastLineChartProps, ForecastLineQueryFormData } from '../types';
import { parseColorList } from '../utils/format';
import shapeRows from '../utils/transformData';

export default function transformProps(
  chartProps: ChartProps<ForecastLineQueryFormData>,
): ForecastLineChartProps {
  const { formData, queriesData, width, height } = chartProps;
  const queryResult = queriesData?.[0] as
    | { data?: DataRecord[]; error?: string }
    | undefined;

  const dimensions = ensureIsArray<QueryFormColumn>(formData.groupby).map(
    column => getColumnLabel(column),
  );

  const shaped = shapeRows(queryResult?.data ?? [], {
    xLabel: formData.x_axis ? getColumnLabel(formData.x_axis) : '',
    seriesLabel: dimensions[0] ?? '',
    flagLabel: dimensions[1] ?? '',
    metricLabel: formData.metric ? getMetricLabel(formData.metric) : '',
    forecastValue: formData.forecastValue || DEFAULT_FORECAST_VALUE,
    labelSuffix: formData.seriesLabelSuffix ?? '',
    forecastSuffix: formData.forecastLabelSuffix ?? '',
  });

  return {
    ...shaped,
    width: width ?? 0,
    height: height ?? 0,
    title: formData.chartTitle ?? '',
    currencySymbol: formData.currency_format
      ? (getCurrencySymbol(formData.currency_format) ?? '')
      : '',
    palette: parseColorList(formData.seriesColors),
    showDecimals: formData.showDecimals ?? false,
    showLegend: formData.showLegend ?? true,
    showScrollbar: formData.showScrollbar ?? true,
    showDivider: formData.showDivider ?? true,
    showViewToggle: formData.showViewToggle ?? true,
    showTotalInTooltip: formData.showTotalInTooltip ?? true,
    loading: !queriesData,
    error: queryResult?.error ?? null,
  };
}
