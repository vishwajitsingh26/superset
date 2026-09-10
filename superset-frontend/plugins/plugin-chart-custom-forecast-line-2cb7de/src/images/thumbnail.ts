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

// Inline so the plugin carries no binary asset; swap for a real PNG when one exists.
const thumbnail =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='100'><polyline points='8,80 40,48 72,62' fill='none' stroke='gray' stroke-width='3'/><polyline points='72,62 104,34 152,20' fill='none' stroke='gray' stroke-width='3' stroke-dasharray='6 4'/><line x1='72' y1='10' x2='72' y2='90' stroke='silver' stroke-width='2' stroke-dasharray='4 4'/></svg>";

export default thumbnail;
