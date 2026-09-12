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

// The design draws this control at the top-right of the header band, so the
// shell right-aligns a content-width pill inside whatever cell it lands in.
export const Shell = styled.div<{ $width: number; $height: number }>`
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  gap: 4px;
  width: ${({ $width }) => $width}px;
  height: ${({ $height }) => $height}px;
  box-sizing: border-box;
`;

// White fill, 1px light border, 8px radius, 10px/14px padding: the pill as drawn.
export const Pill = styled.button<{ $pending: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 10px;
  max-width: 100%;
  padding: 10px 14px;
  background-color: ${({ theme }) => theme.colorBgContainer};
  border: 1px solid
    ${({ $pending, theme }) =>
      $pending ? theme.colorPrimary : theme.colorBorder};
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s ease;

  &:hover:not(:disabled) {
    border-color: ${({ theme }) => theme.colorPrimary};
  }

  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.colorPrimary};
    outline-offset: 1px;
  }

  &:disabled {
    cursor: not-allowed;
    background-color: ${({ theme }) => theme.colorBgContainerDisabled};
  }
`;

export const IconSlot = styled.span`
  display: inline-flex;
  flex-shrink: 0;
  color: ${({ theme }) => theme.colorTextSecondary};
`;

export const Label = styled.span<{ $muted: boolean }>`
  font-size: 13px;
  font-weight: 500;
  line-height: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: ${({ $muted, theme }) =>
    $muted ? theme.colorTextTertiary : theme.colorText};
`;

export const Caret = styled.span`
  display: inline-flex;
  flex-shrink: 0;
  margin-left: auto;
  padding-left: 6px;
  color: ${({ theme }) => theme.colorTextTertiary};
`;

export const Hint = styled.div`
  max-width: 100%;
  font-size: 11px;
  font-weight: 400;
  line-height: 14px;
  text-align: right;
  color: ${({ theme }) => theme.colorTextTertiary};
`;
