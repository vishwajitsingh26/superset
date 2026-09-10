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

export const Card = styled.div<{ cardHeight: number }>`
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.sizeUnit}px;
  width: 100%;
  height: ${({ cardHeight }) => cardHeight}px;
  padding: ${({ theme }) => theme.sizeUnit * 3}px;
  background: ${({ theme }) => theme.colorBgContainer};
  border: 1px solid ${({ theme }) => theme.colorBorder};
  border-radius: ${({ theme }) => theme.borderRadiusLG}px;
  overflow: hidden;
`;

export const Header = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
`;

export const Title = styled.span`
  color: ${({ theme }) => theme.colorText};
  font-size: ${({ theme }) => theme.fontSize}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const Logo = styled.img`
  height: ${({ theme }) => theme.sizeUnit * 4}px;
  object-fit: contain;
`;

export const ValueRow = styled.div`
  display: flex;
  align-items: baseline;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
`;

export const Value = styled.span`
  color: ${({ theme }) => theme.colorText};
  font-size: ${({ theme }) => theme.fontSizeXXL}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  line-height: 1.2;
`;

export const DeltaGroup = styled.span`
  display: flex;
  align-items: baseline;
  gap: ${({ theme }) => theme.sizeUnit}px;
`;

export const Delta = styled.span<{ positive: boolean }>`
  color: ${({ theme, positive }) =>
    positive ? theme.colorSuccess : theme.colorError};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  white-space: nowrap;
`;

export const SubLine = styled.div`
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const SparkArea = styled.div`
  display: flex;
  flex-direction: column;
  align-items: stretch;
  margin-top: ${({ theme }) => theme.sizeUnit}px;
`;

export const SparkCaption = styled.span`
  align-self: flex-end;
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
`;

export const DriverStrip = styled.div`
  margin-top: ${({ theme }) => theme.sizeUnit}px;
  padding: ${({ theme }) => theme.sizeUnit}px
    ${({ theme }) => theme.sizeUnit * 2}px;
  background: ${({ theme }) => theme.colorFillAlter};
  border-radius: ${({ theme }) => theme.borderRadius}px;
  color: ${({ theme }) => theme.colorTextSecondary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export const DriverName = styled.span`
  color: ${({ theme }) => theme.colorText};
  font-weight: ${({ theme }) => theme.fontWeightStrong};
`;

export const Footer = styled.div`
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
  margin-top: auto;
`;

export const FooterBlock = styled.div`
  display: flex;
  flex-direction: column;
`;

export const FooterLabel = styled.span`
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
`;

export const FooterValue = styled.span`
  color: ${({ theme }) => theme.colorTextSecondary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
`;

export const ExternalLink = styled.a`
  color: ${({ theme }) => theme.colorPrimary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  white-space: nowrap;
`;

export const Centered = styled.div`
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  text-align: center;
`;
