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

export type NullableNumber = number | null;

export interface RgbaColor {
  r: number;
  g: number;
  b: number;
  a?: number;
}

export type ColorValue = string | RgbaColor;

export interface SpendNode {
  key: string;
  label: string;
  values: Record<string, NullableNumber>;
  spend: number;
  mom: NullableNumber;
  pctOfTotal: NullableNumber;
  trend: number[];
  children: SpendNode[];
}

export interface SpendTotals {
  values: Record<string, NullableNumber>;
  spend: number;
}

export type ColumnKind =
  | 'entity'
  | 'provider'
  | 'mom'
  | 'trend'
  | 'pct'
  | 'spend';

export interface ColumnDef {
  key: string;
  label: string;
  kind: ColumnKind;
  align: 'left' | 'right' | 'center';
}

export interface SortState {
  key: string;
  desc: boolean;
}

export interface SpendTableStylesProps {
  width: number;
  height: number;
}

export interface SpendTableCustomizeProps {
  groupby: QueryFormColumn[];
  providerColumn?: QueryFormColumn | QueryFormColumn[];
  trendColumn?: QueryFormColumn | QueryFormColumn[];
  metric: QueryFormMetric;
  momMetric?: QueryFormMetric;
  cardTitle?: string;
  valueFormat?: string;
  currencyFormat?: Currency;
  accentColor?: ColorValue;
  showPercentOfTotal?: boolean;
  showTotalRow?: boolean;
  showSearch?: boolean;
  rowLimit?: number;
  row_limit?: number;
}

export type SpendTableQueryFormData = QueryFormData &
  SpendTableCustomizeProps;

export interface SpendTableProps extends SpendTableStylesProps {
  rows: SpendNode[];
  totals: SpendTotals;
  providers: string[];
  entityLabel: string;
  spendLabel: string;
  cardTitle: string;
  valueFormat: string;
  currency?: Currency;
  accentColor?: string;
  hasMom: boolean;
  hasTrend: boolean;
  showPercentOfTotal: boolean;
  showTotalRow: boolean;
  showSearch: boolean;
  hasQuery: boolean;
}
