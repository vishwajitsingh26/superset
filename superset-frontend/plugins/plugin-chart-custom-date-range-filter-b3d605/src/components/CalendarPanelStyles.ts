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

export type DayState = 'idle' | 'edge' | 'inRange' | 'disabled';

// The dropdown is not drawn in the design, so it takes the design system's
// card chrome: 12px radius, 1px border, the page's card shadow, 20px padding.
export const Panel = styled.div`
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 20;
  width: 288px;
  padding: 20px;
  box-sizing: border-box;
  background-color: ${({ theme }) => theme.colorBgContainer};
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: 12px;
  box-shadow: ${({ theme }) => theme.boxShadow};
`;

export const PanelHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
`;

export const MonthTitle = styled.div`
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
  color: ${({ theme }) => theme.colorText};
`;

export const NavButton = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  background-color: transparent;
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: 6px;
  cursor: pointer;
  color: ${({ theme }) => theme.colorTextSecondary};

  &:hover:not(:disabled) {
    border-color: ${({ theme }) => theme.colorPrimary};
    color: ${({ theme }) => theme.colorPrimary};
  }

  &:disabled {
    cursor: not-allowed;
    color: ${({ theme }) => theme.colorTextQuaternary};
  }
`;

export const WeekdayRow = styled.div`
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
  margin-bottom: 4px;
`;

export const Weekday = styled.span`
  text-align: center;
  font-size: 11px;
  font-weight: 500;
  line-height: 16px;
  color: ${({ theme }) => theme.colorTextTertiary};
`;

export const Grid = styled.div`
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
`;

export const Blank = styled.span`
  height: 30px;
`;

export const DayCell = styled.button<{
  $state: DayState;
  $accent: string | null;
}>`
  height: 30px;
  padding: 0;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  line-height: 30px;
  cursor: ${({ $state }) =>
    $state === 'disabled' ? 'not-allowed' : 'pointer'};
  background-color: ${({ $state, $accent, theme }) => {
    if ($state === 'edge') return $accent ?? theme.colorPrimary;
    if ($state === 'inRange') return theme.colorPrimaryBg;
    return 'transparent';
  }};
  color: ${({ $state, theme }) => {
    if ($state === 'edge') return theme.colorBgContainer;
    if ($state === 'disabled') return theme.colorTextQuaternary;
    return theme.colorText;
  }};

  &:hover {
    background-color: ${({ $state, $accent, theme }) => {
      if ($state === 'edge') return $accent ?? theme.colorPrimary;
      if ($state === 'disabled') return 'transparent';
      return theme.colorPrimaryBg;
    }};
  }
`;

export const PanelFooter = styled.div`
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid ${({ theme }) => theme.colorBorderSecondary};
  font-size: 11px;
  font-weight: 400;
  line-height: 16px;
  color: ${({ theme }) => theme.colorTextTertiary};
`;
