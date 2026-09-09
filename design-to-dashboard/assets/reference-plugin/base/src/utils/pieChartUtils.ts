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
/* eslint-disable no-restricted-syntax */
import {
  CK_LENS_PALETTE,
  DEFAULT_TOP_N,
} from '../constants';

export interface FormData {
  groupby?: string[];
  metric?: { label: string } | string;
  // Optional column for tooltip breakdown (if different from groupby[1])
  tooltipBreakdownCol?: string;
}

export interface DataRow {
  [key: string]: string | number;
}

export interface BreakdownMap {
  total: number;
  breakdown: Record<string, number>;
}

// Parse user-provided color string (comma-separated hex) into an array.
export function parseColors(input?: string): string[] {
  if (!input || !input.trim()) return [...CK_LENS_PALETTE];
  const parsed = input
    .split(',')
    .map(c => c.trim())
    .filter(c => /^#[0-9A-Fa-f]{3,8}$/.test(c));
  return parsed.length > 0 ? parsed : [...CK_LENS_PALETTE];
}

// Get color from the provided palette by index (cycles).
export const GetColor = (palette: string[], index: number): string =>
  palette[index % palette.length];

// Format a number using Indian locale conventions.
export function formatNumber(
  val: number | string | undefined,
  showDecimals = false,
): string {
  const num = Number(val || 0);
  if (showDecimals) {
    return num.toLocaleString('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  return num.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

// Aggregates data rows by the first groupby column (pie slices).
export function buildProviderMap(
  data: DataRow[],
  formData: FormData,
): Record<string, BreakdownMap> {
  const groupbyCols = formData.groupby || [];
  const metricLabel =
    typeof formData.metric === 'object'
      ? formData.metric?.label
      : formData.metric;

  const breakdownCol = formData.tooltipBreakdownCol || groupbyCols[1] || '';

  const providerMap: Record<string, BreakdownMap> = {};

  data.forEach(row => {
    const provider = String(row[groupbyCols[0]]);
    const value = Number(row[metricLabel ?? ''] || 0);

    if (!providerMap[provider]) {
      providerMap[provider] = { total: 0, breakdown: {} };
    }
    providerMap[provider].total += value;

    if (breakdownCol) {
      const category = String(row[breakdownCol] ?? '');
      if (!providerMap[provider].breakdown[category]) {
        providerMap[provider].breakdown[category] = 0;
      }
      providerMap[provider].breakdown[category] += value;
    }
  });

  return providerMap;
}

// Takes the full provider map and returns exactly `topN` total slices.
export function getTopNSlices(
  providerMap: Record<string, BreakdownMap>,
  palette: string[],
  topN: number = DEFAULT_TOP_N,
): { name: string; value: number; itemStyle: { color: string } }[] {
  const sorted = Object.entries(providerMap)
    .map(([name, { total }]) => ({ name, value: total }))
    .sort((a, b) => b.value - a.value);

  if (sorted.length <= topN) {
    return sorted.map((item, index) => ({
      name: item.name,
      value: item.value,
      itemStyle: { color: GetColor(palette, index) },
    }));
  }

  const visibleCount = topN - 1;
  const topSlices = sorted.slice(0, visibleCount);
  const othersSlices = sorted.slice(visibleCount);

  const pieDataResult = topSlices.map((item, index) => ({
    name: item.name,
    value: item.value,
    itemStyle: { color: GetColor(palette, index) },
  }));

  const othersTotal = othersSlices.reduce((sum, s) => sum + s.value, 0);

  providerMap['Others'] = { total: othersTotal, breakdown: {} };

  pieDataResult.push({
    name: 'Others',
    value: othersTotal,
    itemStyle: { color: GetColor(palette, visibleCount) },
  });

  return pieDataResult;
}
