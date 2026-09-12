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
  getColumnLabel,
  getMetricLabel,
  getNumberFormatter,
} from '../adapters/supersetAdapter';
import { CustomKpiSparkCardFormData, CustomKpiSparkCardProps } from '../types';
import {
  DEFAULT_PERCENT_FORMAT,
  DEFAULT_SUB_CAPTION,
  DEFAULT_VALUE_FORMAT,
} from '../utils/constants';
import {
  deltaDirectionOf,
  deltaToneOf,
  deriveDeltaPercent,
  extractSeries,
  normalizePoints,
} from '../utils/kpiSparkCard';

// All shaping happens here: the component renders strings and normalised
// geometry only, so a re-render costs nothing beyond layout.
export default function transformProps(
  chartProps: ChartProps<CustomKpiSparkCardFormData>,
): CustomKpiSparkCardProps {
  const { width, height, formData, queriesData } = chartProps;
  const records: DataRecord[] = queriesData?.[0]?.data ?? [];

  const valueKey = formData.metric ? getMetricLabel(formData.metric) : '';
  const deltaKey = formData.deltaMetric
    ? getMetricLabel(formData.deltaMetric)
    : '';
  const xKey = formData.x_axis ? getColumnLabel(formData.x_axis) : '';

  const series = extractSeries(records, xKey, valueKey, deltaKey);
  const latest = series.length > 0 ? series[series.length - 1] : null;

  const valueFormatter = getNumberFormatter(
    formData.valueFormat || DEFAULT_VALUE_FORMAT,
  );
  const percentFormatter = getNumberFormatter(
    formData.percentFormat || DEFAULT_PERCENT_FORMAT,
  );

  const delta = deriveDeltaPercent(series);
  const direction = deltaDirectionOf(delta);
  const cardLabel = formData.cardLabel?.trim();

  return {
    width: width ?? 0,
    height: height ?? 0,
    hasMetric: Boolean(valueKey),
    hasData: latest !== null,
    label: cardLabel || valueKey,
    valueText: latest === null ? '' : valueFormatter(latest.v),
    // Percent values are stored as percentage points, so the magnitude is
    // formatted plainly and the sign is carried by the arrow, not the text.
    deltaText: delta === null ? null : `${percentFormatter(Math.abs(delta))}%`,
    deltaDirection: direction,
    deltaTone: deltaToneOf(
      direction,
      formData.deltaSemantics ?? 'decrease_is_good',
    ),
    subCaption: formData.subCaption ?? DEFAULT_SUB_CAPTION,
    iconGlyph: formData.iconGlyph ?? 'cloud',
    accentColor: formData.accentColor?.trim() || null,
    favorableColor: formData.favorableColor?.trim() || null,
    unfavorableColor: formData.unfavorableColor?.trim() || null,
    showSparkline: formData.showSparkline ?? true,
    sparkPoints: normalizePoints(series.map(row => row.v)),
  };
}
