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
  QueryFormColumn,
  QueryFormData,
  QueryFormMetric,
} from './adapters/supersetAdapter';

export type CardState = 'loading' | 'error' | 'empty' | 'ready';

export interface TrendPoint {
  label: string;
  value: number;
}

export interface SpendCardStylesProps {
  width: number;
  height: number;
}

export interface SpendCardQueryProps {
  metric?: QueryFormMetric;
  shareTotalMetric?: QueryFormMetric;
  driverDimension?: QueryFormColumn;
  x_axis?: QueryFormColumn;
}

export interface SpendCardCustomizeProps {
  cardLabel?: string;
  logoUrl?: string;
  linkLabel?: string;
  linkUrl?: string;
  shareLabel?: string;
  driverLabel?: string;
  trendCaption?: string;
  accentColor?: string;
  valueFormat?: string;
  rateFormat?: string;
  percentFormat?: string;
  shareFormat?: string;
  trendLabelFormat?: string;
  timestampFormat?: string;
  rateHours?: number;
  trendPeriods?: number;
}

export type SpendCardFormData = QueryFormData &
  SpendCardQueryProps &
  SpendCardCustomizeProps;

export type SpendCardProps = SpendCardStylesProps & {
  state: CardState;
  errorMessage: string | null;
  label: string;
  logoUrl: string | null;
  value: string | null;
  absoluteDelta: string | null;
  absoluteDeltaPositive: boolean;
  percentDelta: string | null;
  percentDeltaPositive: boolean;
  share: string | null;
  shareLabel: string;
  rate: string | null;
  trend: TrendPoint[];
  trendCaption: string;
  accentColor: string | null;
  driverLabel: string;
  driverName: string | null;
  driverValue: string | null;
  lastUpdated: string | null;
  linkLabel: string | null;
  linkUrl: string | null;
};
