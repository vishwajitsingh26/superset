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
  QueryFormData,
  DataRecord,
  QueryFormColumn,
  QueryFormMetric,
} from './adapters/supersetAdapter';

export interface CustomRegionMapStylesProps {
  height: number;
  width: number;
}

// Every control `controlPanel.ts` declares belongs here. `row_limit` is not
// redeclared: it already comes through the base `QueryFormData` as
// `string | number`, and redeclaring it as `number` here would conflict.
export interface CustomRegionMapCustomizeProps {
  groupby?: QueryFormColumn[];
  metric?: QueryFormMetric;
  markerColor?: string;
  highlightColor?: string;
  highlightMatch?: string;
  sizeByMetric?: boolean;
}

export type CustomRegionMapFormData = QueryFormData &
  CustomRegionMapStylesProps &
  CustomRegionMapCustomizeProps;

// What `transformProps` hands the component -- already resolved, so the
// component never has to guard against a raw, possibly-empty form-data
// value.
export interface CustomRegionMapProps {
  data: DataRecord[];
  width: number;
  height: number;
  regionColumn: string | null;
  metricLabel: string | null;
  markerColor: string;
  highlightColor: string;
  highlightMatch: string;
  sizeByMetric: boolean;
}
