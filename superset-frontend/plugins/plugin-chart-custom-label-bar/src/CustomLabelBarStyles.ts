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
import { styled } from './adapters/supersetAdapter';
import { DIMMED_OPACITY } from './constants';

export const ChartRoot = styled.div<{
  chartHeight: number;
  chartWidth: number;
}>`
  height: ${({ chartHeight }) => chartHeight}px;
  width: ${({ chartWidth }) => chartWidth}px;
  box-sizing: border-box;
  overflow: auto;
  padding: ${({ theme }) => theme.sizeUnit * 3}px
    ${({ theme }) => theme.sizeUnit * 4}px;
  background-color: ${({ theme }) => theme.colorBgContainer};
  border-radius: ${({ theme }) => theme.borderRadius}px;
`;

// A single grid for every row: the value column is sized by the widest value,
// so value labels line up instead of tracking each bar's end.
export const BarGrid = styled.div`
  display: grid;
  grid-template-columns: minmax(0, 1fr) max-content;
  column-gap: ${({ theme }) => theme.sizeUnit * 4}px;
  row-gap: ${({ theme }) => theme.sizeUnit * 4}px;
  align-items: end;
`;

export const BarCell = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.sizeUnit}px;
  min-width: 0;
`;

export const CategoryLabel = styled.div`
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  line-height: ${({ theme }) => theme.lineHeightSM};
  color: ${({ theme }) => theme.colorTextTertiary};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

export const BarTrack = styled.div`
  width: 100%;
`;

export const BarFill = styled.div<{
  ratio: number;
  barColor: string | null;
  barHeight: number;
  dimmed: boolean;
  clickable: boolean;
}>`
  height: ${({ barHeight }) => barHeight}px;
  width: ${({ ratio }) => Math.max(ratio * 100, 0.5)}%;
  background-color: ${({ barColor, theme }) => barColor ?? theme.colorPrimary};
  border-radius: ${({ theme }) => theme.borderRadiusXS}px;
  opacity: ${({ dimmed }) => (dimmed ? DIMMED_OPACITY : 1)};
  cursor: ${({ clickable }) => (clickable ? 'pointer' : 'default')};
  transition: opacity ${({ theme }) => theme.motionDurationMid};
`;

export const ValueLabel = styled.div`
  justify-self: end;
  align-self: end;
  white-space: nowrap;
  font-size: ${({ theme }) => theme.fontSize}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  color: ${({ theme }) => theme.colorText};
`;

export const StateMessage = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  color: ${({ theme }) => theme.colorTextTertiary};
`;
