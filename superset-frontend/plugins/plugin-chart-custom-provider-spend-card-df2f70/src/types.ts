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

export interface ProviderSpendCardStylesProps {
  width: number;
  height: number;
}

export interface ProviderSpendCardCustomizeProps {
  cardTitle?: string;
  logoUrl?: string | null;
  linkLabel?: string;
  linkUrl?: string | null;
  accentColor?: string | null;
  sparkCaption?: string;
  sparkPeriods?: number;
  driverLabel?: string;
  shareCaption?: string;
  rateCaption?: string;
  hoursInPeriod?: number;
  valueFormat?: string;
  deltaFormat?: string;
  percentFormat?: string;
  shareFormat?: string;
  rateFormat?: string;
}

export interface ProviderSpendCardFormData
  extends QueryFormData,
    ProviderSpendCardCustomizeProps {
  metric: QueryFormMetric;
  share_metric?: QueryFormMetric;
  rate_metric?: QueryFormMetric;
  x_axis?: QueryFormColumn;
  driver_dimension?: QueryFormColumn;
}

export interface ProviderSpendCardProps extends ProviderSpendCardStylesProps {
  title: string;
  logoUrl: string | null;
  valueText: string | null;
  deltaText: string | null;
  deltaPercentText: string | null;
  deltaPositive: boolean;
  subParts: string[];
  series: number[];
  sparkCaption: string;
  driverLabel: string;
  driverName: string | null;
  driverValueText: string | null;
  lastUpdatedText: string;
  linkLabel: string | null;
  linkUrl: string | null;
  accentColor: string | null;
  loading: boolean;
  error: string | null;
}
