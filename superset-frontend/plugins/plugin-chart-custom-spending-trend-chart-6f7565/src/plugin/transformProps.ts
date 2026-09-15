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
import { ChartProps, getColumnLabel } from '../adapters/supersetAdapter';
import { metricLabelOrNull } from '../adapters/optionalMetrics';
import {
  CustomSpendingTrendChartFormData,
  CustomSpendingTrendChartProps,
} from '../types';
import { buildSeries } from '../utils/pivot';

export default function transformProps(
  chartProps: ChartProps<CustomSpendingTrendChartFormData>,
): CustomSpendingTrendChartProps {
  const { width, height, formData, queriesData } = chartProps;
  const data = queriesData?.[0]?.data ?? [];

  const xAxisLabel = formData.x_axis ? getColumnLabel(formData.x_axis) : null;
  const groupbyCols = formData.groupby ?? [];
  const groupbyLabel = groupbyCols.length
    ? getColumnLabel(groupbyCols[0])
    : null;
  const metricLabel = metricLabelOrNull(formData.metric);

  const { categories, providers, series } = buildSeries(
    data,
    xAxisLabel,
    groupbyLabel,
    metricLabel,
  );

  return {
    width: width ?? 0,
    height: height ?? 0,
    categories,
    providers,
    series,
    seriesColors: formData.seriesColors,
  };
}
