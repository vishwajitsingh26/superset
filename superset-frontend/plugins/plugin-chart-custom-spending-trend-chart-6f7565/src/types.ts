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
  QueryFormColumn,
  QueryFormMetric,
} from './adapters/supersetAdapter';

export interface CustomSpendingTrendChartStylesProps {
  height: number;
  width: number;
}

// Every control `controlPanel.ts` declares belongs here. A control the form
// data type does not name can only be read through a cast, and renaming the
// control would then break the chart with no type error.
export interface CustomSpendingTrendChartCustomizeProps {
  x_axis?: QueryFormColumn;
  groupby?: QueryFormColumn[];
  metric?: QueryFormMetric;
  grain?: string;
  row_limit?: number | string;
  seriesColors?: string;
}

export type CustomSpendingTrendChartFormData = QueryFormData &
  CustomSpendingTrendChartStylesProps &
  CustomSpendingTrendChartCustomizeProps;

// Shape the component actually receives -- already pivoted by
// `transformProps`, so the component does no data shaping of its own.
export interface CustomSpendingTrendChartProps {
  width: number;
  height: number;
  categories: string[];
  providers: string[];
  series: number[][];
  seriesColors?: string;
}
