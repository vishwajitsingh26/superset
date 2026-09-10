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

export interface SelectFilterStylesProps {
  height: number;
  width: number;
}

export interface SelectFilterCustomizeProps {
  groupby?: QueryFormColumn | QueryFormColumn[];
  filterLabel?: string;
  allLabel?: string;
  multiSelect?: boolean;
  rowLimit?: number;
  row_limit?: number;
}

export type SelectFilterFormData = QueryFormData &
  SelectFilterStylesProps &
  SelectFilterCustomizeProps;

export type SelectValue = string | string[] | null | undefined;

export interface SelectFilterProps extends SelectFilterStylesProps {
  columnLabel: string;
  filterLabel: string;
  allLabel: string;
  multiSelect: boolean;
  options: string[];
  selectedValues: string[];
  errorMessage: string | null;
  isLoading: boolean;
  setDataMask: SetDataMaskHook;
}
