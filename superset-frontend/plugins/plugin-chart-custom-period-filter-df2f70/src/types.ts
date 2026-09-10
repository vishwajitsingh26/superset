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
  SetDataMaskHook,
} from './adapters/supersetAdapter';

export interface Period {
  month: number;
  year: number;
}

export interface MonthOption extends Period {
  value: string;
  label: string;
}

export interface DimensionOption {
  column: string;
  values: string[];
}

export type DimensionSelection = Record<string, string[]>;

export interface PeriodFilterValue {
  period: string | null;
  dimensions: DimensionSelection;
}

export interface PeriodFilterStylesProps {
  width: number;
  height: number;
}

export interface PeriodFilterCustomizeProps {
  date_column?: string;
  dateColumn?: string;
  groupby?: QueryFormColumn[];
  row_limit?: number;
  rowLimit?: number;
  show_filter_button?: boolean;
  showFilterButton?: boolean;
}

export type PeriodFilterFormData = QueryFormData & PeriodFilterCustomizeProps;

export type PeriodFilterProps = PeriodFilterStylesProps & {
  monthOptions: MonthOption[];
  dimensionOptions: DimensionOption[];
  selectedValue: PeriodFilterValue | null;
  dateColumn: string;
  showFilterButton: boolean;
  setDataMask: SetDataMaskHook;
  isRefreshing?: boolean;
};
