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
  CustomTableWithBarFormData,
  CustomTableWithBarProps,
  TableRow,
} from '../types';
import { DEFAULT_VALUE_FORMAT } from '../constants';

export default function transformProps(
  chartProps: ChartProps<CustomTableWithBarFormData>,
): CustomTableWithBarProps {
  const { width, height, formData, queriesData } = chartProps;
  const { groupby, metric, secondaryMetric, barColor, valueFormat } = formData;

  const data: DataRecord[] = queriesData?.[0]?.data ?? [];
  const groupbyCols = ensureIsArray<QueryFormColumn>(groupby);
  const dimensionCol = groupbyCols[0];
  const dimensionLabel = dimensionCol
    ? getColumnLabel(dimensionCol)
    : 'Account Name';

  // Every metric control is read through optionalMetrics: a saved chart can
  // hold an empty secondary metric regardless of its validators.
  const metricLabel = metricLabelOrNull(metric);
  const secondaryLabel = metricLabelOrNull(secondaryMetric);
  const formatValue = getNumberFormatter(valueFormat || DEFAULT_VALUE_FORMAT);

  const spendByRow = data.map((row: DataRecord) =>
    Number(metricValue(row, metric) ?? 0),
  );
  const maxSpend = spendByRow.reduce(
    (max: number, value: number) => Math.max(max, value),
    0,
  );

  const rows: TableRow[] = data.map((row: DataRecord, index: number) => ({
    accountName: dimensionCol ? String(row[dimensionLabel] ?? '') : '',
    totalSpendDisplay: metricLabel ? formatValue(spendByRow[index]) : '—',
    pctChange:
      secondaryLabel !== null
        ? Number(metricValue(row, secondaryMetric) ?? 0)
        : null,
    barPct: maxSpend > 0 ? (spendByRow[index] / maxSpend) * 100 : 0,
  }));

  return {
    width,
    height,
    rows,
    dimensionLabel,
    totalSpendLabel: metricLabel ?? 'Total Spend',
    pctChangeLabel: secondaryLabel ?? '% Change',
    barColor,
  };
}
