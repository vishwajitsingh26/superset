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
  DataRecordValue,
  ensureIsArray,
  getMetricLabel,
  getNumberFormatter,
  QueryFormColumn,
} from '@superset-ui/core';
// In 6.x the translation helper `t` moved out of @superset-ui/core.
import { t } from '@apache-superset/core/translation';
import { RankedBarDatum, RankedBarProps, RankedBarQueryFormData } from '../types';

const DEFAULT_BAR_COLOR = '#22a7c2';
const DEFAULT_BAR_THICKNESS = 12;
const DEFAULT_NUMBER_FORMAT = ',.0f';
const DEFAULT_VALUE_SUFFIX = '';
/** Extra character cells reserved between the bar end and the value label. */
const VALUE_GUTTER_PADDING_CH = 2;

function columnLabel(column?: QueryFormColumn): string {
  if (!column) {
    return '';
  }
  return typeof column === 'string'
    ? column
    : column.label ?? column.sqlExpression;
}

function toNumber(value: DataRecordValue): number {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0;
  }
  const parsed = Number(value ?? Number.NaN);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * All shaping happens here, once per data change: ordering, formatting and the
 * bar width itself. The component then does nothing but map over the result.
 */
export default function transformProps(
  chartProps: ChartProps<RankedBarQueryFormData>,
): RankedBarProps {
  const { width, height, formData, queriesData } = chartProps;
  const {
    groupby,
    metric,
    cardTitle,
    barColor,
    barThickness,
    numberFormat,
    valueSuffix,
    showCardBorder,
  } = formData;

  const records = (queriesData?.[0]?.data ?? []) as DataRecord[];
  const metricKey = metric ? getMetricLabel(metric) : '';
  const categoryKey = columnLabel(ensureIsArray<QueryFormColumn>(groupby)[0]);

  const format = numberFormat || DEFAULT_NUMBER_FORMAT;
  const suffix = valueSuffix ?? DEFAULT_VALUE_SUFFIX;
  const formatter = getNumberFormatter(format);

  // The query already orders descending; this keeps the card honest if a saved
  // chart carries a different orderby.
  const rows = records
    .map((record, index) => {
      const rawLabel = record[categoryKey];
      const hasLabel =
        rawLabel !== null && rawLabel !== undefined && rawLabel !== '';
      return {
        key: `${hasLabel ? String(rawLabel) : 'null'}-${index}`,
        label: hasLabel ? String(rawLabel) : t('N/A'),
        value: toNumber(record[metricKey]),
      };
    })
    .sort((a, b) => b.value - a.value);

  const maxValue = rows.reduce(
    (acc, row) => (row.value > acc ? row.value : acc),
    0,
  );
  const valueLabels = rows.map(row => `${formatter(row.value)}${suffix}`);
  // Reserve the value column in `ch` units so the bar never overlaps its own
  // label, without ever measuring the DOM.
  const gutterCh =
    valueLabels.reduce((acc, label) => Math.max(acc, label.length), 0) +
    VALUE_GUTTER_PADDING_CH;

  const data: RankedBarDatum[] = rows.map((row, index) => {
    const fraction = maxValue > 0 && row.value > 0 ? row.value / maxValue : 0;
    return {
      ...row,
      valueLabel: valueLabels[index],
      fraction,
      barStyle: {
        width: `calc((100% - ${gutterCh}ch) * ${fraction.toFixed(4)})`,
      },
    };
  });

  return {
    width,
    height,
    data,
    cardTitle: cardTitle ?? '',
    barColor: barColor || DEFAULT_BAR_COLOR,
    barThickness: barThickness ?? DEFAULT_BAR_THICKNESS,
    numberFormat: format,
    valueSuffix: suffix,
    showCardBorder: showCardBorder ?? false,
    emptyMessage: t('No data'),
  };
}
