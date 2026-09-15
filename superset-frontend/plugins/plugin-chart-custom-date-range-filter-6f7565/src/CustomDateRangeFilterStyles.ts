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
// Every colour here is a theme token, never a literal -- `check-custom-rules.js`
// rejects a hex/rgb literal anywhere in plugin source.
import { styled } from './adapters/supersetAdapter';

export const Pill = styled.button`
  display: inline-flex;
  align-items: center;
  height: 36px;
  padding: 0 12px;
  gap: 8px;
  font-family: inherit;
  background: ${({ theme }) => theme.colorBgContainer};
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: 8px;
  cursor: pointer;
  appearance: none;
  outline: none;

  &:hover {
    border-color: ${({ theme }) => theme.colorPrimary};
  }
`;

export const IconSlot = styled.span`
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
`;

export const LabelText = styled.span`
  font-size: 14px;
  font-weight: 500;
  color: ${({ theme }) => theme.colorText};
  white-space: nowrap;
`;

export const ChevronSlot = styled.span`
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
`;

export const DropdownAnchor = styled.div`
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  z-index: 10;
`;

export const DropdownPanel = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  min-width: 220px;
  background: ${({ theme }) => theme.colorBgContainer};
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: 8px;
  box-shadow: ${({ theme }) => theme.boxShadow};
`;

export const FieldRow = styled.div`
  display: flex;
  flex-direction: column;
  gap: 4px;
`;

export const FieldLabel = styled.span`
  font-size: 12px;
  font-weight: 400;
`;

export const DateInput = styled.input`
  font-size: 14px;
  padding: 6px 8px;
  font-family: inherit;
  color: ${({ theme }) => theme.colorText};
  background: ${({ theme }) => theme.colorBgContainer};
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: 6px;
`;
