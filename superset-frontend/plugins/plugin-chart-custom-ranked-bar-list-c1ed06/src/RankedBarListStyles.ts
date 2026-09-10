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
import { BAR_HEIGHT_UNITS, VALUE_COLUMN_UNITS } from './constants';

export const Card = styled.div<{ height: number; width: number }>`
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  width: ${({ width }) => width}px;
  height: ${({ height }) => height}px;
  padding: ${({ theme }) => theme.sizeUnit * 4}px;
  background-color: ${({ theme }) => theme.colorBgContainer};
  border-radius: ${({ theme }) => theme.borderRadius}px;
  overflow: auto;
`;

export const CardTitle = styled.div`
  color: ${({ theme }) => theme.colorText};
  font-size: ${({ theme }) => theme.fontSizeLG}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  line-height: 1.4;
  margin-bottom: ${({ theme }) => theme.sizeUnit * 3}px;
`;

export const BarRow = styled.div`
  display: flex;
  flex-direction: column;
  margin-bottom: ${({ theme }) => theme.sizeUnit * 2}px;
`;

export const CategoryLabel = styled.div`
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  line-height: 1.4;
  text-align: left;
  margin-bottom: ${({ theme }) => theme.sizeUnit / 2}px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const BarLine = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
`;

export const BarTrack = styled.div`
  flex: 1 1 auto;
  min-width: 0;
  height: ${({ theme }) => theme.sizeUnit * BAR_HEIGHT_UNITS}px;
`;

export const BarFill = styled.div<{ ratio: number; fill: string }>`
  height: 100%;
  border-radius: 0;
  width: ${({ ratio }) => Math.max(0, Math.min(1, ratio)) * 100}%;
  background-color: ${({ fill }) => fill};
`;

export const ValueCell = styled.div`
  flex: 0 0 auto;
  width: ${({ theme }) => theme.sizeUnit * VALUE_COLUMN_UNITS}px;
  text-align: right;
  color: ${({ theme }) => theme.colorText};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  line-height: 1.4;
  white-space: nowrap;
`;

export const StateMessage = styled.div`
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  justify-content: center;
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
`;
