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
import type { ChartProps, SetDataMaskHook } from '../adapters/supersetAdapter';
import type {
  CustomDateRangeFilterFormData,
  CustomDateRangeFilterProps,
} from '../types';
import { columnName } from '../utils/columns';
import { toISODateString } from '../utils/dateFormat';

const DEFAULT_START_COLUMN = 'range_start';
const DEFAULT_END_COLUMN = 'range_end';

interface FilterHooks {
  setDataMask?: SetDataMaskHook;
}

interface FilterStateShape {
  value?: [string, string] | null;
}

export default function transformProps(
  chartProps: ChartProps<CustomDateRangeFilterFormData>,
): CustomDateRangeFilterProps {
  const { width, height, formData, queriesData } = chartProps;
  const { hooks, filterState, isRefreshing } = chartProps as unknown as {
    hooks?: FilterHooks;
    filterState?: FilterStateShape;
    isRefreshing?: boolean;
  };

  const rangeStartColumn = columnName(
    formData.rangeStartColumn,
    DEFAULT_START_COLUMN,
  );
  const rangeEndColumn = columnName(
    formData.rangeEndColumn,
    DEFAULT_END_COLUMN,
  );

  const rows = (queriesData?.[0]?.data ?? []) as Record<string, unknown>[];
  const row = rows[0];

  const minDate = toISODateString(row?.[rangeStartColumn]);
  const maxDate = toISODateString(row?.[rangeEndColumn]);

  return {
    width,
    height,
    minDate,
    maxDate,
    selectedRange: filterState?.value ?? null,
    isLoading: Boolean(isRefreshing) || queriesData === undefined,
    setDataMask: hooks?.setDataMask ?? (() => {}),
  };
}
