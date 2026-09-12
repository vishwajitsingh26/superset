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
import { t } from './adapters/supersetAdapter';
import CalendarPanel from './components/CalendarPanel';
import {
  Caret,
  Hint,
  IconSlot,
  Label,
  Pill,
  Shell,
} from './components/DateRangePillStyles';
import { CalendarGlyph, ChevronDown } from './components/icons';
import { CustomDateRangeFilterProps, DateRangeValue } from './types';
import { buildDateRangeMask } from './utils/dataMask';
import { formatRangeLabel } from './utils/dateUtils';

export default function CustomDateRangeFilter({
  width,
  height,
  bounds,
  selected,
  defaultRange,
  targetDateColumn,
  accentColor,
  isLoading,
  errorMessage,
  setDataMask,
}: CustomDateRangeFilterProps) {
  const [open, setOpen] = useState(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const seededRef = useRef(false);

  const activeRange = selected ?? defaultRange ?? bounds;

  // The dashboard opens on the window the design displays, pushed once.
  useEffect(() => {
    if (seededRef.current || selected || !defaultRange) return;
    seededRef.current = true;
    setDataMask(buildDateRangeMask(defaultRange, targetDateColumn));
  }, [defaultRange, selected, setDataMask, targetDateColumn]);

  useEffect(() => {
    if (!open) return undefined;
    const handlePointer = (event: MouseEvent) => {
      if (
        shellRef.current &&
        !shellRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', handlePointer);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handlePointer);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  // No Apply button is drawn, so each selection commits immediately.
  const handleSelect = useCallback(
    (range: DateRangeValue) => {
      setDataMask(buildDateRangeMask(range, targetDateColumn));
      setOpen(false);
    },
    [setDataMask, targetDateColumn],
  );

  const label = useMemo(() => {
    if (errorMessage) return t('Date range unavailable');
    if (activeRange) return formatRangeLabel(activeRange);
    return isLoading ? t('Loading date range…') : t('No dates available');
  }, [activeRange, errorMessage, isLoading]);

  const disabled = Boolean(errorMessage) || !bounds;

  return (
    <Shell
      ref={shellRef}
      $width={width}
      $height={height}
      data-testid="custom-date-range-filter"
    >
      <Pill
        type="button"
        $pending={open}
        disabled={disabled}
        onClick={() => setOpen(current => !current)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t('Date range')}
      >
        <IconSlot>
          <CalendarGlyph />
        </IconSlot>
        <Label $muted={!activeRange || Boolean(errorMessage)}>{label}</Label>
        <Caret>
          <ChevronDown />
        </Caret>
      </Pill>
      {errorMessage ? <Hint role="alert">{errorMessage}</Hint> : null}
      {open && bounds ? (
        <CalendarPanel
          min={bounds.start}
          max={bounds.end}
          value={activeRange}
          accentColor={accentColor}
          onSelect={handleSelect}
        />
      ) : null}
    </Shell>
  );
}
