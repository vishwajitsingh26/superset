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

// One options dataset (filter_type / filter_value rows) feeds all four
// dropdowns. These controls say which type-column value belongs to which
// dropdown, and which column on *other* charts that dropdown's choice
// should filter -- the actual dashboard datasets are not this chart's own.
export interface CustomFilterBandCustomizeProps {
  typeColumn?: QueryFormColumn;
  valueColumn?: QueryFormColumn;
  row_limit?: number | string;
  providerTypeKey?: string;
  providerTargetColumn?: string;
  providerLabel?: string;
  accountTypeKey?: string;
  accountTargetColumn?: string;
  accountLabel?: string;
  regionTypeKey?: string;
  regionTargetColumn?: string;
  regionLabel?: string;
  environmentTypeKey?: string;
  environmentTargetColumn?: string;
  environmentLabel?: string;
}

export type CustomFilterBandFormData = QueryFormData &
  CustomFilterBandCustomizeProps;

export type FilterSlotKey = 'provider' | 'account' | 'region' | 'environment';

export interface FilterSlotConfig {
  key: FilterSlotKey;
  allLabel: string;
  targetColumn: string;
  options: string[];
}

export type FilterSelection = Record<FilterSlotKey, string | null>;

export interface CustomFilterBandProps {
  width: number;
  height: number;
  slots: FilterSlotConfig[];
  selection: FilterSelection;
  setDataMask: SetDataMaskHook;
}
