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
import { ExtraFormData } from '../adapters/supersetAdapter';
import { MONTH_GRAIN } from '../constants';
import { MonthOption } from '../types';

// Emits the month window and the matching grain in one mask, so every chart on
// the page re-windows and re-buckets from a single consistent selection.
export function buildMonthExtraFormData(
  dateColumn: string,
  option: MonthOption,
): ExtraFormData {
  const extra: Record<string, unknown> = {
    time_grain_sqla: MONTH_GRAIN,
    time_range: `${option.start} : ${option.endExclusive}`,
  };

  // Explicit range filters so charts window even when time_range is not bound
  // to their temporal column.
  if (dateColumn) {
    extra.filters = [
      { col: dateColumn, op: '>=', val: option.start },
      { col: dateColumn, op: '<', val: option.endExclusive },
    ];
  }

  return extra as unknown as ExtraFormData;
}
