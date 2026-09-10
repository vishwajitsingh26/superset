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
import { useMemo } from 'react';
import { t, useTheme } from './adapters/supersetAdapter';
import DeltaBadge from './components/DeltaBadge';
import Sparkline from './components/Sparkline';
import * as S from './ProviderSpendCardStyles';
import { SpendCardProps } from './types';

export default function ProviderSpendCard(props: SpendCardProps) {
  const {
    width,
    height,
    state,
    errorMessage,
    label,
    logoUrl,
    value,
    absoluteDelta,
    absoluteDeltaPositive,
    percentDelta,
    percentDeltaPositive,
    share,
    shareLabel,
    rate,
    trend,
    trendCaption,
    accentColor,
    driverLabel,
    driverName,
    driverValue,
    lastUpdated,
    linkLabel,
    linkUrl,
  } = props;
  const theme = useTheme();
  const sizeStyle = useMemo(() => ({ width, height }), [width, height]);
  const strokeColor = accentColor || theme.colorPrimary;

  if (state !== 'ready') {
    const message =
      state === 'loading'
        ? t('Loading…')
        : state === 'error'
          ? errorMessage || t('This chart could not be loaded.')
          : t('No data');
    return (
      <S.Card style={sizeStyle} data-testid="custom-provider-spend-card">
        <S.Header>
          <S.Label>{label}</S.Label>
        </S.Header>
        <S.Centered>{message}</S.Centered>
      </S.Card>
    );
  }

  return (
    <S.Card style={sizeStyle} data-testid="custom-provider-spend-card">
      <S.Header>
        <S.Label>{label}</S.Label>
        {logoUrl ? <S.Logo src={logoUrl} alt={label} /> : null}
      </S.Header>
      <S.ValueRow>
        <S.Value>{value}</S.Value>
        {absoluteDelta ? (
          <DeltaBadge text={absoluteDelta} positive={absoluteDeltaPositive} />
        ) : null}
        {percentDelta ? (
          <DeltaBadge text={percentDelta} positive={percentDeltaPositive} />
        ) : null}
      </S.ValueRow>
      {share || rate ? (
        <S.SubLine>
          {share ? <span>{`${share} ${shareLabel}`.trim()}</span> : null}
          {share && rate ? <S.Separator>&bull;</S.Separator> : null}
          {rate ? <span>{rate}</span> : null}
        </S.SubLine>
      ) : null}
      <S.TrendWrap>
        <Sparkline points={trend} color={strokeColor} />
        {trendCaption ? (
          <S.TrendCaption>{trendCaption}</S.TrendCaption>
        ) : null}
      </S.TrendWrap>
      {driverName ? (
        <S.DriverStrip>
          <S.DriverTitle>{driverLabel}</S.DriverTitle>
          <span>{`${driverName}: ${driverValue ?? ''}`}</span>
        </S.DriverStrip>
      ) : null}
      <S.Footer>
        <div>
          <S.FooterLabel>{t('Last Updated')}</S.FooterLabel>
          <S.FooterValue>{lastUpdated || t('Unknown')}</S.FooterValue>
        </div>
        {linkLabel && linkUrl ? (
          <S.FooterLink href={linkUrl} target="_blank" rel="noopener noreferrer">
            {linkLabel}
            <svg width="10" height="10" viewBox="0 0 12 12" aria-hidden="true">
              <path
                d="M4.5 1H11v6.5H9.5V3.56L4.8 8.26 3.74 7.2l4.7-4.7H4.5V1z"
                fill="currentColor"
              />
              <path
                d="M1 3h3v1.5H2.5v5h5V8H9v4H1V3z"
                fill="currentColor"
              />
            </svg>
          </S.FooterLink>
        ) : null}
      </S.Footer>
    </S.Card>
  );
}
