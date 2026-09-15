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
// Not pictured in the crop (the design only shows the closed pill), but the
// filter has to actually work: two native date inputs, bounded to the
// fetched min/max so a date outside the real data can never be selected.
import { useEffect, useState } from 'react';
import type { ChangeEvent } from 'react';
import { t, useTheme } from '../adapters/supersetAdapter';
import {
  DropdownPanel,
  FieldRow,
  FieldLabel,
  DateInput,
} from '../CustomDateRangeFilterStyles';

export interface DateRangeDropdownProps {
  minDate: string | null;
  maxDate: string | null;
  startValue: string | null;
  endValue: string | null;
  onChange: (start: string, end: string) => void;
}

export default function DateRangeDropdown({
  minDate,
  maxDate,
  startValue,
  endValue,
  onChange,
}: DateRangeDropdownProps) {
  const theme = useTheme();
  const [start, setStart] = useState<string>(startValue ?? minDate ?? '');
  const [end, setEnd] = useState<string>(endValue ?? maxDate ?? '');

  // Re-sync whenever the committed filter value or the fetched bounds
  // change, so the dropdown never shows a stale selection from before.
  useEffect(() => {
    setStart(startValue ?? minDate ?? '');
    setEnd(endValue ?? maxDate ?? '');
  }, [startValue, endValue, minDate, maxDate]);

  const handleStartChange = (event: ChangeEvent<HTMLInputElement>) => {
    const { value } = event.target;
    setStart(value);
    if (value && end) onChange(value, end);
  };

  const handleEndChange = (event: ChangeEvent<HTMLInputElement>) => {
    const { value } = event.target;
    setEnd(value);
    if (start && value) onChange(start, value);
  };

  return (
    <DropdownPanel data-test="custom-date-range-dropdown">
      <FieldRow>
        <FieldLabel style={{ color: theme.colorTextSecondary }}>
          {t('Start date')}
        </FieldLabel>
        <DateInput
          type="date"
          value={start}
          min={minDate ?? undefined}
          max={end || maxDate || undefined}
          onChange={handleStartChange}
        />
      </FieldRow>
      <FieldRow>
        <FieldLabel style={{ color: theme.colorTextSecondary }}>
          {t('End date')}
        </FieldLabel>
        <DateInput
          type="date"
          value={end}
          min={start || minDate || undefined}
          max={maxDate ?? undefined}
          onChange={handleEndChange}
        />
      </FieldRow>
    </DropdownPanel>
  );
}
