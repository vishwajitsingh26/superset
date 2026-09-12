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
import { DateRangeValue } from '../types';
import { formatRangeLabel, nextDayIso } from './dateUtils';

export type DateRangeDataMask = {
  extraFormData: ExtraFormData;
  filterState: { value: DateRangeValue | null; label: string };
};

// `time_range` windows every chart bound to a temporal column; the explicit
// range filters cover grouped charts whose date column is not the dataset's
// main temporal one. The end is exclusive, so the last day is included whole.
export function buildDateRangeMask(
  range: DateRangeValue,
  targetDateColumn: string,
): DateRangeDataMask {
  const endExclusive = nextDayIso(range.end);
  const extra: Record<string, unknown> = {
    time_range: `${range.start} : ${endExclusive}`,
  };

  if (targetDateColumn) {
    extra.filters = [
      { col: targetDateColumn, op: '>=', val: range.start },
      { col: targetDateColumn, op: '<', val: endExclusive },
    ];
  }

  return {
    extraFormData: extra as unknown as ExtraFormData,
    filterState: { value: range, label: formatRangeLabel(range) },
  };
}
