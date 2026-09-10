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

// The design draws a compact rounded outlined pill sitting loose in the header
// row: white fill, hairline border, caret on the right.
export const PickerRoot = styled.div<{ accent: string }>`
  display: flex;
  align-items: center;
  width: 100%;
  height: 100%;

  .ant-select {
    width: 100%;
  }

  .ant-select-selector {
    border-radius: ${({ theme }) => theme.borderRadiusLG}px;
    border: 1px solid ${({ theme }) => theme.colorBorder};
    background: ${({ theme }) => theme.colorBgContainer};
    padding: 0 ${({ theme }) => theme.sizeUnit * 3}px;
  }

  .ant-select-selection-item {
    color: ${({ theme }) => theme.colorText};
    font-size: ${({ theme }) => theme.fontSize}px;
    font-weight: ${({ theme }) => theme.fontWeightStrong};
  }

  .ant-select:hover .ant-select-selector,
  .ant-select-focused .ant-select-selector {
    border-color: ${({ accent }) => accent};
  }

  .ant-select-arrow {
    color: ${({ theme }) => theme.colorTextSecondary};
  }
`;

export const StatusText = styled.div`
  display: flex;
  align-items: center;
  width: 100%;
  height: 100%;
  padding: 0 ${({ theme }) => theme.sizeUnit * 3}px;
  border-radius: ${({ theme }) => theme.borderRadiusLG}px;
  border: 1px solid ${({ theme }) => theme.colorBorder};
  background: ${({ theme }) => theme.colorBgContainer};
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
`;

export const ErrorText = styled(StatusText)`
  color: ${({ theme }) => theme.colorError};
  border-color: ${({ theme }) => theme.colorErrorBorder};
`;
