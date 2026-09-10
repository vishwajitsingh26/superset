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

// Placeholder gallery thumbnail. A binary PNG cannot be emitted by the
// generator, so this data URI stands in until src/images/thumbnail.png is
// dropped in and this module is replaced by that import.
const thumbnail =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="100">' +
      '<rect width="160" height="100" fill="none" stroke="currentColor"/>' +
      '<rect x="96" y="16" width="48" height="20" rx="10" fill="none" stroke="currentColor"/>' +
      '<path d="M104 22h16l-6 7v6l-4 2v-8z" fill="currentColor"/>' +
      '</svg>',
  );

export default thumbnail;
