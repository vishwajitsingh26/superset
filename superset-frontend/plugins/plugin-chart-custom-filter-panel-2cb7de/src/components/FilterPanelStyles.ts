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
import { styled } from '../adapters/supersetAdapter';
import { PANEL_WIDTH_UNITS } from '../constants';

// The design puts the control at the far right of the header row.
export const TriggerWrap = styled.div<{ height: number }>`
  display: flex;
  align-items: center;
  justify-content: flex-end;
  width: 100%;
  height: ${({ height }) => height}px;
  overflow: visible;
`;

export const TriggerButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.sizeUnit}px;
  height: ${({ theme }) => theme.sizeUnit * 8.5}px;
  padding: 0 ${({ theme }) => theme.sizeUnit * 3}px;
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: ${({ theme }) => theme.sizeUnit * 5}px;
  background: ${({ theme }) => theme.colorBgContainer};
  color: ${({ theme }) => theme.colorText};
  font-size: ${({ theme }) => theme.fontSize}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  line-height: 1;
  cursor: pointer;

  &:hover {
    border-color: ${({ theme }) => theme.colorPrimaryBorderHover};
  }
`;

export const TriggerCount = styled.span`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: ${({ theme }) => theme.sizeUnit * 4}px;
  height: ${({ theme }) => theme.sizeUnit * 4}px;
  padding: 0 ${({ theme }) => theme.sizeUnit / 2}px;
  border-radius: ${({ theme }) => theme.sizeUnit * 2}px;
  background: currentColor;
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  line-height: 1;
`;

export const CountText = styled.span`
  color: ${({ theme }) => theme.colorBgContainer};
  font-weight: ${({ theme }) => theme.fontWeightStrong};
`;

export const PanelBody = styled.div`
  width: ${({ theme }) => theme.sizeUnit * PANEL_WIDTH_UNITS}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.sizeUnit * 3}px;
`;

export const PanelField = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.sizeUnit}px;
`;

export const FieldLabel = styled.span`
  color: ${({ theme }) => theme.colorTextSecondary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
`;

export const PanelFooter = styled.div`
  display: flex;
  justify-content: flex-end;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
  padding-top: ${({ theme }) => theme.sizeUnit}px;
  border-top: 1px solid ${({ theme }) => theme.colorSplit};
`;

export const PanelMessage = styled.div`
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  padding: ${({ theme }) => theme.sizeUnit * 2}px 0;
`;
