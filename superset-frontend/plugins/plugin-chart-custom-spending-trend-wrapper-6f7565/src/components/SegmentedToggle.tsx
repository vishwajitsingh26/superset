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
// A three-segment pill, text labels only: light track, the active segment a
// solid filled rounded rect, the rest plain text. Matches the crop's own
// "Daily / Weekly / Monthly" control exactly — no icons, per its own spec.
import { styled } from '../adapters/supersetAdapter';

interface SegmentedToggleProps<T extends string> {
  options: readonly T[];
  value: T;
  onChange: (value: T) => void;
}

const Pill = styled.div`
  display: inline-flex;
  align-items: center;
  background: ${({ theme }) => theme.colorFillTertiary};
  border-radius: ${({ theme }) => theme.borderRadius}px;
  padding: 2px;
  gap: 2px;
`;

const Segment = styled.button<{ $active: boolean }>`
  border: none;
  cursor: pointer;
  padding: 4px 12px;
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  font-weight: 500;
  line-height: 16px;
  border-radius: ${({ theme }) => theme.borderRadiusSM}px;
  background: ${({ theme, $active }) =>
    $active ? theme.colorPrimary : 'transparent'};
  color: ${({ theme, $active }) =>
    $active ? theme.colorTextLightSolid : theme.colorTextSecondary};
  transition:
    background 0.15s ease,
    color 0.15s ease;

  &:hover {
    background: ${({ theme, $active }) =>
      $active ? theme.colorPrimary : theme.colorFillSecondary};
  }
`;

export default function SegmentedToggle<T extends string>({
  options,
  value,
  onChange,
}: SegmentedToggleProps<T>) {
  return (
    <Pill role="tablist" data-test="segmented-toggle">
      {options.map(option => (
        <Segment
          key={option}
          type="button"
          role="tab"
          aria-selected={option === value}
          $active={option === value}
          onClick={() => onChange(option)}
        >
          {option}
        </Segment>
      ))}
    </Pill>
  );
}
