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
import { QueryFormData, SetDataMaskHook } from './adapters/supersetAdapter';

// No groupby/metric here: this widget binds to no dataset of its own (see
// binding note) and never queries. Its only configuration is which columns,
// on whichever charts are in its scope, the typed text is matched against.
export interface CustomSearchFilterCustomizeProps {
  searchColumns?: string;
  placeholderText?: string;
}

export type CustomSearchFilterFormData = QueryFormData &
  CustomSearchFilterCustomizeProps;

export interface SearchFilterState {
  value: string | null;
}

export interface CustomSearchFilterProps {
  width: number;
  height: number;
  searchColumns: string[];
  placeholderText: string;
  filterState: SearchFilterState;
  setDataMask: SetDataMaskHook;
}
