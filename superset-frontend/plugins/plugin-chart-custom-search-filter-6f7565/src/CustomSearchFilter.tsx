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
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ChangeEvent } from 'react';
import { Input, styled } from './adapters/supersetAdapter';
import { CustomSearchFilterProps } from './types';
import { buildSearchExtraFormData } from './utils/searchFilter';
import SearchGlyph from './components/SearchGlyph';

// `bare` surface: this is the design's own atomic control (a search box),
// not a card wrapping other content, so it draws its own thin border and
// fill directly rather than relying on the dashboard's card chrome.
const StyledInput = styled(Input)<{ $height: number }>`
  width: 100%;
  height: ${({ $height }) => $height}px;
  border-radius: 8px;
  background-color: ${({ theme }) => theme.colorFillQuaternary};
  border-color: ${({ theme }) => theme.colorBorderSecondary};
  font-size: ${({ theme }) => theme.fontSize}px;
  font-weight: 400;
  color: ${({ theme }) => theme.colorText};

  &::placeholder {
    color: ${({ theme }) => theme.colorTextTertiary};
  }

  .anticon,
  svg {
    color: ${({ theme }) => theme.colorTextTertiary};
  }
`;

export default function CustomSearchFilter({
  height,
  searchColumns,
  placeholderText,
  filterState,
  setDataMask,
}: CustomSearchFilterProps) {
  const [text, setText] = useState<string>(filterState?.value ?? '');

  // Superset resets filter values externally (e.g. "Clear all filters");
  // follow that rather than only tracking our own local edits.
  useEffect(() => {
    setText(filterState?.value ?? '');
  }, [filterState?.value]);

  const emit = useCallback(
    (nextValue: string) => {
      setDataMask({
        filterState: { value: nextValue.trim() ? nextValue : null },
        extraFormData: buildSearchExtraFormData(searchColumns, nextValue),
      });
    },
    [searchColumns, setDataMask],
  );

  // No Apply button is drawn for this control, so every keystroke commits
  // immediately -- no debounce, no batching, per the design.
  const onChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const next = event.target.value;
      setText(next);
      emit(next);
    },
    [emit],
  );

  const inputHeight = useMemo(
    () => Math.min(Math.max(height || 40, 32), 44),
    [height],
  );

  return (
    <StyledInput
      value={text}
      onChange={onChange}
      placeholder={placeholderText}
      prefix={<SearchGlyph size={16} />}
      $height={inputHeight}
      data-test="custom-search-filter-input"
    />
  );
}
