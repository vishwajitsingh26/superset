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
import { memo, useMemo } from 'react';
import { t, useTheme } from './adapters/supersetAdapter';
import { KpiCardProps } from './types';
import { Card, Label, StateText, Value } from './KpiCardStyles';

function KpiCard({
  width,
  height,
  cardLabel,
  formattedValue,
  valueColor,
  status,
  errorMessage,
}: KpiCardProps) {
  const theme = useTheme();

  const valueStyle = useMemo(
    () => ({ color: valueColor ?? theme.colorText }),
    [valueColor, theme.colorText],
  );

  const stateMessage = useMemo(() => {
    if (status === 'loading') return t('Loading…');
    if (status === 'error') return errorMessage ?? t('Unable to load data');
    return t('No data');
  }, [status, errorMessage]);

  return (
    <Card width={width} height={height} data-testid="custom-kpi-card">
      <Label title={cardLabel}>{cardLabel}</Label>
      {status === 'ok' ? (
        <Value style={valueStyle} title={formattedValue}>
          {formattedValue}
        </Value>
      ) : (
        <StateText>{stateMessage}</StateText>
      )}
    </Card>
  );
}

export default memo(KpiCard);
