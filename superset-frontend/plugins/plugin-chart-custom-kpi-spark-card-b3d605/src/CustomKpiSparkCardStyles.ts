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
import { SIZES } from './utils/constants';

export const Card = styled.div`
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  width: 100%;
  height: 100%;
  overflow: hidden;
  padding: ${SIZES.cardPadding}px;
  background-color: ${({ theme }) => theme.colorBgContainer};
  border: 1px solid ${({ theme }) => theme.colorBorderSecondary};
  border-radius: ${SIZES.cardRadius}px;
  box-shadow: ${({ theme }) => theme.boxShadow};
`;

export const LabelRow = styled.div`
  display: flex;
  align-items: center;
  gap: ${SIZES.labelGap}px;
  min-width: 0;
`;

export const Label = styled.span`
  overflow: hidden;
  font-size: ${SIZES.labelFontSize}px;
  font-weight: 500;
  line-height: 20px;
  color: ${({ theme }) => theme.colorTextSecondary};
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const Value = styled.div`
  margin-top: ${SIZES.valueGap}px;
  font-size: ${SIZES.valueFontSize}px;
  font-weight: 700;
  line-height: 38px;
  letter-spacing: -0.5px;
  color: ${({ theme }) => theme.colorText};
  white-space: nowrap;
`;

export const BottomRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: ${SIZES.bottomGap}px;
  margin-top: ${SIZES.bottomGap}px;
`;

export const DeltaBlock = styled.div`
  display: flex;
  flex-direction: column;
  min-width: 0;
`;

export const DeltaText = styled.span<{ deltaColor: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: ${SIZES.deltaFontSize}px;
  font-weight: 500;
  line-height: 20px;
  color: ${({ deltaColor }) => deltaColor};
  white-space: nowrap;
`;

export const Caption = styled.span`
  margin-top: 4px;
  font-size: ${SIZES.captionFontSize}px;
  font-weight: 400;
  line-height: 16px;
  color: ${({ theme }) => theme.colorTextTertiary};
  white-space: nowrap;
`;

export const SparkSlot = styled.div`
  display: flex;
  flex-shrink: 0;
  align-items: center;
`;

export const Message = styled.div`
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  font-size: ${SIZES.labelFontSize}px;
  color: ${({ theme }) => theme.colorTextTertiary};
  text-align: center;
`;
