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
// No colours live here -- every one below is a theme token, matching the
// page's own repeated card border/fill/typography rather than this file's
// own guess at them.
import { styled } from '../adapters/supersetAdapter';

export const PillRow = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
  width: 100%;
  height: 100%;
`;

export const Pill = styled.div`
  display: flex;
  align-items: center;
  flex: 1 1 0;
  min-width: 0;
  height: 40px;
  padding: 0 12px;
  gap: 8px;
  border: 1px solid ${({ theme }) => theme.colorBorderSecondary};
  border-radius: 8px;
  background: ${({ theme }) => theme.colorBgContainer};

  .ant-select {
    flex: 1 1 0;
    min-width: 0;
  }

  .ant-select-selector {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    padding: 0 !important;
  }

  .ant-select-selection-item,
  .ant-select-selection-placeholder {
    font-size: 14px;
    font-weight: 500;
    color: ${({ theme }) => theme.colorText};
    padding: 0 !important;
  }

  .ant-select-arrow {
    color: ${({ theme }) => theme.colorTextTertiary};
  }
`;

export const PillIcon = styled.span`
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  color: ${({ theme }) => theme.colorTextSecondary};
`;
