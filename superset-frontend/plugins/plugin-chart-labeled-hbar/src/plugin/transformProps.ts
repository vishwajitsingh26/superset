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
  getMetricLabel,
  getNumberFormatter,
} from '@superset-ui/core';
import {
  LabeledHbarDatum,
  LabeledHbarProps,
  LabeledHbarTransformFormData,
} from '../types';

const DEFAULT_NUMBER_FORMAT = ',.0f';
const DEFAULT_BAR_COLOR = '#22A7C4';
const DEFAULT_BAR_THICKNESS = 24;

function toNumber(value: DataRecordValue): number {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0;
  }
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function toLabel(value: DataRecordValue): string {
  return value === null || value === undefined ? '' : String(value);
}

/**
 * All shaping happens here: the component receives rows that are ready to
 * render. Row order and the top-N cut come from the query (see buildQuery),
 * so no client-side sorting is done.
 */
export default function transformProps(chartProps: ChartProps): LabeledHbarProps {
  const { width, height, formData, queriesData } = chartProps;
  const {
    series,
    metric,
    headerText = '',
    barColor = DEFAULT_BAR_COLOR,
    barThickness = DEFAULT_BAR_THICKNESS,
    valueSuffix = '',
    numberFormat = DEFAULT_NUMBER_FORMAT,
  } = formData as LabeledHbarTransformFormData;

  const categoryKey = series ?? '';
  const metricKey = metric ? getMetricLabel(metric) : '';
  const records = (queriesData?.[0]?.data ?? []) as DataRecord[];
  const format = getNumberFormatter(numberFormat);

  let maxValue = 0;
  const rows = records.map((record, index) => {
    const value = toNumber(record[metricKey]);
    if (value > maxValue) {
      maxValue = value;
    }
    const label = toLabel(record[categoryKey]);
    return {
      key: label === '' ? `row-${index}` : label,
      label,
      value,
    };
  });

  let valueColumnChars = 0;
  const data: LabeledHbarDatum[] = rows.map(row => {
    const formattedValue = `${format(row.value)}${valueSuffix}`;
    if (formattedValue.length > valueColumnChars) {
      valueColumnChars = formattedValue.length;
    }
    return {
      ...row,
      formattedValue,
      widthPercent: maxValue > 0 ? (row.value / maxValue) * 100 : 0,
    };
  });

  return {
    width,
    height,
    data,
    valueColumnChars,
    headerText,
    barColor,
    barThickness,
    valueSuffix,
    numberFormat,
  };
}
