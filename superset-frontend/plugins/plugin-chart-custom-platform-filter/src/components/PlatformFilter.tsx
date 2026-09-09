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
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Select, t } from '../adapters/supersetAdapter';
import { PlatformFilterProps } from '../types';
import { buildPlatformDataMask } from '../utils/emitPlatform';
import {
  FilterBar,
  FilterLabel,
  SelectWrap,
  StatusText,
} from './PlatformFilterStyles';

export default function PlatformFilter({
  height,
  width,
  options,
  selectedValues,
  columnName,
  filterLabel,
  placeholderText,
  multiSelect,
  isLoading,
  errorMessage,
  setDataMask,
}: PlatformFilterProps) {
  const [values, setValues] = useState<string[]>(selectedValues);
  const emittedKey = useRef<string | null>(null);

  useEffect(() => {
    setValues(selectedValues);
  }, [selectedValues]);

  // One emit path for both the initial mask and every user change.
  useEffect(() => {
    const key = JSON.stringify(values);
    if (emittedKey.current === key) {
      return;
    }
    emittedKey.current = key;
    setDataMask(
      buildPlatformDataMask(columnName, values, filterLabel, placeholderText),
    );
  }, [values, columnName, filterLabel, placeholderText, setDataMask]);

  const handleChange = useCallback((next: unknown) => {
    if (next === undefined || next === null) {
      setValues([]);
      return;
    }
    setValues(
      Array.isArray(next) ? next.map(item => String(item)) : [String(next)],
    );
  }, []);

  const selectValue = useMemo(
    () => (multiSelect ? values : values[0]),
    [multiSelect, values],
  );

  const barStyle = useMemo(
    () => ({ height, maxWidth: width }),
    [height, width],
  );

  return (
    <FilterBar style={barStyle} data-testid="custom-platform-filter">
      <FilterLabel>{`${filterLabel}:`}</FilterLabel>
      {errorMessage ? (
        <StatusText>{errorMessage}</StatusText>
      ) : (
        <SelectWrap>
          <Select
            allowClear
            ariaLabel={filterLabel}
            loading={isLoading}
            mode={multiSelect ? 'multiple' : undefined}
            maxTagCount={2}
            notFoundContent={t('No values available')}
            onChange={handleChange}
            options={options}
            placeholder={placeholderText}
            value={selectValue}
          />
        </SelectWrap>
      )}
    </FilterBar>
  );
}
