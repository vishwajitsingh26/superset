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
  QueryFormData,
  AdhocMetric,
  AdhocColumn,
  FeatureFlag,
  getColumnLabel,
  getNumberFormatter,
  isAdhocColumn,
  isFeatureEnabled,
  isPhysicalColumn,
  CurrencyFormatter,
  buildQueryContext,
  ensureIsArray,
  QueryFormColumn,
  QueryFormOrderBy,
  Behavior,
  ChartMetadata,
  ChartPlugin,
  DataRecord,
  extractTimegrain,
  getTimeFormatter,
  getTimeFormatterForGranularity,
  SMART_DATE_ID,
  TimeFormats,
  validateNonEmpty,
  QueryFormMetric,
  SetDataMaskHook,
  DataRecordValue,
  JsonObject,
  TimeFormatter,
  NumberFormatter,
  TimeGranularity,
  ContextMenuFilters,
  Currency,
} from '@superset-ui/core';

// Superset 6.1 moved these out of @superset-ui/core. This barrel is exactly
// why: call sites never change, only this file does.
import { GenericDataType } from '@apache-superset/core/common';
import {
  styled as styledComponent,
  useTheme as useThemeHook,
} from '@apache-superset/core/theme';
import { t as translate } from '@apache-superset/core/translation';
import {
  ControlPanelConfig,
  ControlPanelState,
  D3_TIME_FORMAT_OPTIONS,
  Dataset,
  getStandardizedControls,
  sharedControls,
  getColorFormatters,
  ColorFormatters,
} from '@superset-ui/chart-controls';

export const styled = styledComponent;
export const useTheme = useThemeHook;

export const t = translate;

export type {
  ChartProps,
  QueryFormData,
  AdhocMetric,
  AdhocColumn,
  QueryFormColumn,
  QueryFormOrderBy,
  DataRecord,
  QueryFormMetric,
  SetDataMaskHook,
  DataRecordValue,
  JsonObject,
  TimeFormatter,
  NumberFormatter,
  TimeGranularity,
  ContextMenuFilters,
  Currency,
};

export {
  getColumnLabel,
  getNumberFormatter,
  isAdhocColumn,
  isFeatureEnabled,
  isPhysicalColumn,
  CurrencyFormatter,
  buildQueryContext,
  ensureIsArray,
  Behavior,
  ChartMetadata,
  ChartPlugin,
  extractTimegrain,
  getTimeFormatter,
  getTimeFormatterForGranularity,
  SMART_DATE_ID,
  TimeFormats,
  validateNonEmpty,
  FeatureFlag,
  GenericDataType,
};

export type {
  ControlPanelConfig,
  ControlPanelState,
  Dataset,
  ColorFormatters,
};
export {
  D3_TIME_FORMAT_OPTIONS,
  getStandardizedControls,
  sharedControls,
  getColorFormatters,
};

export interface StableChartInput {
  data: DataRecord[];
  width: number;
  height: number;
  groupby: string[];
  metric: string;
  formData: QueryFormData;
}

export interface StableFormatter {
  (value: number | string | null): string;
}

export function adaptChartProps(
  props: ChartProps<QueryFormData>,
): StableChartInput {
  const { queriesData, formData, width, height } = props;

  const groupby = ensureIsArray<QueryFormColumn>(formData?.groupby).map(item =>
    getColumnLabel(item),
  );
  const metricLabel =
    typeof formData?.metric === 'object'
      ? formData?.metric?.label
      : formData?.metric;

  return {
    data: queriesData?.[0]?.data ?? [],
    width: width ?? 800,
    height: height ?? 600,
    groupby,
    metric: metricLabel ?? '',
    formData,
  };
}

export function createFormatter(
  valueFormat: string,
  currencyFormat?: Currency,
): StableFormatter {
  if (currencyFormat?.symbol) {
    return new CurrencyFormatter({
      currency: currencyFormat,
      d3Format: valueFormat,
    });
  }
  return getNumberFormatter(valueFormat);
}

export function extractMetricNames(
  metrics: (string | AdhocMetric)[],
): string[] {
  return metrics.map((metric: string | AdhocMetric) =>
    typeof metric === 'string' ? metric : (metric.label as string),
  );
}
