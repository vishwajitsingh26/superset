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
import { useTheme } from './adapters/supersetAdapter';
import type { CustomDateRangeFilterProps } from './types';
import {
  Pill,
  IconSlot,
  LabelText,
  ChevronSlot,
  DropdownAnchor,
} from './CustomDateRangeFilterStyles';
import { CalendarIcon, ChevronDownIcon } from './utils/icons';
import { addDaysISO, formatDisplayDate } from './utils/dateFormat';
import DateRangeDropdown from './components/DateRangeDropdown';

export default function CustomDateRangeFilter({
  width,
  height,
  minDate,
  maxDate,
  selectedRange,
  isLoading,
  setDataMask,
}: CustomDateRangeFilterProps) {
  const theme = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  // Keep the last known bounds on screen through a refetch instead of
  // blanking the pill: this control renders before its own query resolves.
  const [knownBounds, setKnownBounds] = useState<{
    min: string | null;
    max: string | null;
  }>({ min: null, max: null });

  useEffect(() => {
    if (minDate && maxDate) setKnownBounds({ min: minDate, max: maxDate });
  }, [minDate, maxDate]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const effectiveStart = selectedRange?.[0] ?? knownBounds.min;
  const effectiveEnd = selectedRange?.[1] ?? knownBounds.max;

  const label = useMemo(() => {
    const startLabel = formatDisplayDate(effectiveStart);
    const endLabel = formatDisplayDate(effectiveEnd);
    if (!startLabel || !endLabel) {
      return isLoading ? 'Loading date range\u2026' : 'Select date range';
    }
    return `${startLabel} - ${endLabel}`;
  }, [effectiveStart, effectiveEnd, isLoading]);

  // No Apply button is drawn for this control, so every change commits
  // immediately -- one refresh per selection, not a batch.
  const handleApply = useCallback(
    (nextStart: string, nextEnd: string) => {
      setDataMask({
        extraFormData: {
          time_range: `${nextStart} : ${addDaysISO(nextEnd, 1)}`,
        },
        filterState: {
          value: [nextStart, nextEnd],
          label: `${formatDisplayDate(nextStart)} - ${formatDisplayDate(nextEnd)}`,
        },
      });
    },
    [setDataMask],
  );

  return (
    <div
      ref={containerRef}
      style={{
        width,
        height,
        display: 'flex',
        alignItems: 'center',
        position: 'relative',
      }}
      data-test="custom-date-range-filter"
    >
      <Pill
        type="button"
        onClick={() => setIsOpen(prev => !prev)}
        aria-expanded={isOpen}
      >
        <IconSlot>
          <CalendarIcon size={16} color={theme.colorTextSecondary} />
        </IconSlot>
        <LabelText>{label}</LabelText>
        <ChevronSlot>
          <ChevronDownIcon size={12} color={theme.colorTextSecondary} />
        </ChevronSlot>
      </Pill>
      {isOpen && (
        <DropdownAnchor>
          <DateRangeDropdown
            minDate={knownBounds.min}
            maxDate={knownBounds.max}
            startValue={effectiveStart}
            endValue={effectiveEnd}
            onChange={handleApply}
          />
        </DropdownAnchor>
      )}
    </div>
  );
}
