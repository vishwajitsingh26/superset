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
import { useEffect, useMemo, useState } from 'react';
import { Select } from './adapters/supersetAdapter';
import { CustomFilterBandProps, FilterSelection, FilterSlotKey } from './types';
import {
  CloudIcon,
  PeopleIcon,
  PinIcon,
  LayersIcon,
  ChevronDownIcon,
} from './components/Icons';
import { Pill, PillIcon, PillRow } from './components/CustomFilterBandStyles';

type IconComponent = (props: { size?: number }) => JSX.Element;

// Fixed by design: this widget is always these four dropdowns in this
// order, so the glyph-to-slot mapping is structural, not configurable.
const ICONS: Record<FilterSlotKey, IconComponent> = {
  provider: CloudIcon,
  account: PeopleIcon,
  region: PinIcon,
  environment: LayersIcon,
};

export default function CustomFilterBand({
  width,
  height,
  slots,
  selection,
  setDataMask,
}: CustomFilterBandProps) {
  const [localSelection, setLocalSelection] =
    useState<FilterSelection>(selection);

  useEffect(() => {
    setLocalSelection(selection);
  }, [
    selection.provider,
    selection.account,
    selection.region,
    selection.environment,
  ]);

  const slotOptions = useMemo(
    () =>
      slots.map(slot => {
        const IconComponent = ICONS[slot.key];
        return {
          ...slot,
          icon: <IconComponent size={16} />,
          choices: [
            { value: '', label: slot.allLabel },
            ...slot.options.map(value => ({ value, label: value })),
          ],
        };
      }),
    [slots],
  );

  // No Apply button is drawn, so every change commits immediately: the whole
  // combined selection (this slot's new value plus the other three untouched)
  // is pushed as one extraFormData.filters array on every change.
  const commit = (key: FilterSlotKey, rawValue: string) => {
    const next: FilterSelection = {
      ...localSelection,
      [key]: rawValue === '' ? null : rawValue,
    };
    setLocalSelection(next);

    const filters = slots
      .filter(slot => Boolean(next[slot.key]))
      .map(slot => ({
        col: slot.targetColumn,
        op: 'IN',
        val: [next[slot.key] as string],
      }));

    const activeLabels = slots
      .filter(slot => Boolean(next[slot.key]))
      .map(slot => next[slot.key] as string);

    const payload = {
      extraFormData: { filters },
      filterState: {
        value: next,
        label: activeLabels.length > 0 ? activeLabels.join(', ') : undefined,
      },
    };

    setDataMask(payload as unknown as Parameters<typeof setDataMask>[0]);
  };

  return (
    <PillRow style={{ width, height }} data-test="custom-filter-band">
      {slotOptions.map(slot => (
        <Pill key={slot.key}>
          <PillIcon aria-hidden>{slot.icon}</PillIcon>
          <Select
            value={localSelection[slot.key] ?? ''}
            options={slot.choices}
            onChange={(value: unknown) => commit(slot.key, String(value ?? ''))}
            suffixIcon={<ChevronDownIcon size={14} />}
            showSearch
            optionFilterProps={['label']}
          />
        </Pill>
      ))}
    </PillRow>
  );
}
