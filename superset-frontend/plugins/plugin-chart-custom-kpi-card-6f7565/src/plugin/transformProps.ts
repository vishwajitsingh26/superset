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
import { ChartProps } from '../adapters/supersetAdapter';
import { metricValue, metricLabelOrNull } from '../adapters/optionalMetrics';
import { CustomKpiCardFormData, CustomKpiCardProps } from '../types';
import { computeTrend } from '../utils/computeTrend';

export default function transformProps(
  chartProps: ChartProps<CustomKpiCardFormData>,
): CustomKpiCardProps {
  const { width, height, formData, queriesData } = chartProps;
  const { metric } = formData;
  const metricLabel = metricLabelOrNull(metric);

  const headlineRow = queriesData?.[0]?.data?.[0];
  const rawTotal = metricLabel ? metricValue(headlineRow, metric) : null;
  const value =
    typeof rawTotal === 'number'
      ? rawTotal
      : rawTotal === null
        ? null
        : Number(rawTotal);

  const seriesRows = queriesData?.[1]?.data ?? [];
  const timeColumnLabel = formData.granularity_sqla
    ? String(formData.granularity_sqla)
    : null;
  const trend = computeTrend(seriesRows, metric, timeColumnLabel);

  return {
    width: width ?? 300,
    height: height ?? 160,
    label: formData.label || metricLabel || '',
    icon: formData.icon || 'cloud',
    accentColor: formData.accentColor || null,
    valueFormat: formData.valueFormat || '$,.0f',
    comparisonSuffix: formData.comparisonSuffix || 'vs. last month',
    value: value !== null && Number.isFinite(value) ? value : null,
    deltaPercent: trend.deltaPercent,
    sparkline: trend.points,
  };
}
