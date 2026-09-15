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
import type {
  QueryFormColumn,
  QueryFormData,
  SetDataMaskHook,
} from './adapters/supersetAdapter';

// The two columns on the bounds dataset. Exposed as controls (not
// hardcoded) so this keeps working if the view's column names ever change
// or the chart is repointed at a differently-named bounds dataset.
export interface CustomDateRangeFilterCustomizeProps {
  rangeStartColumn?: QueryFormColumn;
  rangeEndColumn?: QueryFormColumn;
}

export type CustomDateRangeFilterFormData = QueryFormData &
  CustomDateRangeFilterCustomizeProps;

// What `transformProps` hands the component. `selectedRange` is null until
// the user picks a range (or the dashboard restores a saved filter value);
// `minDate`/`maxDate` are the fetched true bounds, also null until the
// bounds query resolves.
export interface CustomDateRangeFilterProps {
  width: number;
  height: number;
  minDate: string | null;
  maxDate: string | null;
  selectedRange: [string, string] | null;
  isLoading: boolean;
  setDataMask: SetDataMaskHook;
}
