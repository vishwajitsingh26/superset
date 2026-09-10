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
import { memo, useCallback, useMemo } from 'react';
import {
  DataMask,
  ExtraFormData,
  Select,
  ensureIsArray,
  t,
} from '../adapters/supersetAdapter';
import { SelectFilterProps } from '../types';
import { Bar, Prefix, SelectSlot, Status } from './SelectFilterBarStyles';

function buildMask(
  column: string,
  values: string[],
  allLabel: string,
): DataMask {
  const extraFormData: ExtraFormData =
    column && values.length
      ? { filters: [{ col: column, op: 'IN' as const, val: values }] }
      : {};
  return {
    extraFormData,
    filterState: {
      value: values.length ? values : null,
      label: values.length ? values.join(', ') : allLabel,
    },
  };
}

function SelectFilterBar({
  height,
  columnLabel,
  filterLabel,
  allLabel,
  multiSelect,
  options,
  selectedValues,
  errorMessage,
  isLoading,
  setDataMask,
}: SelectFilterProps) {
  const selectOptions = useMemo(
    () => options.map(option => ({ label: option, value: option })),
    [options],
  );

  const value = useMemo(
    () => (multiSelect ? selectedValues : selectedValues[0]),
    [multiSelect, selectedValues],
  );

  const handleChange = useCallback(
    // antd's own SelectValue is wider than this plugin's (it admits numbers),
    // and a narrower handler is not assignable to its onChange.
    (next: unknown) => {
      const values = ensureIsArray<string>(
        (next ?? []) as string | string[],
      ).filter(item => item !== '' && item !== undefined && item !== null);
      setDataMask(buildMask(columnLabel, values, allLabel));
    },
    [allLabel, columnLabel, setDataMask],
  );

  if (errorMessage) {
    return (
      <Bar barHeight={height} data-testid="custom-select-filter">
        <Status>{errorMessage}</Status>
      </Bar>
    );
  }

  if (isLoading) {
    return (
      <Bar barHeight={height} data-testid="custom-select-filter">
        <Status>{t('Loading options…')}</Status>
      </Bar>
    );
  }

  return (
    <Bar barHeight={height} data-testid="custom-select-filter">
      <Prefix>{`${filterLabel}:`}</Prefix>
      <SelectSlot>
        <Select
          ariaLabel={filterLabel}
          allowClear
          showSearch={false}
          mode={multiSelect ? 'multiple' : 'single'}
          options={selectOptions}
          value={value}
          placeholder={allLabel}
          disabled={selectOptions.length === 0}
          onChange={handleChange}
        />
      </SelectSlot>
      {selectOptions.length === 0 && <Status>{t('No values')}</Status>}
    </Bar>
  );
}

export default memo(SelectFilterBar);
