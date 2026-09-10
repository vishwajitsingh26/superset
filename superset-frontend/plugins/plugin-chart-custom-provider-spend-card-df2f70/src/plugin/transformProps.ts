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
} from '../adapters/supersetAdapter';
import {
  formatNumeric,
  formatPercent,
  formatSigned,
  formatUtcTimestamp,
  toNumber,
} from '../utils/format';
import { ProviderSpendCardFormData, ProviderSpendCardProps } from '../types';

const cell = (row: DataRecord | undefined, key: string | null): number | null =>
  row && key ? toNumber(row[key]) : null;

export default function transformProps(
  chartProps: ChartProps,
): ProviderSpendCardProps {
  const { width, height, formData, queriesData } = chartProps;
  const fd = formData as ProviderSpendCardFormData;
  const primary = queriesData?.[0];
  const driverResult = queriesData?.[1];
  const rows = (primary?.data ?? []) as DataRecord[];

  const valueFormat = fd.valueFormat ?? '$,.0f';
  const deltaFormat = fd.deltaFormat ?? '$,.0f';
  const percentFormat = fd.percentFormat ?? '.2f';
  const shareFormat = fd.shareFormat ?? '.0f';
  const rateFormat = fd.rateFormat ?? '$,.2f';

  const metricLabel = fd.metric ? getMetricLabel(fd.metric) : null;
  const shareMetricLabel = fd.share_metric
    ? getMetricLabel(fd.share_metric)
    : null;
  const rateMetricLabel = fd.rate_metric ? getMetricLabel(fd.rate_metric) : null;

  // Rows arrive newest first; the sparkline needs oldest first.
  const latest = rows[0];
  const previous = rows[1];
  const value = cell(latest, metricLabel);
  const previousValue = cell(previous, metricLabel);
  const deltaAbsolute =
    value !== null && previousValue !== null ? value - previousValue : null;
  const deltaPercent =
    deltaAbsolute !== null && previousValue
      ? (deltaAbsolute / Math.abs(previousValue)) * 100
      : null;

  const shareTotal = cell(latest, shareMetricLabel);
  const sharePercent =
    value !== null && shareTotal ? (value / shareTotal) * 100 : null;

  const hours = fd.hoursInPeriod ?? 0;
  const explicitRate = cell(latest, rateMetricLabel);
  const ratePerHour =
    explicitRate !== null
      ? explicitRate
      : value !== null && hours > 0
        ? value / hours
        : null;

  const series = rows
    .map(row => cell(row, metricLabel) ?? 0)
    .slice()
    .reverse();

  const shareText = formatPercent(sharePercent, shareFormat);
  const rateText = formatNumeric(ratePerHour, rateFormat);
  const subParts: string[] = [];
  if (shareText && fd.shareCaption) {
    subParts.push(`${shareText} of ${fd.shareCaption}`);
  } else if (shareText) {
    subParts.push(shareText);
  }
  if (rateText) subParts.push(`${rateText} ${fd.rateCaption ?? '/ hr'}`.trim());

  const driverRow = (driverResult?.data ?? [])[0] as DataRecord | undefined;
  const driverColumn = fd.driver_dimension
    ? getColumnLabel(fd.driver_dimension)
    : null;
  const driverRaw =
    driverRow && driverColumn ? driverRow[driverColumn] : undefined;

  return {
    width,
    height,
    title: fd.cardTitle ?? '',
    logoUrl: fd.logoUrl ?? null,
    valueText: formatNumeric(value, valueFormat),
    deltaText: formatSigned(deltaAbsolute, deltaFormat),
    deltaPercentText: formatPercent(
      deltaPercent === null ? null : Math.abs(deltaPercent),
      percentFormat,
    ),
    deltaPositive: (deltaAbsolute ?? 0) >= 0,
    subParts,
    series,
    sparkCaption: fd.sparkCaption ?? '',
    driverLabel: fd.driverLabel ?? '',
    driverName:
      driverRaw === undefined || driverRaw === null ? null : String(driverRaw),
    driverValueText: formatNumeric(cell(driverRow, metricLabel), valueFormat),
    lastUpdatedText: formatUtcTimestamp(new Date()),
    linkLabel: fd.linkLabel ?? null,
    linkUrl: fd.linkUrl ?? null,
    accentColor: fd.accentColor ?? null,
    loading: primary === undefined,
    error: primary?.error ?? null,
  };
}
