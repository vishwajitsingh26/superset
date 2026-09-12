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
import { useCallback, useMemo, useState } from 'react';
import { t } from '../adapters/supersetAdapter';
import { DateRangeValue } from '../types';
import {
  MONTH_FULL_LABELS,
  WEEKDAY_LABELS,
  addMonths,
  buildMonthCells,
  firstOfMonthIso,
  formatDisplayDate,
  formatRangeLabel,
  lastOfMonthIso,
  monthIndexOf,
  yearOf,
} from '../utils/dateUtils';
import {
  Blank,
  DayCell,
  DayState,
  Grid,
  MonthTitle,
  NavButton,
  Panel,
  PanelFooter,
  PanelHeader,
  Weekday,
  WeekdayRow,
} from './CalendarPanelStyles';
import { ChevronLeft, ChevronRight } from './icons';

export type CalendarPanelProps = {
  min: string;
  max: string;
  value: DateRangeValue | null;
  accentColor: string | null;
  onSelect: (range: DateRangeValue) => void;
};

export default function CalendarPanel({
  min,
  max,
  value,
  accentColor,
  onSelect,
}: CalendarPanelProps) {
  const opensOn = value?.start ?? min;
  const [view, setView] = useState({
    year: yearOf(opensOn),
    month: monthIndexOf(opensOn),
  });
  const [pendingStart, setPendingStart] = useState<string | null>(null);

  const cells = useMemo(() => buildMonthCells(view.year, view.month), [view]);
  const monthStart = firstOfMonthIso(view.year, view.month);
  const monthEnd = lastOfMonthIso(view.year, view.month);

  const stateFor = useCallback(
    (iso: string): DayState => {
      if (iso < min || iso > max) return 'disabled';
      if (pendingStart) return iso === pendingStart ? 'edge' : 'idle';
      if (!value) return 'idle';
      if (iso === value.start || iso === value.end) return 'edge';
      return iso > value.start && iso < value.end ? 'inRange' : 'idle';
    },
    [max, min, pendingStart, value],
  );

  // Two clicks make a range, and the second one commits: the design shows no
  // Apply button on this control.
  const handleDayClick = useCallback(
    (iso: string) => {
      if (!pendingStart) {
        setPendingStart(iso);
        return;
      }
      const range: DateRangeValue =
        iso < pendingStart
          ? { start: iso, end: pendingStart }
          : { start: pendingStart, end: iso };
      setPendingStart(null);
      onSelect(range);
    },
    [onSelect, pendingStart],
  );

  const shift = useCallback((delta: number) => {
    setView(current => addMonths(current.year, current.month, delta));
  }, []);

  return (
    <Panel role="dialog" aria-label={t('Select a date range')}>
      <PanelHeader>
        <NavButton
          type="button"
          disabled={monthStart <= min}
          onClick={() => shift(-1)}
          aria-label={t('Previous month')}
        >
          <ChevronLeft />
        </NavButton>
        <MonthTitle>{`${MONTH_FULL_LABELS[view.month]} ${view.year}`}</MonthTitle>
        <NavButton
          type="button"
          disabled={monthEnd >= max}
          onClick={() => shift(1)}
          aria-label={t('Next month')}
        >
          <ChevronRight />
        </NavButton>
      </PanelHeader>
      <WeekdayRow aria-hidden="true">
        {WEEKDAY_LABELS.map((day, index) => (
          <Weekday key={`weekday-${index}`}>{day}</Weekday>
        ))}
      </WeekdayRow>
      <Grid>
        {cells.map((iso, index) =>
          iso === null ? (
            <Blank key={`blank-${index}`} />
          ) : (
            <DayCell
              key={iso}
              type="button"
              $state={stateFor(iso)}
              $accent={accentColor}
              disabled={iso < min || iso > max}
              onClick={() => handleDayClick(iso)}
              aria-label={formatDisplayDate(iso)}
            >
              {Number(iso.slice(8, 10))}
            </DayCell>
          ),
        )}
      </Grid>
      <PanelFooter>
        {pendingStart
          ? `${t('Start')}: ${formatDisplayDate(pendingStart)} — ${t('pick an end date')}`
          : `${t('Available')}: ${formatRangeLabel({ start: min, end: max })}`}
      </PanelFooter>
    </Panel>
  );
}
