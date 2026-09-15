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
import { CustomKpiCardFormData } from '../types';

const GRAIN_BY_TIME_GRAIN_SQLA: Record<string, string> = {
  P1M: 'month',
  P1W: 'week',
  P1D: 'day',
  PT1H: 'hour',
};

function extractRangeEnd(range: string): string | null {
  const separatorIndex = range.indexOf(' : ');
  if (separatorIndex === -1) return null;
  const end = range.slice(separatorIndex + 3).trim();
  return end || null;
}

// Widens the series query's time_range, anchored to the end of whatever
// range the dashboard currently has in effect, so the sparkline moves with
// the dashboard's date control instead of ignoring it. Superset parses the
// DATEADD(...) expression server-side; no date arithmetic happens here.
export function widenedSeriesFormData(
  formData: CustomKpiCardFormData,
  span: number,
): CustomKpiCardFormData {
  const extra = formData.extra_form_data as { time_range?: string } | undefined;
  const effectiveRange =
    extra?.time_range ?? formData.time_range ?? 'No filter';

  if (!effectiveRange || effectiveRange === 'No filter') {
    return {
      ...formData,
      extra_form_data: { ...extra, time_range: 'No filter' },
    };
  }

  const end = extractRangeEnd(effectiveRange);
  if (!end) {
    return formData;
  }

  const grain =
    GRAIN_BY_TIME_GRAIN_SQLA[formData.time_grain_sqla ?? ''] ?? 'day';
  const widenedRange = `DATEADD(DATETIME('${end}'), -${span}, ${grain}) : ${end}`;

  return {
    ...formData,
    extra_form_data: { ...extra, time_range: widenedRange },
  };
}
