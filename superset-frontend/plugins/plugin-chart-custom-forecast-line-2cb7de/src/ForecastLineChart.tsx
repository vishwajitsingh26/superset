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
import { useMemo, useState } from 'react';
import { t, useTheme } from './adapters/supersetAdapter';
import ChartHeader from './components/ChartHeader';
import EChartsPanel from './components/EChartsPanel';
import SeriesTable from './components/SeriesTable';
import { HEADER_HEIGHT } from './constants';
import { Card, Message } from './ForecastLineStyles';
import { ColoredSeries, ForecastLineChartProps, ViewMode } from './types';
import buildOption from './utils/buildOption';
import { formatMoney } from './utils/format';
import createTooltipFormatter from './utils/tooltip';

export default function ForecastLineChart(props: ForecastLineChartProps) {
  const { width, height, series, categories, dividerX, totals } = props;
  const theme = useTheme();
  const [mode, setMode] = useState<ViewMode>('line');

  const cardStyle = useMemo(() => ({ width, height }), [width, height]);

  const palette = useMemo(
    () =>
      props.palette.length > 0
        ? props.palette
        : [
            theme.colorPrimary,
            theme.colorSuccess,
            theme.colorWarning,
            theme.colorInfo,
            theme.colorError,
          ],
    [props.palette, theme],
  );

  const groups = useMemo(
    () => Array.from(new Set(series.map(item => item.group))),
    [series],
  );

  const colored: ColoredSeries[] = useMemo(
    () =>
      series.map(item => ({
        ...item,
        color: palette[groups.indexOf(item.group) % palette.length],
      })),
    [series, groups, palette],
  );

  const money = useMemo(
    () => (value: number) =>
      formatMoney(value, props.currencySymbol, props.showDecimals),
    [props.currencySymbol, props.showDecimals],
  );

  const tooltipFormatter = useMemo(
    () =>
      createTooltipFormatter({
        totals,
        showTotal: props.showTotalInTooltip,
        money,
        colors: {
          title: theme.colorText,
          label: theme.colorTextTertiary,
          value: theme.colorText,
          divider: theme.colorSplit,
        },
      }),
    [totals, props.showTotalInTooltip, money, theme],
  );

  const option = useMemo(
    () =>
      buildOption({
        series: colored,
        categories,
        dividerIndex: dividerX === null ? -1 : categories.indexOf(dividerX),
        mode,
        showLegend: props.showLegend,
        showScrollbar: props.showScrollbar,
        showDivider: props.showDivider,
        colors: {
          text: theme.colorText,
          muted: theme.colorTextTertiary,
          line: theme.colorSplit,
          card: theme.colorBgContainer,
          border: theme.colorBorderSecondary,
        },
        tooltipFormatter,
      }),
    [
      colored,
      categories,
      dividerX,
      mode,
      props.showLegend,
      props.showScrollbar,
      props.showDivider,
      theme,
      tooltipFormatter,
    ],
  );

  const bodyHeight = Math.max(
    height - HEADER_HEIGHT - theme.sizeUnit * 6,
    theme.sizeUnit * 10,
  );
  const bodyWidth = Math.max(width - theme.sizeUnit * 6, theme.sizeUnit * 10);

  let body = (
    <EChartsPanel option={option} width={bodyWidth} height={bodyHeight} />
  );
  if (props.loading) body = <Message>{t('Loading…')}</Message>;
  else if (props.error) body = <Message>{props.error}</Message>;
  else if (colored.length === 0) body = <Message>{t('No data')}</Message>;
  else if (mode === 'list')
    body = (
      <SeriesTable series={colored} categories={categories} money={money} />
    );

  return (
    <Card style={cardStyle} data-test="custom-forecast-line">
      <ChartHeader
        title={props.title}
        mode={mode}
        showToggle={props.showViewToggle}
        onChange={setMode}
      />
      {body}
    </Card>
  );
}
