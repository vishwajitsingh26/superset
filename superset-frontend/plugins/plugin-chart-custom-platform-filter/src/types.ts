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

export interface PlatformFilterStylesProps {
  height: number;
  width: number;
}

export interface PlatformFilterCustomizeProps {
  filterColumn?: QueryFormColumn;
  filterLabel?: string;
  placeholderText?: string;
  multiSelect?: boolean;
  sortAscending?: boolean;
  defaultValues?: string[];
  rowLimit?: number;
}

export type PlatformFilterFormData = QueryFormData &
  PlatformFilterStylesProps &
  PlatformFilterCustomizeProps;

export interface PlatformOption {
  label: string;
  value: string;
}

export interface PlatformFilterValue {
  values: string[];
}

export interface PlatformFilterProps extends PlatformFilterStylesProps {
  options: PlatformOption[];
  selectedValues: string[];
  columnName: string;
  filterLabel: string;
  placeholderText: string;
  multiSelect: boolean;
  isLoading: boolean;
  errorMessage: string | null;
  setDataMask: SetDataMaskHook;
}
