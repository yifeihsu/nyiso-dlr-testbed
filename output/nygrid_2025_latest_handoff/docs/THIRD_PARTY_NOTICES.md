# Third-party notices for the current model package

The numerical runtime uses a code-only subset of MATPOWER 8.1, MIPS 1.5.2,
MP-Opt-Model 5.0, and MP-Test 8.1. Each component retains its original LICENSE
and AUTHORS files, and its CITATION file where supplied. The retained files
in vendor/matpower8.1 govern the redistributed code.

The current coupled AC solver uses MATPOWER network construction, case-index
conversion, device callbacks and power-flow result APIs. Package-specific
coupled loss equations, compact voltage/current recovery and thermal screening
remain distinct from the unmodified vendor sources.

MATPOWER's distributed case data, examples, tests, documentation, MOST and
optional solver binaries are not included. MATLAB is an external prerequisite
and is not redistributed. This runtime subset is not the full MATPOWER
installation. It is used through setup_nygrid_latest.

Official project: https://github.com/MATPOWER/matpower
Official license page: https://matpower.org/license/

The MATPOWER copyright, conditions and disclaimer are reproduced below; the
component-specific copies in vendor remain authoritative for their files.

The code in MATPOWER is distributed under the 3-clause BSD license
below. The MATPOWER case files distributed with MATPOWER are not covered
by the BSD license. In most cases, the data has either been included
with permission or has been converted from data available from a
public source.

The following is the official license notice:

--------------------------------------------------------------------------

Copyright (c) 1996-2025, Power Systems Engineering Research Center (PSERC)
and individual contributors (see AUTHORS file for details).
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

1. Redistributions of source code must retain the above copyright
notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright
notice, this list of conditions and the following disclaimer in the
documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
contributors may be used to endorse or promote products derived from
this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

--------------------------------------------------------------------------
