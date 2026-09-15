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
import { ChartProps, SetDataMaskHook } from '../adapters/supersetAdapter';
import {
  CustomSearchFilterFormData,
  CustomSearchFilterProps,
  SearchFilterState,
} from '../types';
import {
  DEFAULT_PLACEHOLDER,
  DEFAULT_SEARCH_COLUMNS,
  parseSearchColumns,
} from '../utils/searchFilter';

// `hooks.setDataMask` and `filterState` exist on every native-filter chart at
// runtime but are not part of the public `ChartProps` type; the reference
// filter widget reads them the same way, through a narrow local cast.
interface FilterRuntimeProps {
  hooks?: { setDataMask?: SetDataMaskHook };
  filterState?: SearchFilterState;
}

export default function transformProps(
  chartProps: ChartProps<CustomSearchFilterFormData>,
): CustomSearchFilterProps {
  const { width, height, formData } = chartProps;
  const { hooks, filterState } =
    chartProps as ChartProps<CustomSearchFilterFormData> & FilterRuntimeProps;

  const searchColumns = parseSearchColumns(
    formData?.searchColumns,
    DEFAULT_SEARCH_COLUMNS,
  );
  const placeholderText =
    formData?.placeholderText?.trim() || DEFAULT_PLACEHOLDER;

  return {
    width: width ?? 400,
    height: height ?? 40,
    searchColumns,
    placeholderText,
    filterState: { value: filterState?.value ?? null },
    setDataMask: hooks?.setDataMask ?? (() => {}),
  };
}
