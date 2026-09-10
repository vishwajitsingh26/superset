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
import { memo, useCallback, useMemo, useState } from 'react';
import {
  Button,
  Popover,
  Select,
  t,
  useTheme,
} from '../adapters/supersetAdapter';
import { FilterPanelProps, FilterPanelValue } from '../types';
import {
  buildFilterExtraFormData,
  buildFilterLabel,
  countActive,
  emptySelection,
  hasSelection,
} from '../utils/buildExtraFormData';
import { toStringArray } from '../utils/labels';
import FunnelIcon from './FunnelIcon';
import {
  CountText,
  FieldLabel,
  PanelBody,
  PanelField,
  PanelFooter,
  PanelMessage,
  TriggerButton,
  TriggerCount,
  TriggerWrap,
} from './FilterPanelStyles';

function FilterPanel({
  height,
  fields,
  selected,
  buttonLabel,
  accentColor,
  setDataMask,
}: FilterPanelProps) {
  const theme = useTheme();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<FilterPanelValue>(selected);

  const activeCount = useMemo(() => countActive(selected), [selected]);
  const accent = accentColor ?? theme.colorPrimary;
  const accentStyle = useMemo(() => ({ color: accent }), [accent]);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (next) setDraft(selected);
      setOpen(next);
    },
    [selected],
  );

  const handleFieldChange = useCallback((column: string, value: unknown) => {
    const values = toStringArray(value);
    setDraft(prev => ({ ...prev, [column]: values }));
  }, []);

  const apply = useCallback(() => {
    setDataMask({
      extraFormData: buildFilterExtraFormData(draft),
      filterState: {
        value: hasSelection(draft) ? draft : null,
        label: buildFilterLabel(draft, fields),
      },
    });
    setOpen(false);
  }, [draft, fields, setDataMask]);

  const clear = useCallback(() => {
    const empty = emptySelection(fields);
    setDraft(empty);
    setDataMask({
      extraFormData: {},
      filterState: { value: null, label: '' },
    });
    setOpen(false);
  }, [fields, setDataMask]);

  const content =
    fields.length === 0 ? (
      <PanelBody>
        <PanelMessage>
          {t('Choose one or more filter fields in the chart controls.')}
        </PanelMessage>
      </PanelBody>
    ) : (
      <PanelBody>
        {fields.map(field => (
          <PanelField key={field.column}>
            <FieldLabel>{field.label}</FieldLabel>
            <Select
              ariaLabel={field.label}
              mode="multiple"
              allowClear
              allowNewOptions={false}
              options={field.options}
              value={draft[field.column] ?? []}
              placeholder={t('All')}
              onChange={(value: unknown) =>
                handleFieldChange(field.column, value)
              }
            />
          </PanelField>
        ))}
        <PanelFooter>
          <Button buttonSize="small" buttonStyle="secondary" onClick={clear}>
            {t('Clear all')}
          </Button>
          <Button buttonSize="small" buttonStyle="primary" onClick={apply}>
            {t('Apply')}
          </Button>
        </PanelFooter>
      </PanelBody>
    );

  return (
    <TriggerWrap height={height} data-test="custom-filter-panel">
      <Popover
        content={content}
        trigger="click"
        placement="bottomRight"
        open={open}
        onOpenChange={handleOpenChange}
        destroyTooltipOnHide
      >
        <TriggerButton type="button">
          {buttonLabel}
          {activeCount > 0 ? (
            <TriggerCount style={accentStyle}>
              <CountText>{activeCount}</CountText>
            </TriggerCount>
          ) : null}
          <FunnelIcon size={theme.sizeUnit * 4} />
        </TriggerButton>
      </Popover>
    </TriggerWrap>
  );
}

export default memo(FilterPanel);
