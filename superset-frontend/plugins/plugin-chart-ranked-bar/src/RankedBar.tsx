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
// In 6.x `styled` and the theme moved out of @superset-ui/core.
import { styled } from '@apache-superset/core/theme';
import { RankedBarProps } from './types';

/**
 * The card. Padding, radius and surface come from theme tokens so the chart
 * follows light and dark themes. The border is opt-in because the dashboard
 * chart holder already draws one.
 */
const Card = styled.div<{
  cardHeight: number;
  cardWidth: number;
  bordered: boolean;
}>`
  ${({ theme, cardHeight, cardWidth, bordered }) => `
    height: ${cardHeight}px;
    width: ${cardWidth}px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    padding: ${theme.sizeUnit * 4}px;
    color: ${theme.colorText};
    background-color: ${theme.colorBgContainer};
    border-radius: ${theme.borderRadius}px;
    border: ${bordered ? `1px solid ${theme.colorSplit}` : '0'};
  `}
`;

const Title = styled.div`
  ${({ theme }) => `
    flex: 0 0 auto;
    color: ${theme.colorText};
    font-size: ${theme.fontSizeLG}px;
    font-weight: ${theme.fontWeightStrong};
    line-height: 1.3;
    margin-bottom: ${theme.sizeUnit * 3}px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  `}
`;

/** No axis, no gridlines, no legend: just a stack of label + bar rows. */
const List = styled.div`
  ${({ theme }) => `
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: ${theme.sizeUnit * 2}px;
    overflow: hidden;
  `}
`;

const Item = styled.div`
  display: flex;
  flex-direction: column;
  flex: 0 1 auto;
  min-height: 0;
`;

/** Category sits above its bar in small grey text, not in a left axis gutter. */
const CategoryLabel = styled.div`
  ${({ theme }) => `
    color: ${theme.colorTextTertiary};
    font-size: ${theme.fontSizeSM}px;
    line-height: 1.4;
    margin-bottom: ${theme.sizeUnit}px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  `}
`;

const BarRow = styled.div`
  ${({ theme }) => `
    display: flex;
    align-items: center;
    font-size: ${theme.fontSize}px;
    font-variant-numeric: tabular-nums;
  `}
`;

const Bar = styled.div<{ thickness: number; fill: string }>`
  ${({ theme, thickness, fill }) => `
    flex: 0 0 auto;
    height: ${thickness}px;
    min-width: ${theme.sizeUnit / 2}px;
    background-color: ${fill};
    border-radius: ${theme.borderRadiusSM}px;
  `}
`;

/** Value is printed immediately to the right of its own bar, in dark text. */
const Value = styled.div`
  ${({ theme }) => `
    flex: 0 0 auto;
    color: ${theme.colorText};
    font-size: ${theme.fontSize}px;
    font-weight: ${theme.fontWeightStrong};
    padding-left: ${theme.sizeUnit * 2}px;
    white-space: nowrap;
  `}
`;

const EmptyState = styled.div`
  ${({ theme }) => `
    flex: 1 1 auto;
    display: flex;
    align-items: center;
    justify-content: center;
    color: ${theme.colorTextTertiary};
    font-size: ${theme.fontSize}px;
  `}
`;

/**
 * Renders the ranked bar card. Every derived value (ordering, formatting, bar
 * width) arrives precomputed from transformProps, so this component only maps
 * over the rows it is given and holds no derived state.
 */
export default function RankedBar(props: RankedBarProps) {
  const {
    data,
    height,
    width,
    cardTitle,
    barColor,
    barThickness,
    showCardBorder,
    emptyMessage,
  } = props;

  return (
    <Card cardHeight={height} cardWidth={width} bordered={showCardBorder}>
      {cardTitle ? <Title title={cardTitle}>{cardTitle}</Title> : null}
      {data.length === 0 ? (
        <EmptyState>{emptyMessage}</EmptyState>
      ) : (
        <List>
          {data.map(datum => (
            <Item key={datum.key}>
              <CategoryLabel title={datum.label}>{datum.label}</CategoryLabel>
              <BarRow>
                <Bar
                  thickness={barThickness}
                  fill={barColor}
                  style={datum.barStyle}
                />
                <Value>{datum.valueLabel}</Value>
              </BarRow>
            </Item>
          ))}
        </List>
      )}
    </Card>
  );
}
