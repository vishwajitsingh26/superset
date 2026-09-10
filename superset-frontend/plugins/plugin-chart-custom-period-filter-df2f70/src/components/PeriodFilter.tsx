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
import { Button, Popover, Select, t } from '../adapters/supersetAdapter';
import { buildPeriodExtraFormData } from '../utils/emitPeriod';
import {
  DimensionSelection,
  MonthOption,
  PeriodFilterProps,
} from '../types';
import FunnelIcon from './FunnelIcon';
import {
  Bar,
  ButtonLabel,
  PanelBody,
  PanelEmpty,
  PanelLabel,
  PanelRow,
  PeriodSelectWrapper,
} from './PeriodFilterStyles';

export default function PeriodFilter({
  monthOptions,
  dimensionOptions,
  selectedValue,
  dateColumn,
  showFilterButton,
  setDataMask,
  isRefreshing,
}: PeriodFilterProps) {
  const [panelOpen, setPanelOpen] = useState(false);

  const periodOptions = useMemo(
    () => monthOptions.map(o => ({ value: o.value, label: o.label })),
    [monthOptions],
  );

  const selectedPeriod =
    selectedValue?.period ?? monthOptions[0]?.value ?? null;
  const dimensions: DimensionSelection = selectedValue?.dimensions ?? {};

  const emit = useCallback(
    (period: string | null, dims: DimensionSelection) => {
      const option: MonthOption | undefined = monthOptions.find(
        o => o.value === period,
      );
      setDataMask({
        extraFormData: option
          ? buildPeriodExtraFormData(dateColumn, option, dims)
          : {},
        filterState: {
          value: option ? { period: option.value, dimensions: dims } : null,
          label: option?.label ?? '',
        },
      });
    },
    [dateColumn, monthOptions, setDataMask],
  );

  // Seed the dashboard with the newest month so the page is never unfiltered.
  useEffect(() => {
    if (!selectedValue?.period && selectedPeriod) {
      emit(selectedPeriod, {});
    }
  }, [emit, selectedPeriod, selectedValue]);

  const handleDimensionChange = useCallback(
    (column: string, values: string[]) => {
      emit(selectedPeriod, { ...dimensions, [column]: values });
    },
    [dimensions, emit, selectedPeriod],
  );

  const panel = useMemo(
    () =>
      dimensionOptions.length === 0 ? (
        <PanelEmpty>
          {t('No filter dimensions configured for this control.')}
        </PanelEmpty>
      ) : (
        <PanelBody>
          {dimensionOptions.map(dimension => (
            <PanelRow key={dimension.column}>
              <PanelLabel>{dimension.column}</PanelLabel>
              <Select
                allowClear
                mode="multiple"
                ariaLabel={dimension.column}
                placeholder={t('All')}
                value={dimensions[dimension.column] ?? []}
                options={dimension.values.map(v => ({ value: v, label: v }))}
                onChange={(value: unknown) =>
                  handleDimensionChange(
                    dimension.column,
                    (value as string[]) ?? [],
                  )
                }
              />
            </PanelRow>
          ))}
        </PanelBody>
      ),
    [dimensionOptions, dimensions, handleDimensionChange],
  );

  return (
    <Bar data-testid="custom-period-filter">
      <PeriodSelectWrapper>
        <Select
          ariaLabel={t('Period')}
          placeholder={
            isRefreshing ? t('Loading periods…') : t('Select a period')
          }
          disabled={periodOptions.length === 0}
          value={selectedPeriod ?? undefined}
          options={periodOptions}
          onChange={(value: unknown) => emit(value as string, dimensions)}
        />
      </PeriodSelectWrapper>
      {showFilterButton && (
        <Popover
          trigger="click"
          placement="bottomRight"
          open={panelOpen}
          onOpenChange={setPanelOpen}
          title={t('Filter')}
          content={panel}
        >
          <Button buttonStyle="secondary" buttonSize="small">
            <ButtonLabel>
              <FunnelIcon />
              {t('Filter')}
            </ButtonLabel>
          </Button>
        </Popover>
      )}
    </Bar>
  );
}
