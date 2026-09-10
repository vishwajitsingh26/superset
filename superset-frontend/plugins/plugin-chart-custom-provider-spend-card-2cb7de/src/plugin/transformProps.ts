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
  QueryFormData,
  getColumnLabel,
  getMetricLabel,
  getNumberFormatter,
  t,
} from '../adapters/supersetAdapter';
import {
  DEFAULT_PERCENT_FORMAT,
  DEFAULT_RATE_FORMAT,
  DEFAULT_RATE_HOURS,
  DEFAULT_SHARE_FORMAT,
  DEFAULT_TIMESTAMP_FORMAT,
  DEFAULT_TREND_LABEL_FORMAT,
  DEFAULT_VALUE_FORMAT,
} from '../constants';
import { CardState, SpendCardFormData, SpendCardProps } from '../types';
import { formatTemporal, signedLabel, toNumber } from '../utils/format';
import { buildTrend, computeDeltas, topDriver } from '../utils/spendCard';

interface QueryResult {
  data?: DataRecord[];
  error?: string | null;
}

export default function transformProps(
  chartProps: ChartProps<QueryFormData>,
): SpendCardProps {
  const { width, height, queriesData } = chartProps;
  const formData = chartProps.formData as SpendCardFormData;
  const results = (queriesData ?? []) as unknown as QueryResult[];
  const trendRows = results[0]?.data ?? [];
  const driverRows = results[1]?.data ?? [];
  const errorMessage = results.find(result => result?.error)?.error ?? null;

  const metricKey = formData.metric ? getMetricLabel(formData.metric) : '';
  const totalKey = formData.shareTotalMetric
    ? getMetricLabel(formData.shareTotalMetric)
    : '';
  const xKey = formData.x_axis ? getColumnLabel(formData.x_axis) : '';
  const driverKey = formData.driverDimension
    ? getColumnLabel(formData.driverDimension)
    : '';

  const valueFormatter = getNumberFormatter(
    formData.valueFormat || DEFAULT_VALUE_FORMAT,
  );
  const rateFormatter = getNumberFormatter(
    formData.rateFormat || DEFAULT_RATE_FORMAT,
  );
  const percentFormatter = getNumberFormatter(
    formData.percentFormat || DEFAULT_PERCENT_FORMAT,
  );
  const shareFormatter = getNumberFormatter(
    formData.shareFormat || DEFAULT_SHARE_FORMAT,
  );
  const trendLabelFormat =
    formData.trendLabelFormat || DEFAULT_TREND_LABEL_FORMAT;

  const trend = buildTrend(trendRows, xKey, metricKey, value =>
    formatTemporal(value, trendLabelFormat),
  );
  const latestRow = trendRows[0];
  let latest: number | null = null;
  if (trend.length > 0) {
    latest = trend[trend.length - 1].value;
  } else if (latestRow && metricKey) {
    latest = toNumber(latestRow[metricKey]);
  }
  const total = latestRow && totalKey ? toNumber(latestRow[totalKey]) : 0;
  const { absolute, percent } = computeDeltas(trend);
  const driver = topDriver(driverRows, driverKey, metricKey);
  const rateHours = Number(formData.rateHours) || DEFAULT_RATE_HOURS;

  let state: CardState = 'ready';
  if (errorMessage) {
    state = 'error';
  } else if (results.length === 0) {
    state = 'loading';
  } else if (trendRows.length === 0) {
    state = 'empty';
  }

  return {
    width,
    height,
    state,
    errorMessage: errorMessage ?? null,
    label: formData.cardLabel || '',
    logoUrl: formData.logoUrl || null,
    value: latest === null ? null : valueFormatter(latest),
    absoluteDelta:
      absolute === null ? null : signedLabel(absolute, valueFormatter),
    absoluteDeltaPositive: (absolute ?? 0) >= 0,
    percentDelta:
      percent === null ? null : `${percentFormatter(Math.abs(percent))}%`,
    percentDeltaPositive: (percent ?? 0) >= 0,
    share:
      latest === null || total === 0
        ? null
        : `${shareFormatter((latest / total) * 100)}%`,
    shareLabel: formData.shareLabel || '',
    rate:
      latest === null
        ? null
        : `${rateFormatter(latest / rateHours)} ${t('/ hr')}`,
    trend,
    trendCaption: formData.trendCaption || '',
    accentColor: formData.accentColor || null,
    driverLabel: formData.driverLabel || '',
    driverName: driver ? driver.name : null,
    driverValue: driver ? valueFormatter(driver.value) : null,
    lastUpdated:
      latestRow && xKey
        ? formatTemporal(
            latestRow[xKey],
            formData.timestampFormat || DEFAULT_TIMESTAMP_FORMAT,
          )
        : null,
    linkLabel: formData.linkLabel || null,
    linkUrl: formData.linkUrl || null,
  };
}
