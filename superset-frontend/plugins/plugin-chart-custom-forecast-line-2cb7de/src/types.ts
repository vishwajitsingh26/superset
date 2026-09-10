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
  Currency,
  QueryFormColumn,
  QueryFormData,
  QueryFormMetric,
} from './adapters/supersetAdapter';

export type ViewMode = 'line' | 'area' | 'list';

export interface ForecastLineStylesProps {
  width: number;
  height: number;
}

export interface ForecastLineCustomizeProps {
  x_axis?: QueryFormColumn;
  groupby?: QueryFormColumn[];
  metric?: QueryFormMetric;
  row_limit?: number;
  currency_format?: Currency;
  forecastValue?: string;
  seriesLabelSuffix?: string;
  forecastLabelSuffix?: string;
  seriesColors?: string;
  chartTitle?: string;
  showDecimals?: boolean;
  showLegend?: boolean;
  showScrollbar?: boolean;
  showDivider?: boolean;
  showViewToggle?: boolean;
  showTotalInTooltip?: boolean;
}

export type ForecastLineQueryFormData = QueryFormData &
  ForecastLineStylesProps &
  ForecastLineCustomizeProps;

export interface ForecastSeries {
  id: string;
  group: string;
  name: string;
  forecast: boolean;
  values: (number | null)[];
}

export interface ColoredSeries extends ForecastSeries {
  color: string;
}

export interface ShapedData {
  series: ForecastSeries[];
  categories: number[];
  dividerX: number | null;
  totals: Record<string, number>;
}

export interface ForecastLineChartProps
  extends ForecastLineStylesProps,
    ShapedData {
  title: string;
  currencySymbol: string;
  palette: string[];
  showDecimals: boolean;
  showLegend: boolean;
  showScrollbar: boolean;
  showDivider: boolean;
  showViewToggle: boolean;
  showTotalInTooltip: boolean;
  loading: boolean;
  error: string | null;
}
