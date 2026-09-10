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

export interface KpiCardStylesProps {
  height: number;
  width: number;
}

export interface KpiCardCustomizeProps {
  metric?: QueryFormMetric;
  cardLabel?: string;
  numberFormat?: string;
  unitSuffix?: string;
  valueColor?: string | null;
}

export type KpiCardQueryFormData = QueryFormData &
  KpiCardStylesProps &
  KpiCardCustomizeProps;

export type KpiCardStatus = 'ok' | 'loading' | 'empty' | 'error';

export type KpiCardProps = KpiCardStylesProps & {
  cardLabel: string;
  formattedValue: string;
  valueColor: string | null;
  status: KpiCardStatus;
  errorMessage: string | null;
};
