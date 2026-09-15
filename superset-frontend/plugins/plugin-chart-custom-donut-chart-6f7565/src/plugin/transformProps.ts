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
  getNumberFormatter,
  QueryFormColumn,
} from '../adapters/supersetAdapter';
import { metricLabelOrNull, metricValue } from '../adapters/optionalMetrics';
import {
  CustomDonutChartFormData,
  CustomDonutChartProps,
  DonutSliceDatum,
} from '../types';

const DEFAULT_VALUE_FORMAT = '$,.0f';
const DEFAULT_PERCENT_FORMAT = '.1%';
const DEFAULT_CENTER_LABEL = 'Total Spend';

// Shape of a slice before it has been given its formatted labels; named so
// the map/filter/reduce chain below never needs an implicit `any` parameter.
interface RawSlice {
  name: string;
  value: number;
}

export default function transformProps(
  chartProps: ChartProps<CustomDonutChartFormData>,
): CustomDonutChartProps {
  const { width, height, formData, queriesData } = chartProps;
  const data = queriesData?.[0]?.data ?? [];

  const [dimension] = ensureIsArray<QueryFormColumn>(formData.groupby).map(
    getColumnLabel,
  );
  const metricLabel = metricLabelOrNull(formData.metric);

  const valueFormatter = getNumberFormatter(
    formData.numberFormat || DEFAULT_VALUE_FORMAT,
  );
  const percentFormatter = getNumberFormatter(
    formData.percentFormat || DEFAULT_PERCENT_FORMAT,
  );

  const rawSlices: RawSlice[] =
    dimension && metricLabel
      ? data
          .map(
            (row: DataRecord): RawSlice => ({
              name: String(row[dimension] ?? ''),
              value: Number(metricValue(row, formData.metric)) || 0,
            }),
          )
          .filter((slice: RawSlice) => slice.value > 0)
      : [];

  const total = rawSlices.reduce(
    (sum: number, slice: RawSlice) => sum + slice.value,
    0,
  );

  const slices: DonutSliceDatum[] = rawSlices.map((slice: RawSlice) => ({
    name: slice.name,
    value: slice.value,
    valueLabel: valueFormatter(slice.value),
    percentLabel: percentFormatter(total ? slice.value / total : 0),
  }));

  return {
    width,
    height,
    slices,
    totalLabel: valueFormatter(total),
    centerLabel: formData.centerLabel || DEFAULT_CENTER_LABEL,
    sliceColors: formData.sliceColors,
    tooltipEnabled: formData.tooltipEnabled ?? true,
  };
}
