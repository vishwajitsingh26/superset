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

// The design draws one control row, controls flush right, no card chrome around
// the row itself; the chrome lives on each control.
export const Bar = styled.div`
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
  width: 100%;
  height: 100%;
  padding: ${({ theme }) => theme.sizeUnit}px
    ${({ theme }) => theme.sizeUnit * 2}px;
  box-sizing: border-box;
  background: transparent;
  overflow: visible;
`;

export const PeriodSelectWrapper = styled.div`
  min-width: 168px;

  .ant-select-selector {
    background: ${({ theme }) => theme.colorBgContainer};
    border: 1px solid ${({ theme }) => theme.colorBorder};
    border-radius: ${({ theme }) => theme.borderRadius}px;
    color: ${({ theme }) => theme.colorText};
    font-size: ${({ theme }) => theme.fontSize}px;
  }
`;

export const PanelBody = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.sizeUnit * 3}px;
  min-width: 240px;
  max-height: 320px;
  overflow-y: auto;
`;

export const PanelRow = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.sizeUnit}px;
`;

export const PanelLabel = styled.span`
  color: ${({ theme }) => theme.colorTextSecondary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
`;

export const PanelEmpty = styled.div`
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  max-width: 240px;
  line-height: ${({ theme }) => theme.sizeUnit * 5}px;
`;

export const ButtonLabel = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.sizeUnit}px;
`;
