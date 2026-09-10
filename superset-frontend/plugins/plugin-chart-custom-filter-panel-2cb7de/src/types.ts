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

export interface FilterPanelStylesProps {
  height: number;
  width: number;
}

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterField {
  column: string;
  label: string;
  options: FilterOption[];
}

export type FilterPanelValue = Record<string, string[]>;

export interface FilterPanelCustomizeProps {
  groupby: QueryFormColumn[];
  buttonLabel?: string;
  accentColor?: string | null;
  rowLimit?: number;
  row_limit?: number;
}

export type FilterPanelFormData = QueryFormData &
  FilterPanelStylesProps &
  FilterPanelCustomizeProps;

export interface FilterPanelProps extends FilterPanelStylesProps {
  fields: FilterField[];
  selected: FilterPanelValue;
  buttonLabel: string;
  accentColor: string | null;
  setDataMask: SetDataMaskHook;
}
