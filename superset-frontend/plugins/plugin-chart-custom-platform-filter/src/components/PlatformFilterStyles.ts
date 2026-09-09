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
import { CONTROL_MAX_WIDTH } from '../constants';

// Full-width white bar: light border, rounded corners, one left-aligned control.
export const FilterBar = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.sizeUnit}px;
  width: 100%;
  box-sizing: border-box;
  padding: 0 ${({ theme }) => theme.sizeUnit * 3}px;
  background: ${({ theme }) => theme.colorBgContainer};
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: ${({ theme }) => theme.borderRadius}px;
  overflow: hidden;
`;

export const FilterLabel = styled.span`
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSize}px;
  white-space: nowrap;
`;

export const SelectWrap = styled.div`
  flex: 0 1 ${CONTROL_MAX_WIDTH}px;
  min-width: 0;

  .ant-select-selector {
    border-color: transparent;
    background: transparent;
  }
`;

export const StatusText = styled.span`
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSize}px;
`;
