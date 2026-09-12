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

// A type alias, not an interface: this value is pushed into `filterState.value`,
// and only type aliases get the implicit index signature that assignment needs.
export type DateRangeValue = {
  start: string;
  end: string;
};

// Every control `controlPanel.ts` declares belongs here, so the component reads
// them by name and typed rather than through a cast.
export type CustomDateRangeFilterCustomizeProps = {
  boundsStartColumn?: QueryFormColumn;
  boundsEndColumn?: QueryFormColumn;
  targetDateColumn?: string;
  defaultStart?: string;
  defaultEnd?: string;
  accentColor?: string;
};

export type CustomDateRangeFilterFormData = QueryFormData &
  CustomDateRangeFilterCustomizeProps;

export type CustomDateRangeFilterProps = {
  width: number;
  height: number;
  // Selectable window, read from the bounds dataset. Null while unknown.
  bounds: DateRangeValue | null;
  selected: DateRangeValue | null;
  defaultRange: DateRangeValue | null;
  targetDateColumn: string;
  accentColor: string | null;
  isLoading: boolean;
  errorMessage: string | null;
  setDataMask: SetDataMaskHook;
};
