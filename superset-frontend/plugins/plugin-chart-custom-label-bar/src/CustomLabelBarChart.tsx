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
import { Fragment, memo, useCallback, useMemo } from 'react';
import { t } from './adapters/supersetAdapter';
import { CustomLabelBarProps } from './types';
import {
  BarCell,
  BarFill,
  BarGrid,
  BarTrack,
  CategoryLabel,
  ChartRoot,
  StateMessage,
  ValueLabel,
} from './CustomLabelBarStyles';

function CustomLabelBarChart(props: CustomLabelBarProps) {
  const {
    width,
    height,
    bars,
    barColor,
    barHeight,
    groupbyLabel,
    metricLabel,
    emitCrossFilters,
    selectedValues,
    setDataMask,
  } = props;

  const selected = useMemo(() => new Set(selectedValues), [selectedValues]);

  const handleSelect = useCallback(
    (key: string) => {
      if (!emitCrossFilters) return;
      const next = selected.has(key) ? [] : [key];
      setDataMask({
        extraFormData: next.length
          ? { filters: [{ col: groupbyLabel, op: 'IN' as const, val: next }] }
          : {},
        filterState: {
          value: next.length ? next : null,
          selectedValues: next.length ? next : null,
        },
      });
    },
    [emitCrossFilters, groupbyLabel, selected, setDataMask],
  );

  if (!groupbyLabel || !metricLabel) {
    return (
      <ChartRoot chartHeight={height} chartWidth={width}>
        <StateMessage>
          {t('Choose a dimension and a metric to render this chart.')}
        </StateMessage>
      </ChartRoot>
    );
  }

  if (bars.length === 0) {
    return (
      <ChartRoot chartHeight={height} chartWidth={width}>
        <StateMessage>{t('No data')}</StateMessage>
      </ChartRoot>
    );
  }

  return (
    <ChartRoot
      chartHeight={height}
      chartWidth={width}
      data-testid="custom-label-bar-chart"
    >
      <BarGrid>
        {bars.map(bar => (
          <Fragment key={bar.key}>
            <BarCell>
              <CategoryLabel title={bar.label}>{bar.label}</CategoryLabel>
              <BarTrack>
                <BarFill
                  role="button"
                  tabIndex={emitCrossFilters ? 0 : -1}
                  aria-label={`${bar.label}: ${bar.formattedValue}`}
                  ratio={bar.ratio}
                  barColor={barColor}
                  barHeight={barHeight}
                  clickable={emitCrossFilters}
                  dimmed={selected.size > 0 && !selected.has(bar.key)}
                  onClick={() => handleSelect(bar.key)}
                  onKeyDown={event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      handleSelect(bar.key);
                    }
                  }}
                />
              </BarTrack>
            </BarCell>
            <ValueLabel>{bar.formattedValue}</ValueLabel>
          </Fragment>
        ))}
      </BarGrid>
    </ChartRoot>
  );
}

export default memo(CustomLabelBarChart);
