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
import { BAR_MIN_HEIGHT } from '../constants';

export const Bar = styled.div<{ barHeight: number }>`
  display: flex;
  align-items: center;
  width: 100%;
  height: ${({ barHeight }) => Math.max(barHeight, BAR_MIN_HEIGHT)}px;
  box-sizing: border-box;
  padding: 0 ${({ theme }) => theme.sizeUnit * 3}px;
  background: ${({ theme }) => theme.colorBgContainer};
  border: 1px solid ${({ theme }) => theme.colorBorderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius}px;
  overflow: hidden;
`;

export const Prefix = styled.span`
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSize}px;
  white-space: nowrap;
`;

export const Status = styled.span`
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSize}px;
`;

// The design draws one continuous grey label plus a caret, so the select is
// chromeless inside the bar rather than a second bordered box.
export const SelectSlot = styled.div`
  flex: 0 1 auto;
  min-width: ${({ theme }) => theme.sizeUnit * 30}px;
  max-width: ${({ theme }) => theme.sizeUnit * 80}px;

  .ant-select-selector {
    background: transparent;
    border: none;
    box-shadow: none;
    padding-inline-start: ${({ theme }) => theme.sizeUnit}px;
  }

  .ant-select-selection-item,
  .ant-select-selection-placeholder,
  .ant-select-arrow {
    color: ${({ theme }) => theme.colorTextTertiary};
  }
`;
