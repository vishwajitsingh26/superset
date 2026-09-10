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

export const Card = styled.div<{ height: number; width: number }>`
  ${({ theme, height, width }) => `
    height: ${height}px;
    width: ${width}px;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: flex-start;
    padding: ${theme.sizeUnit * 4}px;
    background-color: ${theme.colorBgContainer};
    border: 1px solid ${theme.colorBorder};
    border-radius: ${theme.borderRadius}px;
    box-shadow: none;
    overflow: hidden;
  `}
`;

export const Label = styled.div`
  ${({ theme }) => `
    font-size: ${theme.fontSize}px;
    font-weight: ${theme.fontWeightNormal};
    line-height: ${theme.sizeUnit * 5}px;
    color: ${theme.colorTextSecondary};
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  `}
`;

export const Value = styled.div`
  ${({ theme }) => `
    margin-top: ${theme.sizeUnit * 2}px;
    font-size: calc(${theme.fontSizeXXL}px * 1.5);
    font-weight: ${theme.fontWeightStrong};
    line-height: 1.15;
    letter-spacing: -0.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  `}
`;

export const StateText = styled.div`
  ${({ theme }) => `
    margin-top: ${theme.sizeUnit * 2}px;
    font-size: ${theme.fontSize}px;
    color: ${theme.colorTextTertiary};
  `}
`;
