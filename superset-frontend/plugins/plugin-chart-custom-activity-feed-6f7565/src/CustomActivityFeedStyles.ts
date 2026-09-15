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

// No card here: the holder Superset wraps this in already carries the
// border, radius and 16px padding from the dashboard's own card_chrome.
export const Root = styled.div`
  width: 100%;
  height: 100%;
  overflow-y: auto;
  box-sizing: border-box;
`;

export const List = styled.div`
  display: flex;
  flex-direction: column;
  gap: 20px;
`;

export const CenteredMessage = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: ${({ theme }) => theme.colorTextTertiary};
  font-size: 13px;
`;
