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
import { CSSProperties, useMemo } from 'react';
// In 6.x `styled` lives in the theme entry point, not in @superset-ui/core.
import { styled } from '@apache-superset/core/theme';
// In 6.x the translation helper `t` moved out of @superset-ui/core.
import { t } from '@apache-superset/core/translation';
import { LabeledHbarDatum, LabeledHbarProps } from './types';

/** Extra character cells reserved for the gap between a bar and its value. */
const VALUE_GUTTER_PADDING_CH = 2;

const Root = styled.div<{ height: number; width: number }>`
  ${({ theme, height, width }) => `
    height: ${height}px;
    width: ${width}px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    overflow-x: hidden;
    overflow-y: auto;
    background-color: ${theme.colorBgContainer};
    border-radius: ${theme.borderRadius}px;
    padding: ${theme.sizeUnit * 4}px;
  `}
`;

const Header = styled.div`
  ${({ theme }) => `
    margin-bottom: ${theme.sizeUnit * 4}px;
    color: ${theme.colorText};
    font-size: ${theme.fontSizeLG}px;
    font-weight: ${theme.fontWeightStrong};
    line-height: 1.25;
  `}
`;

const List = styled.div`
  ${({ theme }) => `
    display: flex;
    flex-direction: column;
    gap: ${theme.sizeUnit * 4}px;
  `}
`;

/** The category name sits ABOVE its bar, left aligned to the bar origin. */
const CategoryLabel = styled.div`
  ${({ theme }) => `
    margin-bottom: ${theme.sizeUnit}px;
    color: ${theme.colorTextTertiary};
    font-size: ${theme.fontSizeSM}px;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  `}
`;

/**
 * Bars share one left baseline. The row is narrowed by the value gutter so a
 * full-length bar plus its trailing label still fits inside the card.
 */
const BarRow = styled.div<{ reserveCh: number }>`
  ${({ theme, reserveCh }) => `
    display: flex;
    align-items: center;
    gap: ${theme.sizeUnit * 2}px;
    width: calc(100% - ${reserveCh}ch);
  `}
`;

const Bar = styled.div`
  flex: 0 0 auto;
  min-width: 1px;
  border-radius: 0;
`;

const ValueLabel = styled.div`
  ${({ theme }) => `
    flex: 0 0 auto;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
    color: ${theme.colorText};
    font-size: ${theme.fontSize}px;
    font-weight: ${theme.fontWeightStrong};
    line-height: 1.2;
  `}
`;

const EmptyState = styled.div`
  ${({ theme }) => `
    color: ${theme.colorTextTertiary};
    font-size: ${theme.fontSizeSM}px;
  `}
`;

type RenderableRow = LabeledHbarDatum & { barStyle: CSSProperties };

export default function LabeledHbar(props: LabeledHbarProps) {
  const {
    data,
    height,
    width,
    headerText,
    barColor,
    barThickness,
    valueColumnChars,
  } = props;

  // Rows arrive already ordered and cut by the query; only the per-bar style
  // object is derived here, and it is memoised so JSX does not rebuild it.
  const rows = useMemo<RenderableRow[]>(
    () =>
      data.map(datum => ({
        ...datum,
        barStyle: {
          width: `${datum.widthPercent}%`,
          height: `${barThickness}px`,
          backgroundColor: barColor,
        },
      })),
    [data, barColor, barThickness],
  );

  const reserveCh = valueColumnChars + VALUE_GUTTER_PADDING_CH;

  return (
    <Root height={height} width={width}>
      {headerText ? <Header>{headerText}</Header> : null}
      {rows.length === 0 ? (
        <EmptyState>{t('No data')}</EmptyState>
      ) : (
        <List>
          {rows.map(row => (
            <div key={row.key}>
              <CategoryLabel title={row.label}>{row.label}</CategoryLabel>
              <BarRow reserveCh={reserveCh}>
                <Bar style={row.barStyle} />
                <ValueLabel>{row.formattedValue}</ValueLabel>
              </BarRow>
            </div>
          ))}
        </List>
      )}
    </Root>
  );
}
