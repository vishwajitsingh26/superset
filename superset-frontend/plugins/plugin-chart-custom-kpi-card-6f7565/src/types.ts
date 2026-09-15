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
import { QueryFormData, QueryFormMetric } from './adapters/supersetAdapter';

// Every control `controlPanel.ts` declares belongs here. `granularity_sqla`,
// `time_range` and `time_grain_sqla` are already part of `QueryFormData`, so
// they are not redeclared.
export interface CustomKpiCardCustomizeProps {
  metric?: QueryFormMetric;
  label?: string;
  icon?: string;
  accentColor?: string;
  valueFormat?: string;
  comparisonSuffix?: string;
  trendPeriods?: number | string;
}

export type CustomKpiCardFormData = QueryFormData & CustomKpiCardCustomizeProps;

// Props the component reads, produced entirely by transformProps. The
// component does no data shaping of its own.
export interface CustomKpiCardProps {
  width: number;
  height: number;
  label: string;
  icon: string;
  accentColor: string | null;
  valueFormat: string;
  comparisonSuffix: string;
  value: number | null;
  deltaPercent: number | null;
  sparkline: number[];
}
