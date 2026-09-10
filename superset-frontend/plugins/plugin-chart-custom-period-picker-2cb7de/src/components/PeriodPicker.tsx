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
import { memo, useCallback, useEffect, useMemo } from 'react';
import { Select, t, useTheme } from '../adapters/supersetAdapter';
import { PeriodPickerProps } from '../types';
import { buildMonthExtraFormData } from '../utils/emitMonth';
import { ErrorText, PickerRoot, StatusText } from './PeriodPickerStyles';

function PeriodPicker({
  height,
  monthOptions,
  selectedMonth,
  dateColumn,
  defaultToLatest,
  accentColor,
  placeholderText,
  isLoading,
  errorMessage,
  setDataMask,
}: PeriodPickerProps) {
  const theme = useTheme();
  const accent = accentColor ?? theme.colorPrimary;

  const options = useMemo(
    () => monthOptions.map(option => ({ label: option.label, value: option.key })),
    [monthOptions],
  );

  const emit = useCallback(
    (key?: string) => {
      const option = monthOptions.find(item => item.key === key);
      setDataMask({
        extraFormData: option
          ? buildMonthExtraFormData(dateColumn, option)
          : {},
        filterState: {
          value: option ? [option.key] : null,
          label: option ? option.label : undefined,
        },
      });
    },
    [dateColumn, monthOptions, setDataMask],
  );

  // Seed the dashboard with the newest month so the page is never unfiltered.
  useEffect(() => {
    if (defaultToLatest && !selectedMonth && monthOptions.length > 0) {
      emit(monthOptions[0].key);
    }
  }, [defaultToLatest, selectedMonth, monthOptions, emit]);

  const handleChange = useCallback(
    (value: unknown) => {
      emit(value === null || value === undefined ? undefined : String(value));
    },
    [emit],
  );

  if (errorMessage) {
    return <ErrorText data-testid="custom-period-picker">{errorMessage}</ErrorText>;
  }

  if (isLoading) {
    return (
      <StatusText data-testid="custom-period-picker">
        {t('Loading periods…')}
      </StatusText>
    );
  }

  if (options.length === 0) {
    return (
      <StatusText data-testid="custom-period-picker">
        {t('No periods available')}
      </StatusText>
    );
  }

  return (
    <PickerRoot accent={accent} data-testid="custom-period-picker">
      <Select
        ariaLabel={t('Reporting period')}
        allowClear={!defaultToLatest}
        showSearch={false}
        options={options}
        placeholder={placeholderText}
        value={selectedMonth ?? undefined}
        onChange={handleChange}
        header={null}
        dropdownMatchSelectWidth={false}
        css={{ height }}
      />
    </PickerRoot>
  );
}

export default memo(PeriodPicker);
