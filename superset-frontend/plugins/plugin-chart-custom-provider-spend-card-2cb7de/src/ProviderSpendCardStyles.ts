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
import { styled } from './adapters/supersetAdapter';

export const Card = styled.div`
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
  padding: ${({ theme }) => theme.sizeUnit * 4}px;
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: ${({ theme }) => theme.borderRadiusLG}px;
  background-color: ${({ theme }) => theme.colorBgContainer};
  font-family: ${({ theme }) => theme.fontFamily};
`;

export const Centered = styled.div`
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
`;

export const Header = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
`;

export const Label = styled.div`
  color: ${({ theme }) => theme.colorText};
  font-size: ${({ theme }) => theme.fontSize}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
`;

export const Logo = styled.img`
  height: ${({ theme }) => theme.sizeUnit * 5}px;
  object-fit: contain;
`;

export const ValueRow = styled.div`
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
  margin-top: ${({ theme }) => theme.sizeUnit * 2}px;
`;

export const Value = styled.div`
  color: ${({ theme }) => theme.colorText};
  font-size: ${({ theme }) => Math.round(theme.fontSizeXL * 1.5)}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  line-height: 1.1;
`;

export const Delta = styled.span<{ $positive: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.sizeUnit}px;
  color: ${({ theme, $positive }) =>
    $positive ? theme.colorSuccess : theme.colorError};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
`;

export const SubLine = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.sizeUnit}px;
  margin-top: ${({ theme }) => theme.sizeUnit}px;
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
`;

export const Separator = styled.span`
  color: ${({ theme }) => theme.colorTextQuaternary};
`;

export const TrendWrap = styled.div`
  position: relative;
  flex: 1;
  min-height: ${({ theme }) => theme.sizeUnit * 9}px;
  margin-top: ${({ theme }) => theme.sizeUnit * 2}px;
`;

export const TrendCaption = styled.div`
  position: absolute;
  right: 0;
  bottom: 0;
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
`;

export const DriverStrip = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.sizeUnit}px;
  margin-top: ${({ theme }) => theme.sizeUnit * 2}px;
  padding: ${({ theme }) => theme.sizeUnit}px
    ${({ theme }) => theme.sizeUnit * 2}px;
  border-radius: ${({ theme }) => theme.borderRadius}px;
  background-color: ${({ theme }) => theme.colorFillAlter};
  color: ${({ theme }) => theme.colorText};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

export const DriverTitle = styled.span`
  font-weight: ${({ theme }) => theme.fontWeightStrong};
`;

export const Footer = styled.div`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
  margin-top: ${({ theme }) => theme.sizeUnit * 3}px;
`;

export const FooterLabel = styled.div`
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
`;

export const FooterValue = styled.div`
  color: ${({ theme }) => theme.colorTextSecondary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
`;

export const FooterLink = styled.a`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.sizeUnit}px;
  color: ${({ theme }) => theme.colorPrimary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  white-space: nowrap;
`;
