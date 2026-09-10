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
  SetDataMaskHook,
} from './adapters/supersetAdapter';

export interface MonthOption {
  key: string;
  label: string;
  start: string;
  endExclusive: string;
}

export interface PeriodPickerStylesProps {
  width: number;
  height: number;
}

export interface PeriodPickerCustomizeProps {
  x_axis?: QueryFormColumn;
  default_to_latest?: boolean;
  accent_color?: string | null;
  placeholder_text?: string;
  rowLimit?: number;
  row_limit?: number;
}

export type PeriodPickerFormData = QueryFormData &
  PeriodPickerStylesProps &
  PeriodPickerCustomizeProps;

export interface PeriodPickerProps extends PeriodPickerStylesProps {
  monthOptions: MonthOption[];
  selectedMonth: string | null;
  dateColumn: string;
  defaultToLatest: boolean;
  accentColor: string | null;
  placeholderText: string;
  isLoading: boolean;
  errorMessage: string | null;
  setDataMask: SetDataMaskHook;
}
