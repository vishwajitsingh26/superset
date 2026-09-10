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
} from '../adapters/supersetAdapter';
import { KpiCardProps, KpiCardQueryFormData } from '../types';

const DEFAULT_FORMAT = ',.1f';

export default function transformProps(
  chartProps: ChartProps<KpiCardQueryFormData>,
): KpiCardProps {
  const { width, height, formData, queriesData } = chartProps;
  const { metric, cardLabel, numberFormat, unitSuffix, valueColor } = formData;

  const metricLabel = metric ? getMetricLabel(metric) : '';
  const base = {
    width,
    height,
    cardLabel: cardLabel && cardLabel.length > 0 ? cardLabel : metricLabel,
    valueColor: valueColor && valueColor.length > 0 ? valueColor : null,
  };

  const queryData = queriesData?.[0];
  if (!queryData) {
    return { ...base, formattedValue: '', status: 'loading', errorMessage: null };
  }

  const queryError =
    typeof queryData.error === 'string' ? queryData.error : null;
  if (queryError) {
    return {
      ...base,
      formattedValue: '',
      status: 'error',
      errorMessage: queryError,
    };
  }

  const rows: DataRecord[] = queryData.data ?? [];
  const raw: DataRecordValue = rows.length > 0 ? rows[0][metricLabel] : null;
  const value = typeof raw === 'string' ? Number(raw) : raw;

  if (typeof value !== 'number' || Number.isNaN(value)) {
    return { ...base, formattedValue: '', status: 'empty', errorMessage: null };
  }

  const formatter = getNumberFormatter(numberFormat || DEFAULT_FORMAT);
  return {
    ...base,
    formattedValue: `${formatter(value)}${unitSuffix ?? ''}`,
    status: 'ok',
    errorMessage: null,
  };
}
