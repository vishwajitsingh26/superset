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
import Sparkline from './components/Sparkline';
import {
  Card,
  Centered,
  Delta,
  DeltaGroup,
  DriverName,
  DriverStrip,
  ExternalLink,
  Footer,
  FooterBlock,
  FooterLabel,
  FooterValue,
  Header,
  Logo,
  SparkArea,
  SparkCaption,
  SubLine,
  Title,
  Value,
  ValueRow,
} from './ProviderSpendCardStyles';
import { ProviderSpendCardProps } from './types';

export default function ProviderSpendCard(props: ProviderSpendCardProps) {
  const {
    width,
    height,
    title,
    logoUrl,
    valueText,
    deltaText,
    deltaPercentText,
    deltaPositive,
    subParts,
    series,
    sparkCaption,
    driverLabel,
    driverName,
    driverValueText,
    lastUpdatedText,
    linkLabel,
    linkUrl,
    accentColor,
    loading,
    error,
  } = props;
  const theme = useTheme();

  const subLine = useMemo(() => subParts.join('  \u2022  '), [subParts]);
  const sparkWidth = Math.max(0, width - theme.sizeUnit * 8);
  const sparkHeight = Math.max(28, Math.round(height * 0.2));
  const sparkColor = accentColor ?? theme.colorPrimary;

  const header = (
    <Header>
      <Title title={title}>{title}</Title>
      {logoUrl ? <Logo src={logoUrl} alt="" /> : null}
    </Header>
  );

  if (loading) {
    return (
      <Card cardHeight={height} data-testid="provider-spend-card">
        {header}
        <Centered>{t('Loading\u2026')}</Centered>
      </Card>
    );
  }

  if (error) {
    return (
      <Card cardHeight={height} data-testid="provider-spend-card">
        {header}
        <Centered>{error}</Centered>
      </Card>
    );
  }

  if (valueText === null) {
    return (
      <Card cardHeight={height} data-testid="provider-spend-card">
        {header}
        <Centered>{t('No data')}</Centered>
      </Card>
    );
  }

  return (
    <Card cardHeight={height} data-testid="provider-spend-card">
      {header}
      <ValueRow>
        <Value>{valueText}</Value>
        <DeltaGroup>
          {deltaText ? <Delta positive={deltaPositive}>{deltaText}</Delta> : null}
          {deltaPercentText ? (
            <Delta positive={deltaPositive}>
              {deltaPositive ? '\u25b2' : '\u25bc'}
              {deltaPercentText}
            </Delta>
          ) : null}
        </DeltaGroup>
      </ValueRow>
      {subLine ? <SubLine title={subLine}>{subLine}</SubLine> : null}
      {series.length > 1 ? (
        <SparkArea>
          <Sparkline
            values={series}
            width={sparkWidth}
            height={sparkHeight}
            color={sparkColor}
            label={sparkCaption}
          />
          <SparkCaption>{sparkCaption}</SparkCaption>
        </SparkArea>
      ) : null}
      {driverName ? (
        <DriverStrip>
          {`${driverLabel}: `}
          <DriverName>{driverName}</DriverName>
          {driverValueText ? `: ${driverValueText}` : ''}
        </DriverStrip>
      ) : null}
      <Footer>
        <FooterBlock>
          <FooterLabel>{t('Last Updated')}</FooterLabel>
          <FooterValue>{lastUpdatedText}</FooterValue>
        </FooterBlock>
        {linkLabel ? (
          <ExternalLink
            href={linkUrl ?? undefined}
            target="_blank"
            rel="noopener noreferrer"
          >
            {`${linkLabel} \u2197`}
          </ExternalLink>
        ) : null}
      </Footer>
    </Card>
  );
}
