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
  QueryFormColumn,
  ensureIsArray,
  getColumnLabel,
  getMetricLabel,
  t,
} from '../adapters/supersetAdapter';
import { DEFAULT_VALUE_FORMAT } from '../constants';
import { SpendTableProps, SpendTableQueryFormData } from '../types';
import {
  applyShare,
  attachTrends,
  buildTree,
  collectProviders,
  computeTotals,
} from '../utils/buildRows';
import { buildTrendMap } from '../utils/trend';
import { resolveColor } from '../utils/format';

function firstLabel(column?: QueryFormColumn | QueryFormColumn[]): string {
  const value = ensureIsArray<QueryFormColumn>(column)[0];
  return value ? getColumnLabel(value) : '';
}

export default function transformProps(
  chartProps: ChartProps<SpendTableQueryFormData>,
): SpendTableProps {
  const { width, height, formData, queriesData, datasource } = chartProps;
  const {
    groupby,
    providerColumn,
    trendColumn,
    metric,
    momMetric,
    cardTitle,
    valueFormat,
    currencyFormat,
    accentColor,
    showPercentOfTotal,
    showTotalRow,
    showSearch,
  } = formData;

  const verboseMap = datasource?.verboseMap ?? {};
  const columns = ensureIsArray<QueryFormColumn>(groupby);
  const entityKey = columns[0] ? getColumnLabel(columns[0]) : '';
  const childKey = columns[1] ? getColumnLabel(columns[1]) : undefined;
  const providerKey = firstLabel(providerColumn) || undefined;
  const trendKey = firstLabel(trendColumn);
  const metricKey = metric ? getMetricLabel(metric) : '';
  const momKey = momMetric ? getMetricLabel(momMetric) : undefined;

  const data = (queriesData?.[0]?.data ?? []) as DataRecord[];
  const trendData = (queriesData?.[1]?.data ?? []) as DataRecord[];
  const hasQuery = Boolean(entityKey && metricKey);

  const providers =
    hasQuery && providerKey ? collectProviders(data, providerKey) : [];
  const rows = hasQuery
    ? buildTree(data, {
        entity: entityKey,
        child: childKey,
        provider: providerKey,
        metric: metricKey,
        mom: momKey,
      })
    : [];
  const totals = computeTotals(rows, providers);
  applyShare(rows, totals.spend);
  const trends = buildTrendMap(trendData, entityKey, trendKey, metricKey);
  attachTrends(rows, trends);

  return {
    width,
    height,
    rows,
    totals,
    providers,
    entityLabel: verboseMap[entityKey] ?? entityKey ?? t('Category'),
    spendLabel: verboseMap[metricKey] ?? metricKey ?? t('Value'),
    cardTitle: cardTitle ?? t('Overview'),
    valueFormat: valueFormat ?? DEFAULT_VALUE_FORMAT,
    currency: currencyFormat,
    accentColor: resolveColor(accentColor),
    hasMom: Boolean(momKey),
    hasTrend: trends.size > 0,
    showPercentOfTotal: showPercentOfTotal !== false,
    showTotalRow: showTotalRow !== false,
    showSearch: showSearch !== false,
    hasQuery,
  };
}
